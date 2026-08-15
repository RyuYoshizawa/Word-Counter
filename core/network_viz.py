"""
network_viz.py
networkxグラフをJSON化可能な辞書に変換し、ノードの表示座標を計算する。色・サイズなどの
視覚エンコーディングはここでは決めない——ui/network_component.py側（D3.js）の責務とし、
このモジュールはcore/の設計原則通りStreamlit/ブラウザに依存しない純粋なデータ整形のみを行う。
"""

import math

import igraph as ig
import networkx as nx


def graph_to_json_dict(g: nx.Graph, positions: dict[str, tuple[float, float]],
                        communities: dict[str, int] | None = None) -> dict:
    """
    nx.Graphを {nodes, links, max_freq} のJSON化可能な辞書に変換する。
    nodes: {id, node_type, freq, attr_degree, community, x, y}（attr_degreeは単語ノードのみ、
    属性値ノードはNone。communityはcompute_communities()の結果、未指定なら全ノード0。
    x/yはcompute_layout()で計算済みの表示座標）
    links: {source, target, weight}
    """
    communities = communities or {}
    nodes = [
        {
            'id': n,
            'node_type': g.nodes[n].get('node_type', 'word'),
            'freq': int(g.nodes[n].get('freq', 1)),
            'attr_degree': (int(g.nodes[n]['attr_degree'])
                             if g.nodes[n].get('node_type') == 'word' and 'attr_degree' in g.nodes[n]
                             else None),
            'community': int(communities.get(n, 0)),
            'x': positions[n][0],
            'y': positions[n][1],
        }
        for n in g.nodes()
    ]
    links = [
        {'source': u, 'target': v, 'weight': float(g.edges[u, v]['weight'])}
        for u, v in g.edges()
    ]
    return {'nodes': nodes, 'links': links, 'max_freq': int(g.graph.get('max_freq', 1))}


_WEIGHT_SCALE_ATTR = 150.0  # 属性値ハブがあるグラフ（二部グラフ、word-word辺なし）用の引力係数
_WEIGHT_SCALE_WORD = 300.0  # 属性値ハブが無い語×語ネットワーク用の引力係数
# Jaccard係数（0〜1）をFRの引力として十分な強さに引き上げる係数。
# 値が小さすぎると、多くの語が同じ属性値ハブに集中する場合に反発力に負けて無関係な位置まで
# 散らばってしまう（実機検証で確認——ハブ固定時代の知見を、ハブ非固定の全ノード一括FRにも
# 引き継いだ。KH Coder実機の静止画出力（jaccard_3crass.png等）と比較し、ハブが正三角形等に
# 固定されず力学的に自然な位置へ収まる有機的な配置を目指す設計に刷新——単語ごとに1ハブへ
# 制限するような特別な処理は元々していない）。
#
# 属性マッピング時は300→150に引き下げた——「同じハブの語が円状ではなく縦横に直線的に
# 並ぶ」という不具合（ユーザー指摘）への対策で、引力が強すぎると語同士の反発力が相対的に
# 弱まり、ハブ周りに広く円状に展開する代わりに狭い扇状・線状に押し込まれてしまっていた。
# 一方、語×語ネットワーク（属性マッピング無し）では逆の問題が起きた——弱い橋渡し辺1本
# だけで繋がる小さな語群（例:「話す/気/対する」の3語クラスタ）が、全体から大きく離れた
# 位置に孤立し、その間に大きな空白ができてしまう不具合（ユーザー指摘の実データで発覚）。
# 検証したところ、この孤立距離はigraphのFR非決定性による「運」ではなく、弱い橋渡し辺1本
# という構造そのものに起因するほぼ決定的な結果で（同一構造で複数回計算しても孤立距離は
# ほぼ変化しない）、`_LAYOUT_TRIALS`回の試行選択だけでは解決できないことを確認した。
# 一方、引力係数を上げるとこの孤立距離は縮む（合成データで150→4.18、300→3.32、と約2割減）
# ことも確認済み——ハブの丸い展開を優先したい属性マッピング時は150のまま維持し、孤立語群
# の空白を優先したい語×語ネットワークは元の300に戻す、という使い分けにした。
# 「1ハブに語が集中する場合に反発力に負けて無関係な位置に散らばる」症状の再発防止の
# ストレステストは、実際に150を使う属性マッピング側（1ハブに45語集中）でのみ再検証済み。

_MIN_EDGE_WEIGHT = 0.15  # レイアウト計算用のJaccard係数下限（詳細は_layout_via_fr内のコメント参照）


def compute_layout(g: nx.Graph, width: int, height: int) -> dict[str, tuple[float, float]]:
    """
    全ノード（単語＋属性値ハブ、ハブが無ければ単語のみ）に対して、制約なしのigraph
    Fruchterman-Reingoldレイアウトを一括計算し、キャンバスに正規化して返す。属性値ハブを
    固定配置する特別な処理はしない——次数の高いノードは力学的に自然と中心付近へ集まる。
    """
    return _layout_via_fr(g, list(g.nodes()), width, height)


_LAYOUT_TRIALS = 5  # 複数回レイアウトを計算し、最も見た目の良い結果を選ぶ試行回数（下記参照）


def _edge_crossing_count(coords: list[list[float]], edges: list[tuple[int, int]]) -> int:
    """線分交差数を数える（グラフ描画の定番の「見やすさ」指標——交差が少ないほど整理されて見える）。"""
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    def segments_intersect(a, b, c, d):
        return ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d)

    count = 0
    for i in range(len(edges)):
        ui, vi = edges[i]
        a, b = coords[ui], coords[vi]
        for j in range(i + 1, len(edges)):
            uj, vj = edges[j]
            if ui in (uj, vj) or vi in (uj, vj):
                continue  # 端点を共有する辺同士は「交差」とはみなさない
            c, d = coords[uj], coords[vj]
            if segments_intersect(a, b, c, d):
                count += 1
    return count


def _nearest_neighbor_cv(coords: list[list[float]]) -> float:
    """最近傍距離の変動係数（標準偏差/平均）。小さいほどノードが均等に広がっている目安になる
    ——属性値ハブに語が線状・扇状に押し込まれる（一部だけ密集し他は疎になる）ケースほど大きくなる。"""
    n = len(coords)
    if n < 2:
        return 0.0
    nearest = []
    for i in range(n):
        best = min(
            math.dist(coords[i], coords[j]) for j in range(n) if j != i
        )
        nearest.append(best)
    mean_d = sum(nearest) / n
    if mean_d == 0:
        return 0.0
    variance = sum((d - mean_d) ** 2 for d in nearest) / n
    return (variance ** 0.5) / mean_d


def _layout_via_fr(g: nx.Graph, nodes: list[str], width: int, height: int) -> dict[str, tuple[float, float]]:
    """
    指定ノード集合をigraphのFruchterman-Reingoldでレイアウトし、キャンバスに正規化して返す。
    igraphのFRは同一seedでも呼び出すたびに結果が変わる（内部的な非決定性がある）ため、
    複数回計算して「線分交差数」「最近傍距離の均等さ」の総合順位が最も良い結果を選ぶ——
    1回だけの計算だと、属性値ハブに語が線状・扇状に偏って並ぶなど見た目の悪い結果を
    そのまま採用してしまうことがあった（実データでユーザー指摘、4パターン中2パターンで
    発生）。再現性はui層でのst.session_stateキャッシュに委ねる（同じグラフ構造に対して
    再計算しない限り、選んだ結果は変わらない）。
    """
    index_of = {n: i for i, n in enumerate(nodes)}
    edges = [
        (index_of[u], index_of[v], g.edges[u, v]['weight'])
        for u, v in g.edges()
        if u in index_of and v in index_of
    ]
    edge_pairs = [(u, v) for u, v, _ in edges]
    ig_graph = ig.Graph(n=len(nodes), edges=edge_pairs)
    has_attr_hub = any(g.nodes[node].get('node_type') == 'attr' for node in nodes)
    weight_scale = _WEIGHT_SCALE_ATTR if has_attr_hub else _WEIGHT_SCALE_WORD
    # 弱い橋渡し辺（Jaccard係数が非常に小さい）1本だけで繋がる語群は、素の係数のまま引力に
    # 使うと反発力に負けて全体から大きく孤立し、キャンバスに大きな空白ができる（実データで
    # ユーザー指摘）。この孤立自体はigraphのFR非決定性によるものではなく構造的にほぼ
    # 決定的に起きることを確認済み——`_LAYOUT_TRIALS`の試行選択では解決できない。対策として
    # 係数に下限（_MIN_EDGE_WEIGHT）を設け、それを下回る辺は底上げして引力を持たせる
    # （表示上のエッジの太さ・不透明度・ラベル数値には一切影響しない——あくまでレイアウト
    # 計算用の内部的な補正）。下限は実データの係数分布（実測でおよそ0.045〜0.73）を踏まえ、
    # 極端に弱い辺だけに影響するよう控えめな値にした——高すぎると「弱いが意味のある差」まで
    # 均してしまい、本来の強弱関係が潰れる。
    weights = [max(w, _MIN_EDGE_WEIGHT) * weight_scale for _, _, w in edges] or None

    n = len(nodes)
    # 円周上の初期配置から開始する（収束の質を上げる目的——上記の通り再現性はここでは狙わない）
    seed = [[math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)] for i in range(n)]

    candidates = []
    for _ in range(_LAYOUT_TRIALS):
        # niter既定値（500）だと、属性値ハブ数個に多数の語がぶら下がる二部グラフ（属性マッピング時、
        # word-word辺を使わない構造）で収束が不十分なまま終わり、ハブ同士の間隔が不揃いになって
        # キャンバスの一部に大きな空白ができる不具合があった（実データでユーザー指摘）。3000に
        # 引き上げて収束の質を上げる——実際の最大規模相当（170ノード）でも計算時間は0.2秒程度と
        # 軽量で、単語のみのネットワーク（属性マッピング無し）の見た目にも影響しないことを確認済み。
        raw = ig_graph.layout_fruchterman_reingold(weights=weights, seed=seed, niter=3000).coords
        crossings = _edge_crossing_count(raw, edge_pairs) if edge_pairs else 0
        nn_cv = _nearest_neighbor_cv(raw)
        candidates.append((raw, crossings, nn_cv))

    crossing_order = sorted(range(len(candidates)), key=lambda i: candidates[i][1])
    nn_order = sorted(range(len(candidates)), key=lambda i: candidates[i][2])
    crossing_rank = {idx: r for r, idx in enumerate(crossing_order)}
    nn_rank = {idx: r for r, idx in enumerate(nn_order)}
    best_idx = min(range(len(candidates)), key=lambda i: crossing_rank[i] + nn_rank[i])
    raw = candidates[best_idx][0]

    # マージンは60pxだとラベル文字の見切れが起きることがあった（実データでユーザー指摘）——
    # forceBoundary（D3側）はノードの円・正方形の半径分しか余白を見ておらず、その外側に
    # はみ出すラベル文字幅（特に属性値ハブの長い文言、例:「学校事務職員・その他」）を
    # 考慮していないため、ノードがキャンバス端近くに来るとラベルだけキャンバス外に
    # はみ出して見切れる。左右・上下とも合計180pxに広げて余裕を持たせる。
    # 上下・左右とも均等（90/90）にはしていない——タイトル・凡例（左上固定オーバーレイ）の
    # 分だけ上側に余白が必要な一方、下側は同じだけ余白を残すと全体が上に偏って見える
    # （実データでユーザー指摘、「ほんの少し下に」→「下げすぎ」→微調整で100/80に着地）。
    # 左右のマージンは属性値ハブの有無で使い分ける——属性マッピング時は長いハブ文言
    # （例:「学校事務職員・その他」）の見切れを避けるため広めの余白（95/85）を維持する一方、
    # 属性マッピング無し（語のみ、ラベルは短い）では見た目の確認で「もっと左に」との指摘が
    # あり、ラベルが短く見切れの心配が少ないことを踏まえて大きく左に詰めた（40/140）。
    margin_left = 95 if has_attr_hub else 40
    margin_right = 85 if has_attr_hub else 140
    margin_top = 105
    margin_bottom = 75
    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    span_x = max(max(xs) - min(xs), 1e-6)
    span_y = max(max(ys) - min(ys), 1e-6)
    avail_w = max(width - margin_left - margin_right, 1)
    avail_h = max(height - margin_top - margin_bottom, 1)
    # 縦横比を保つmin()スケールだと、FRの自然な点群の縦横比がキャンバスと合わない場合に
    # 片方の軸だけ余分に圧縮され、無駄な余白が生まれると同時にバブル間が実質的に詰まって
    # 見える（ユーザー指摘の「密集感」の一因）。力学的な距離に絶対的な縦横比の意味は無いため、
    # 縦横を独立してキャンバス一杯に引き伸ばす。
    scale_x = avail_w / span_x
    scale_y = avail_h / span_y

    min_x, min_y = min(xs), min(ys)
    positions = {
        node: (margin_left + (x - min_x) * scale_x, margin_top + (y - min_y) * scale_y)
        for node, (x, y) in zip(nodes, raw)
    }
    return _pull_in_outliers(positions)


_OUTLIER_PULL_FACTOR = 0.15  # 外れ値ノードを、閾値超過分のうち何割だけ重心へ引き寄せるか
# 実データでの検証時、0.6では「弱く繋がっているだけの孤立した語群」が本体に近づきすぎ、
# 本来の弱い関係性が実際より強く見えてしまった（ユーザー指摘）ため緩めた——極端な孤立
# （キャンバスの反対側まで飛ぶ）は避けつつ、目に見える距離感は残す。なお同時期に見つかった
# ラベル見切れ対策（margin 60→90）は、キャンバスの使用可能領域を狭めるため、それ単体でも
# 全ての距離（この孤立ギャップを含む）を比例して縮める副作用がある——0.35程度への緩和では
# marginの影響と相殺してほぼ変化が無かったため、0.15まで緩めて正味の効果を確保した。
_OUTLIER_THRESHOLD_MULT = 1.3  # 全ノードの重心距離の中央値の何倍を「外れ値」の閾値とするか


def _pull_in_outliers(positions: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """
    キャンバス正規化後の座標に対し、全ノードの重心から極端に離れたノードだけを、重心方向へ
    引き寄せる。弱い橋渡し辺1本だけで繋がる語群が全体から孤立し、キャンバスに大きな空白が
    できる問題への対策（実データでユーザー指摘）。
    このステップが「正規化後」の座標に対して行われるのが重要——正規化前の生のFR座標に対して
    同様の補正をかけても、キャンバスへの正規化（外接矩形をキャンバスいっぱいに引き伸ばす
    縦横独立スケール）が孤立ノードを含む外接矩形を基準にスケールを再計算してしまうため、
    孤立ノードの生座標上の距離を縮めてもスケール自体が連動して大きくなり、結果として
    キャンバス上の見た目の空白はほとんど変わらないことを検証で確認した。
    中央値ベースの閾値を使うことで、属性値ハブ等「重心からある程度離れているのが自然な」
    ノードには影響しない（実データ相当の合成グラフで、ハブは中央値の1.3倍の閾値を下回る
    ことを確認済み）。
    """
    if len(positions) < 3:
        return positions
    nodes = list(positions.keys())
    coords = list(positions.values())
    cx = sum(p[0] for p in coords) / len(coords)
    cy = sum(p[1] for p in coords) / len(coords)
    dists = sorted(math.dist(p, (cx, cy)) for p in coords)
    median = dists[len(dists) // 2]
    threshold = median * _OUTLIER_THRESHOLD_MULT

    result = {}
    for node in nodes:
        x, y = positions[node]
        d = math.dist((x, y), (cx, cy))
        if d > threshold and d > 0:
            new_d = threshold + (d - threshold) * (1 - _OUTLIER_PULL_FACTOR)
            ratio = new_d / d
            result[node] = (cx + (x - cx) * ratio, cy + (y - cy) * ratio)
        else:
            result[node] = (x, y)
    return result


def compute_communities(g: nx.Graph) -> dict[str, int]:
    """
    Louvain法（modularity最大化、igraphのcommunity_multilevel）で全ノードをサブグラフに分割する。
    KH Coder実機の静止画出力の「サブグラフ検出（modularity）」カラーリングに倣ったもの——
    属性値ハブが無い語×語ネットワークでは、色による構造情報が元々何も無く「まとまり」が
    視覚的に全く分からなくなる問題があったため（ハブ固定配置を撤廃した副作用）、色そのもので
    クラスター構造を示す。戻り値はノードID→サブグラフ番号（0始まり、サイズの大きい順）。
    """
    nodes = list(g.nodes())
    if len(nodes) < 2 or g.number_of_edges() == 0:
        return {n: 0 for n in nodes}

    index_of = {n: i for i, n in enumerate(nodes)}
    edges = [(index_of[u], index_of[v]) for u, v in g.edges()]
    weights = [g.edges[u, v]['weight'] for u, v in g.edges()]
    ig_graph = ig.Graph(n=len(nodes), edges=edges)
    membership = ig_graph.community_multilevel(weights=weights).membership

    sizes: dict[int, int] = {}
    for m in membership:
        sizes[m] = sizes.get(m, 0) + 1
    order = sorted(sizes, key=lambda m: sizes[m], reverse=True)
    remap = {old: new for new, old in enumerate(order)}
    return {nodes[i]: remap[m] for i, m in enumerate(membership)}
