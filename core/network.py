"""
network.py
共起ネットワークマップ：文書-単語の出現有無からJaccard係数を計算し、
networkxでグラフを構築、Plotlyのインタラクティブな図に変換する。
属性値（例：年代・部署など）を追加のノードとしてマッピングすることもできる。
KH Coderの共起ネットワーク出力に近い見た目（属性値=赤い四角、単語の色分け=接続属性数、
サイズ/エッジ太さの凡例、エッジ数値ラベル）を再現する。
"""

from itertools import combinations
from typing import Literal

import networkx as nx
import numpy as np
import plotly.graph_objects as go

from .pos_rules import map_pos
from .tokenizer import Token

NodeType = Literal['word', 'attr']

_ATTR_COLOR = '#F08080'
_WORD_DEGREE_COLORS = {0: '#4C78A8', 1: '#FFD27F', 2: '#D4E157', 3: '#4DB6AC'}  # 3以上はまとめて3扱い
# ラベルをノードの丸の中に収められるよう、以前より大きめのサイズ範囲にしている。
_SIZE_MIN, _SIZE_MAX = 22, 60


def _doc_word_sets(doc_tokens: list[list[Token]], included_categories: set[str] | None,
                    stopwords: set[str] | None = None) -> list[set[str]]:
    """文書ごとの語集合（出現有無のみ、文書内での頻度は問わない）を返す"""
    sets = []
    for tokens in doc_tokens:
        words = set()
        for t in tokens:
            cat = map_pos(t)
            if included_categories is not None and cat not in included_categories:
                continue
            if stopwords and t.normalized in stopwords:
                continue
            words.add(t.normalized)
        sets.append(words)
    return sets


def attr_value_doc_sets(doc_attrs: list[dict], attr_key: str) -> dict[str, set[int]]:
    """指定した属性キーについて、属性値（文字列化）ごとに出現する文書indexの集合を返す（欠損値は除外）"""
    sets: dict[str, set[int]] = {}
    for i, attrs in enumerate(doc_attrs):
        val = attrs.get(attr_key)
        if val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue
        sets.setdefault(val_str, set()).add(i)
    return sets


def build_cooccurrence_edges(
    doc_tokens: list[list[Token]], included_categories: set[str] | None,
    min_doc_freq: int = 2, top_n: int = 60,
    attr_doc_sets: dict[str, set[int]] | None = None,
    attr_min_doc_freq: int = 1, attr_top_n: int = 20,
    stopwords: set[str] | None = None,
) -> tuple[dict[str, int], list[tuple[str, str, float]], list[tuple[str, str, float]], dict[str, NodeType]]:
    """
    Jaccard係数に基づく共起エッジを計算する。
    語×語エッジと語×属性値エッジは別々に返す——同じプールでJaccard係数順に競わせると、
    属性値エッジ（対象語数×対象属性値数で候補は少なく、Jaccard係数も語×語より低くなりがち）が
    語×語エッジに埋もれて消えてしまう不具合があったため（実データで属性値ノードが1個しか
    出ない事例で発覚）。語×属性値エッジは既にtop_n/attr_top_nで候補が絞られているため、
    後段のbuild_graphでは打ち切らず全て採用する。
    戻り値: (freq, word_word_edges, word_attr_edges, node_types)
    """
    doc_sets = _doc_word_sets(doc_tokens, included_categories, stopwords)

    doc_freq: dict[str, int] = {}
    word_docs: dict[str, set[int]] = {}
    for i, words in enumerate(doc_sets):
        for w in words:
            doc_freq[w] = doc_freq.get(w, 0) + 1
            word_docs.setdefault(w, set()).add(i)

    word_candidates = [w for w, f in doc_freq.items() if f >= min_doc_freq]
    word_candidates.sort(key=lambda w: doc_freq[w], reverse=True)
    word_candidates = word_candidates[:top_n]

    freq = {w: doc_freq[w] for w in word_candidates}
    all_docs = {w: word_docs[w] for w in word_candidates}
    node_types: dict[str, NodeType] = {w: 'word' for w in word_candidates}

    attr_candidates: list[str] = []
    if attr_doc_sets:
        attr_candidates = [v for v, docs in attr_doc_sets.items() if len(docs) >= attr_min_doc_freq]
        attr_candidates.sort(key=lambda v: len(attr_doc_sets[v]), reverse=True)
        attr_candidates = attr_candidates[:attr_top_n]
        for v in attr_candidates:
            freq[v] = len(attr_doc_sets[v])
            all_docs[v] = attr_doc_sets[v]
            node_types[v] = 'attr'

    word_word_edges = []
    for w1, w2 in combinations(word_candidates, 2):
        d1, d2 = all_docs[w1], all_docs[w2]
        inter = len(d1 & d2)
        if inter == 0:
            continue
        union = len(d1 | d2)
        word_word_edges.append((w1, w2, inter / union))

    word_attr_edges = []
    for w in word_candidates:
        for v in attr_candidates:
            d1, d2 = all_docs[w], all_docs[v]
            inter = len(d1 & d2)
            if inter == 0:
                continue
            union = len(d1 | d2)
            word_attr_edges.append((w, v, inter / union))

    return freq, word_word_edges, word_attr_edges, node_types


def build_graph(freq: dict[str, int], word_word_edges: list[tuple[str, str, float]],
                 word_attr_edges: list[tuple[str, str, float]] | None = None,
                 node_types: dict[str, NodeType] | None = None,
                 edge_threshold: float = 0.0, max_word_edges: int | None = 100) -> nx.Graph:
    """
    共起エッジからnetworkxグラフを構築する。語×語エッジのみJaccard係数上位max_word_edges本に
    絞り込み、語×属性値エッジは（既に候補数が絞られているため）全て採用する。
    """
    filtered_ww = [e for e in word_word_edges if e[2] >= edge_threshold]
    filtered_ww.sort(key=lambda e: e[2], reverse=True)
    if max_word_edges is not None:
        filtered_ww = filtered_ww[:max_word_edges]

    filtered_wa = [e for e in (word_attr_edges or []) if e[2] >= edge_threshold]

    g = nx.Graph()
    for w1, w2, jac in filtered_ww + filtered_wa:
        g.add_edge(w1, w2, weight=jac)

    node_types = node_types or {}
    for node in g.nodes():
        g.nodes[node]['freq'] = freq.get(node, 1)
        g.nodes[node]['node_type'] = node_types.get(node, 'word')

    for node in g.nodes():
        if g.nodes[node]['node_type'] != 'word':
            continue
        attr_degree = sum(1 for nb in g.neighbors(node) if g.nodes[nb].get('node_type') == 'attr')
        g.nodes[node]['attr_degree'] = attr_degree

    g.graph['max_freq'] = max((g.nodes[n]['freq'] for n in g.nodes()), default=1)
    return g


def _node_size(freq: int, max_freq: int) -> float:
    if max_freq <= 0:
        return _SIZE_MIN
    return _SIZE_MIN + (_SIZE_MAX - _SIZE_MIN) * (freq / max_freq)


def _bin_edges_by_weight(g: nx.Graph, n_bins: int = 4) -> list[tuple[list[tuple[str, str, float]], float]]:
    """エッジをJaccard係数でn_bins段階にビン分けする。戻り値は昇順（弱い→強い）"""
    edges_with_weight = [(u, v, g.edges[u, v]['weight']) for u, v in g.edges()]
    if not edges_with_weight:
        return []
    weights = [w for _, _, w in edges_with_weight]
    if len(set(weights)) == 1:
        return [(edges_with_weight, weights[0])]

    thresholds = np.percentile(weights, np.linspace(0, 100, n_bins + 1))
    bins: list[list[tuple[str, str, float]]] = [[] for _ in range(n_bins)]
    for u, v, w in edges_with_weight:
        idx = int(np.searchsorted(thresholds, w, side='right')) - 1
        idx = min(max(idx, 0), n_bins - 1)
        bins[idx].append((u, v, w))

    result = []
    for b in bins:
        if not b:
            continue
        ws = sorted(w for _, _, w in b)
        rep = ws[len(ws) // 2]
        result.append((b, rep))
    return result


def to_plotly_figure(g: nx.Graph, width: int = 900, height: int = 700,
                      show_edge_labels: bool = True) -> go.Figure:
    """
    networkxグラフをPlotlyの図に変換する（spring_layout = Fruchterman-Reingold相当）。
    属性値ノードが含まれる場合は単語（接続属性数=Degreeで色分け）と属性値（赤い四角）を
    別トレースで描画し、サイズ・エッジ太さの凡例、属性値が存在する場合のみ凡例全体を表示する
    （属性なし時は単一色・凡例なしの従来表示を維持——後方互換）。
    """
    if g.number_of_nodes() == 0:
        return go.Figure()

    pos = nx.spring_layout(g, seed=42)
    has_attr = any(g.nodes[n].get('node_type') == 'attr' for n in g.nodes())
    max_freq = g.graph.get('max_freq', 1)

    data: list[go.Scatter] = []

    # エッジ（Jaccard係数で4段階にビン分けし、ビンごとに別トレース＝太さを変える）
    edge_bins = _bin_edges_by_weight(g)
    edge_label_x, edge_label_y, edge_label_text = [], [], []
    for rank, (edges, rep) in enumerate(edge_bins):
        ex, ey = [], []
        for u, v, w in edges:
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            ex += [x0, x1, None]
            ey += [y0, y1, None]
            if show_edge_labels:
                edge_label_x.append((x0 + x1) / 2)
                edge_label_y.append((y0 + y1) / 2)
                edge_label_text.append(f'{w:.2f}')
        data.append(go.Scatter(
            x=ex, y=ey, mode='lines', name=f'係数: {rep:.2f}',
            line=dict(width=1 + rank, color='#999999'), hoverinfo='none',
            showlegend=has_attr,
        ))

    if show_edge_labels and edge_label_text:
        data.append(go.Scatter(
            x=edge_label_x, y=edge_label_y, mode='text', text=edge_label_text,
            textfont=dict(size=9, color='#777777'), hoverinfo='none', showlegend=False,
        ))

    # ノード（単語はDegreeで色分け、属性値は赤い四角）
    word_nodes = [n for n in g.nodes() if g.nodes[n].get('node_type') == 'word']
    if has_attr:
        degree_groups: dict[int, list[str]] = {}
        for n in word_nodes:
            deg = min(g.nodes[n].get('attr_degree', 0), 3)
            degree_groups.setdefault(deg, []).append(n)
        for deg in sorted(degree_groups):
            data.append(_node_trace(
                degree_groups[deg], g, pos, max_freq,
                color=_WORD_DEGREE_COLORS[deg], symbol='circle',
                name=f'Degree: {deg}{"+" if deg == 3 else ""}', show_legend=True,
            ))
    else:
        data.append(_node_trace(word_nodes, g, pos, max_freq, color='#4C78A8', symbol='circle',
                                 name='単語', show_legend=False))

    if has_attr:
        attr_nodes = [n for n in g.nodes() if g.nodes[n].get('node_type') == 'attr']
        data.append(_node_trace(attr_nodes, g, pos, max_freq, color=_ATTR_COLOR, symbol='square',
                                 name='属性値', show_legend=True))

    if has_attr:
        data.extend(_size_legend_traces(max_freq))

    fig = go.Figure(data=data)
    fig.update_layout(
        showlegend=has_attr, hovermode='closest', width=width, height=height,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(itemsizing='constant'),
    )
    return fig


def _node_trace(nodes: list[str], g: nx.Graph, pos: dict, max_freq: int,
                 color: str, symbol: str, name: str, show_legend: bool) -> go.Scatter:
    xs, ys, hover_text, sizes, font_sizes = [], [], [], [], []
    for n in nodes:
        x, y = pos[n]
        xs.append(x)
        ys.append(y)
        node_freq = g.nodes[n].get('freq', 1)
        hover_text.append(f'{n}（出現文書数: {node_freq}）')
        size = _node_size(node_freq, max_freq)
        sizes.append(size)
        # 語が長いほど文字を小さくして丸の中に収まりやすくする
        font_sizes.append(max(7, min(13, size / (2 + 0.6 * len(n)))))
    return go.Scatter(
        x=xs, y=ys, mode='markers+text', name=name,
        text=nodes, textposition='middle center', textfont=dict(size=font_sizes, color='#222222'),
        hovertext=hover_text, hoverinfo='text',
        marker=dict(size=sizes, color=color, symbol=symbol, line=dict(width=1, color='white')),
        showlegend=show_legend,
    )


def _size_legend_traces(max_freq: int) -> list[go.Scatter]:
    """出現文書数（Frequency）のサイズ凡例をダミートレースで作る"""
    steps = sorted({v for v in (max(1, max_freq // 6), max(1, max_freq // 3),
                                 max(1, max_freq // 2), max_freq) if v > 0})
    traces = []
    for v in steps:
        traces.append(go.Scatter(
            x=[None], y=[None], mode='markers', name=f'頻度: {v}',
            marker=dict(size=_node_size(v, max_freq), color='#CCCCCC', line=dict(width=1, color='white')),
            showlegend=True,
        ))
    return traces
