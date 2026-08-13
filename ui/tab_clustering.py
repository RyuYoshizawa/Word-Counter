"""
tab_clustering.py
クラスター分析タブ：語×文書の出現有無からWard法＋Jaccard距離で階層的クラスタリングを行い、
デンドログラムを表示する。文字サイズ調整、PNG（解像度指定）/SVG（ベクター）ダウンロードに対応。
"""

import streamlit as st

from core.clustering import (
    build_word_doc_matrix,
    compute_linkage,
    figure_to_png_bytes,
    figure_to_svg_bytes,
    render_dendrogram,
)
from ui.common import pos_filter_caption

DPI_OPTIONS = [150, 300, 600]


def render(doc_tokens: list, included_categories: set, stopwords: set[str] | None = None) -> None:
    st.subheader('クラスター分析')
    st.caption('語×文書の出現有無からJaccard距離を計算し、Ward法で階層的クラスタリングを行います。')

    if not doc_tokens:
        st.info('データ準備タブでテキストを読み込んでください（1行＝1文書として集計します）。')
        return

    st.caption(pos_filter_caption(included_categories))

    with st.expander('表示設定', expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            min_doc_freq = st.number_input('最低出現文書数', min_value=1, value=2, step=1, key='cluster_min_doc_freq')
        with col2:
            top_n = st.slider('対象語数（文書頻度上位）', min_value=5, max_value=100, value=40, step=5, key='cluster_top_n')
        with col3:
            n_clusters = st.slider('クラスタ数（色分け目安）', min_value=1, max_value=15, value=4, key='cluster_n')
        label_fontsize = st.slider('文字サイズ', min_value=6, max_value=20, value=10, key='cluster_fontsize')

    words, matrix = build_word_doc_matrix(doc_tokens, included_categories, min_doc_freq=min_doc_freq,
                                           top_n=top_n, stopwords=stopwords)

    if len(words) < 2:
        st.warning('クラスタリング対象の語が不足しています。最低出現文書数や品詞フィルタを見直してください。')
        return

    linkage_matrix = compute_linkage(matrix)
    fig = render_dendrogram(words, linkage_matrix, n_clusters=n_clusters, label_fontsize=label_fontsize)
    st.pyplot(fig)
    st.caption(f'対象語数: {len(words)} / 文書数: {len(doc_tokens)}')

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        dpi = st.selectbox('PNG解像度（DPI）', DPI_OPTIONS, index=1)
        st.download_button(
            '💾 PNGでダウンロード', data=figure_to_png_bytes(fig, dpi=dpi),
            file_name='dendrogram.png', mime='image/png',
        )
    with col_dl2:
        st.caption('ベクター形式（Illustrator等で編集可能）')
        st.download_button(
            '💾 SVGでダウンロード', data=figure_to_svg_bytes(fig),
            file_name='dendrogram.svg', mime='image/svg+xml',
        )
