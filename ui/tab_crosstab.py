"""
tab_crosstab.py
コーディング集計タブ：単語・語群を意味的にまとめたコード（表記ゆれを広く解釈したグルーピング）
を定義し、①出現率、②既存属性とのクロス集計、③コードと語の共起分析、④コードのクラスター分析
をまとめて表示する。
"""

import hashlib
import json

import numpy as np
import streamlit as st

from core.clustering import (
    build_word_doc_matrix,
    compute_linkage,
    figure_to_png_bytes,
    figure_to_svg_bytes,
    render_dendrogram,
)
from core.codebook import (
    apply_codebook,
    code_doc_matrix,
    code_occurrence_rates,
    crosstab_codes_by_attr,
    label_codes,
    parse_codebook,
)
from core.network import build_cooccurrence_edges, build_graph
from core.network_viz import compute_layout, graph_to_json_dict
from ui.network_component import build_network_html

DPI_OPTIONS = [150, 300, 600]


def render(doc_tokens: list, documents: list, doc_attrs: list[dict],
           included_categories: set, stopwords: set[str] | None = None) -> None:
    st.subheader('コーディング集計')
    st.caption(
        'コードブック（1行1コード、「コード名: トリガー1, トリガー2, ...」形式）で、表記ゆれ'
        'だけでなく同じ概念を指す語句を広くまとめられます（例:「年配: 年配, ベテラン, 年長, '
        '経歴の長い, 年寄り, 高齢, 経験豊か」）。トリガーが単語の見出し語と一致すればそれを、'
        'それ以外は原文への部分文字列一致で該当文書を判定します（品詞フィルタ・ストップワード'
        'の対象外——常に全語を対象に判定します）。'
    )

    if not doc_tokens:
        st.info('データ準備タブでテキストを読み込んでください。')
        return

    codebook_text = st.text_area(
        'コードブック（1行1コード）', height=150, key='codebook_text',
        placeholder='年配: 年配, ベテラン, 年長, 経歴の長い, 年寄り, 高齢, 経験豊か\n教師: 先生, 教員, 教師',
    )
    codes = parse_codebook(codebook_text)
    if not codes:
        st.info('コードブックを入力してください。')
        return

    code_doc_sets = apply_codebook(codes, doc_tokens, documents)
    n_docs = len(doc_tokens)

    st.markdown('##### 出現率')
    rates = code_occurrence_rates(code_doc_sets, n_docs)
    rate_rows = [
        {'コード': name, '該当文書数': len(code_doc_sets[name]), '出現率': rates.get(name, 0.0) * 100}
        for name in code_doc_sets
    ]
    st.dataframe(
        rate_rows, height=min(400, 40 + 35 * len(rate_rows)), use_container_width=True,
        column_config={'出現率': st.column_config.NumberColumn(format='%.1f%%')},
        hide_index=True,
    )

    st.markdown('##### 属性クロス集計')
    attr_keys = sorted({k for attrs in doc_attrs for k in attrs})
    if attr_keys:
        attr_key = st.selectbox('クロス集計する属性', attr_keys, key='coding_crosstab_attr')
        df = crosstab_codes_by_attr(code_doc_sets, doc_attrs, attr_key)
        st.dataframe(df, height=min(400, 40 + 35 * len(df)), use_container_width=True)
    else:
        st.caption('属性情報がありません。Excel入力で属性列（年代・学校・職位など）を指定すると、ここに表示されます。')

    with st.expander('各コードの該当状況'):
        for code in codes:
            n = len(code_doc_sets.get(code['name'], set()))
            st.caption(f"「{code['name']}」: {n}文書で該当（トリガー: {', '.join(code['triggers'])}）")

    st.divider()
    _render_code_network(doc_tokens, code_doc_sets, codes, included_categories, stopwords)

    st.divider()
    _render_code_clustering(doc_tokens, code_doc_sets, included_categories, stopwords)


def _render_code_network(doc_tokens: list, code_doc_sets: dict[str, set[int]], codes: list[dict],
                          included_categories: set, stopwords: set[str] | None) -> None:
    """コードと通常の語を混ぜた共起ネットワーク（関係性理解が目的のため、既定で語を含める）。"""
    st.markdown('##### コードの共起分析')
    st.caption('コードを通常の語と混ぜて分析します（コードがどんな語と結びついているかを見るため）。')

    with st.expander('表示設定', expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            min_doc_freq = st.number_input('最低出現文書数', min_value=1, value=2, step=1,
                                            key='coding_net_min_doc_freq')
        with col2:
            top_n = st.slider('対象語数（頻度上位）', min_value=10, max_value=150, value=60, step=10,
                               key='coding_net_top_n')
        with col3:
            width = st.number_input('表示幅（px）', min_value=400, max_value=2000, value=900, step=50,
                                     key='coding_net_width')
        with col4:
            height = st.number_input('表示高さ（px）', min_value=400, max_value=2000, value=600, step=50,
                                      key='coding_net_height')

    labeled = label_codes(code_doc_sets)
    n_codes = max(len(codes), 1)
    freq, _word_word_edges, word_attr_edges, node_types = build_cooccurrence_edges(
        doc_tokens, included_categories, min_doc_freq=min_doc_freq, top_n=top_n,
        attr_doc_sets=labeled, attr_top_n=n_codes, stopwords=stopwords,
    )

    if not word_attr_edges:
        st.warning('コードと語の共起関係が見つかりませんでした。最低出現文書数や対象語数を見直してください。')
        return

    # 既存の属性マッピング時と同じ純粋二部グラフ（コード×語のみ、語×語エッジは使わない）。
    g = build_graph(freq, [], word_attr_edges, node_types=node_types,
                     max_word_edges=top_n, max_attr_edges=n_codes * 20)

    layout_key_src = json.dumps({
        'nodes': sorted((n, g.nodes[n]['node_type']) for n in g.nodes()),
        'edges': sorted((u, v, g.edges[u, v]['weight']) for u, v in g.edges()),
        'width': width, 'height': height,
    }, sort_keys=True)
    layout_key = hashlib.md5(layout_key_src.encode()).hexdigest()
    layout_cache = st.session_state.setdefault('_coding_network_layout_cache', {})
    if layout_key not in layout_cache:
        layout_cache[layout_key] = compute_layout(g, width, height)
    positions = layout_cache[layout_key]

    payload = graph_to_json_dict(g, positions)
    project_name = (st.session_state.get('project') or {}).get('name', '')
    html = build_network_html(
        payload, width=width, height=height, title='コード共起ネットワーク', subtitle=project_name,
        attr_kind_label='コード', attr_degree_label='接続コード数',
    )
    st.iframe(html, width=width, height=height)

    n_words = sum(1 for n in g.nodes() if g.nodes[n].get('node_type') == 'word')
    n_codes_shown = g.number_of_nodes() - n_words
    st.caption(f'単語ノード: {n_words} / コードノード: {n_codes_shown} / エッジ数: {g.number_of_edges()} / 文書数: {len(doc_tokens)}')


def _render_code_clustering(doc_tokens: list, code_doc_sets: dict[str, set[int]],
                             included_categories: set, stopwords: set[str] | None) -> None:
    """コードのクラスター分析。関係性寄りの分析とみなし、既定で通常の語も含める。"""
    st.markdown('##### コードのクラスター分析')

    nonzero = {name: s for name, s in code_doc_sets.items() if s}
    excluded = len(code_doc_sets) - len(nonzero)
    if excluded:
        st.caption(f'{excluded}件のコードは該当文書が無いため、クラスター分析から除外しています。')

    include_words = st.checkbox('語も含める', value=True, key='coding_cluster_include_words')

    with st.expander('表示設定', expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            word_top_n = st.slider('語の対象数（文書頻度上位）', min_value=5, max_value=100, value=30, step=5,
                                    key='coding_cluster_word_top_n', disabled=not include_words)
        with col2:
            n_clusters = st.slider('クラスタ数（色分け目安）', min_value=1, max_value=15, value=4,
                                    key='coding_cluster_n')
        with col3:
            label_fontsize = st.slider('文字サイズ', min_value=6, max_value=20, value=10,
                                        key='coding_cluster_fontsize')

    labels, matrix = code_doc_matrix(nonzero, len(doc_tokens))
    if include_words:
        word_labels, word_matrix = build_word_doc_matrix(
            doc_tokens, included_categories, min_doc_freq=2, top_n=word_top_n, stopwords=stopwords)
        if word_labels:
            labels = labels + word_labels
            matrix = np.vstack([matrix, word_matrix])

    if len(labels) < 2:
        st.warning('クラスタリング対象が不足しています（該当文書のあるコード・語が2件未満です）。')
        return

    linkage_matrix = compute_linkage(matrix)
    fig = render_dendrogram(labels, linkage_matrix, n_clusters=n_clusters, label_fontsize=label_fontsize)
    st.pyplot(fig)
    st.caption(f'対象数: {len(labels)}（コード{len(nonzero)}件 + 語{len(labels) - len(nonzero)}件） / 文書数: {len(doc_tokens)}')

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        dpi = st.selectbox('PNG解像度（DPI）', DPI_OPTIONS, index=1, key='coding_cluster_dpi')
        st.download_button(
            '💾 PNGでダウンロード', data=figure_to_png_bytes(fig, dpi=dpi),
            file_name='coding_dendrogram.png', mime='image/png', key='coding_cluster_png_dl',
        )
    with col_dl2:
        st.caption('ベクター形式（Illustrator等で編集可能）')
        st.download_button(
            '💾 SVGでダウンロード', data=figure_to_svg_bytes(fig),
            file_name='coding_dendrogram.svg', mime='image/svg+xml', key='coding_cluster_svg_dl',
        )
