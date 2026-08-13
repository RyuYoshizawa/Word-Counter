"""
tab_network.py
共起ネットワークマップタブ。Jaccard係数に基づく共起ネットワークをPlotlyで表示する。
属性列（Excel入力時）が指定されていれば、単語×属性値のマッピングも表示できる。
"""

import streamlit as st

from core.network import attr_value_doc_sets, build_cooccurrence_edges, build_graph, to_plotly_figure
from ui.common import pos_filter_caption


def render(doc_tokens: list, doc_attrs: list[dict], included_categories: set,
           stopwords: set[str] | None = None) -> None:
    st.subheader('共起ネットワークマップ')

    if not doc_tokens:
        st.info('データ準備タブでテキストを読み込んでください（1行＝1文書として集計します）。')
        return

    st.caption(pos_filter_caption(included_categories))
    attr_keys = sorted({k for attrs in doc_attrs for k in attrs})

    with st.expander('表示設定', expanded=False):
        # 1行あたりの項目数を増やして縦方向のスペースを詰めている
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            min_doc_freq = st.number_input('最低出現文書数', min_value=1, value=2, step=1)
        with col2:
            top_n = st.slider('対象語数（頻度上位）', min_value=10, max_value=150, value=60, step=10)
        with col3:
            max_edges = st.slider('最大エッジ数（語×語）', min_value=10, max_value=300, value=100, step=10)
        with col4:
            show_edge_labels = st.checkbox('エッジに係数を表示', value=True)

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            width = st.number_input('表示幅（px）', min_value=400, max_value=2000, value=900, step=50)
        with col6:
            height = st.number_input('表示高さ（px）', min_value=400, max_value=2000, value=700, step=50)
        attr_key = None
        attr_top_n = 20
        if attr_keys:
            with col7:
                attr_choice = st.selectbox('属性でマッピング（任意）', ['なし'] + attr_keys)
            if attr_choice != 'なし':
                attr_key = attr_choice
                with col8:
                    attr_top_n = st.slider('対象属性値数', min_value=5, max_value=50, value=20, step=5)

    attr_doc_sets = attr_value_doc_sets(doc_attrs, attr_key) if attr_key else None

    freq, word_word_edges, word_attr_edges, node_types = build_cooccurrence_edges(
        doc_tokens, included_categories, min_doc_freq=min_doc_freq, top_n=top_n,
        attr_doc_sets=attr_doc_sets, attr_top_n=attr_top_n, stopwords=stopwords,
    )

    if not word_word_edges and not word_attr_edges:
        st.warning('共起関係が見つかりませんでした。最低出現文書数や品詞フィルタを見直してください。')
        return

    g = build_graph(freq, word_word_edges, word_attr_edges, node_types=node_types, max_word_edges=max_edges)
    fig = to_plotly_figure(g, width=width, height=height, show_edge_labels=show_edge_labels)
    st.plotly_chart(fig, use_container_width=False)

    n_words = sum(1 for n in g.nodes() if g.nodes[n].get('node_type') == 'word')
    n_attrs = g.number_of_nodes() - n_words
    caption = f'単語ノード: {n_words} / エッジ数: {g.number_of_edges()} / 文書数: {len(doc_tokens)}'
    if n_attrs:
        caption = f'{caption} / 属性値ノード: {n_attrs}（属性: {attr_key}）'
    st.caption(caption)
