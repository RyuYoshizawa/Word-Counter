"""
tab_network.py
共起ネットワークマップタブ。Jaccard係数に基づく共起ネットワークをD3.js（st.iframe埋め込み）で表示する。
属性列（Excel入力時）が指定されていれば、単語×属性値のマッピングも表示できる。
"""

import hashlib
import json

import streamlit as st

from core.network import attr_value_doc_sets, build_cooccurrence_edges, build_graph, expand_to_sentence_units
from core.network_viz import compute_communities, compute_layout, graph_to_json_dict
from ui.common import pos_filter_caption
from ui.network_component import build_network_html


def render(doc_tokens: list, doc_attrs: list[dict], included_categories: set,
           stopwords: set[str] | None = None) -> None:
    st.subheader('共起ネットワークマップ')

    if not doc_tokens:
        st.info('データ準備タブでテキストを読み込んでください（1行＝1文書として集計します）。')
        return

    st.caption(pos_filter_caption(included_categories))
    attr_keys = sorted({k for attrs in doc_attrs for k in attrs})

    with st.expander('表示設定', expanded=False):
        agg_unit = st.selectbox(
            '集計単位', ['段落（文書）', '文'],
            help='「文」を選ぶと、同じ文（「。」等で区切った単位）内に共に出現する語のみを'
                 '共起とみなす——「段落（文書）」より厳しい判定になり、通常はエッジが減るか'
                 '係数が下がる方向になる。KH Coderが「共起ネットワークだけは"文"の設定も'
                 '必ず試すべき」としている選択肢。',
        )
        unit_label = '文' if agg_unit == '文' else '文書'

        # 1行あたりの項目数を増やして縦方向のスペースを詰めている
        col1, col2, col3, col4, col_font, col_size = st.columns(6)
        with col1:
            min_doc_freq = st.number_input(f'最低出現{unit_label}数', min_value=1, value=2, step=1)
        with col2:
            top_n = st.slider('対象語数（頻度上位）', min_value=10, max_value=150, value=60, step=10)
        with col3:
            max_edges = st.slider(
                '最大エッジ数（語×語）', min_value=10, max_value=300, value=100, step=10,
                help='属性でマッピング時は使用されません（単語×属性値エッジのみで構成されるため）。',
            )
        with col4:
            show_edge_labels = st.checkbox('エッジに係数を表示', value=True)
        with col_font:
            label_font_size = st.slider('文字サイズ', min_value=6, max_value=20, value=11, step=1)
        with col_size:
            node_size_scale = st.slider(
                'バブルサイズ', min_value=0.5, max_value=3.0, value=1.5, step=0.1,
                help='ノードの大きさの倍率。多少重なっても大きい方が見やすければ上げる。',
            )

        col5, col6, col7, col8, col9 = st.columns(5)
        with col5:
            width = st.number_input('表示幅（px）', min_value=400, max_value=2000, value=900, step=50)
        with col6:
            height = st.number_input('表示高さ（px）', min_value=400, max_value=2000, value=700, step=50)
        attr_key = None
        attr_top_n = 20
        max_attr_edges = 60
        if attr_keys:
            with col7:
                attr_choice = st.selectbox('属性でマッピング（任意）', ['なし'] + attr_keys)
            if attr_choice != 'なし':
                attr_key = attr_choice
                with col8:
                    attr_top_n = st.slider('対象属性値数', min_value=5, max_value=50, value=20, step=5)
                with col9:
                    max_attr_edges = st.slider(
                        '最大エッジ数（単語×属性値）', min_value=10, max_value=300, value=60, step=10,
                        help='属性でマッピング時は、単語×単語エッジを使わず単語×属性値エッジのみで'
                             '構成する。係数上位のエッジを全体からグローバルに残すため、複数の属性値'
                             'に強く繋がる語は自然に複数本のエッジを持つ。',
                    )

    # 「文」単位の場合は、語のdoc-set・属性のdoc-setの両方を同じ展開結果（unit_tokens/
    # unit_attrs）に揃える——片方だけ差し替えるとインデックスがずれ、Jaccard交差が
    # エラーにならないまま無意味な値になる（実装時に要注意と分かっている落とし穴）。
    if agg_unit == '文':
        unit_tokens, unit_attrs = expand_to_sentence_units(doc_tokens, doc_attrs)
    else:
        unit_tokens, unit_attrs = doc_tokens, doc_attrs

    attr_doc_sets = attr_value_doc_sets(unit_attrs, attr_key) if attr_key else None

    freq, word_word_edges, word_attr_edges, node_types = build_cooccurrence_edges(
        unit_tokens, included_categories, min_doc_freq=min_doc_freq, top_n=top_n,
        attr_doc_sets=attr_doc_sets, attr_top_n=attr_top_n, stopwords=stopwords,
    )

    if not word_word_edges and not word_attr_edges:
        st.warning('共起関係が見つかりませんでした。最低出現文書数や品詞フィルタを見直してください。')
        return

    # 属性でマッピング時は単語×単語エッジを使わず、単語×属性値のみで構成する純粋な二部グラフにする
    # （KH Coderの実出力を解析した結果に合わせた設計——詳細はcore/network.pyのdocstring参照）。
    g = build_graph(freq, word_word_edges if not attr_key else [], word_attr_edges,
                     node_types=node_types, max_word_edges=max_edges, max_attr_edges=max_attr_edges)

    # igraphのFruchterman-Reingoldレイアウトは呼び出しごとに結果が変わりうるため、
    # 同じグラフ構造（ノード・エッジ・重み・キャンバスサイズ）に対しては計算済みの
    # レイアウトをセッション内で使い回す——タブと無関係な操作でのStreamlit全体再実行の
    # たびにネットワーク図が再シャッフルされる不安定さを防ぐ（app.pyの
    # `_tokenize_cache_key`と同じキャッシュパターン）。
    layout_key_src = json.dumps({
        'nodes': sorted((n, g.nodes[n]['node_type']) for n in g.nodes()),
        'edges': sorted((u, v, g.edges[u, v]['weight']) for u, v in g.edges()),
        'width': width, 'height': height,
    }, sort_keys=True)
    layout_key = hashlib.md5(layout_key_src.encode()).hexdigest()
    layout_cache = st.session_state.setdefault('_network_layout_cache', {})
    if layout_key not in layout_cache:
        layout_cache[layout_key] = (compute_layout(g, width, height), compute_communities(g))
    positions, communities = layout_cache[layout_key]

    payload = graph_to_json_dict(g, positions, communities)
    project_name = (st.session_state.get('project') or {}).get('name', '')
    html = build_network_html(payload, width=width, height=height, show_edge_labels=show_edge_labels,
                               label_font_size=label_font_size, node_size_scale=node_size_scale,
                               title='co-occurrence network map', subtitle=project_name)
    st.iframe(html, width=width, height=height)

    n_words = sum(1 for n in g.nodes() if g.nodes[n].get('node_type') == 'word')
    n_attrs = g.number_of_nodes() - n_words
    caption = f'単語ノード: {n_words} / エッジ数: {g.number_of_edges()} / {unit_label}数: {len(unit_tokens)}'
    if agg_unit == '文':
        caption = f'{caption}（元の文書数: {len(doc_tokens)}）'
    if n_attrs:
        caption = f'{caption} / 属性値ノード: {n_attrs}（属性: {attr_key}）'
    st.caption(caption)
