"""
clustering.py
クラスター分析：語×文書の出現有無行列からJaccard距離を計算し、
Ward法で階層的クラスタリングを行う（KH Coderと同じ組み合わせ）。
"""

import matplotlib
matplotlib.use('Agg')  # Streamlit（headless）環境向けの非対話バックエンド

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import pdist

from .fonts import resolve_japanese_font
from .pos_rules import map_pos
from .tokenizer import Token

# matplotlibの既定フォント（DejaVu Sans）は日本語グリフを持たないため、
# ワードクラウドと同じWindows標準搭載フォントを明示的に登録する。
_JP_FONT_PATH = resolve_japanese_font()
if _JP_FONT_PATH:
    fm.fontManager.addfont(_JP_FONT_PATH)
    _JP_FONT_NAME = fm.FontProperties(fname=_JP_FONT_PATH).get_name()
    plt.rcParams['font.family'] = _JP_FONT_NAME
    plt.rcParams['axes.unicode_minus'] = False


def build_word_doc_matrix(doc_tokens: list[list[Token]], included_categories: set[str] | None,
                            min_doc_freq: int = 2, top_n: int = 40,
                            stopwords: set[str] | None = None) -> tuple[list[str], np.ndarray]:
    """
    語×文書の出現有無（0/1）行列を構築する。文書頻度上位top_n語に絞り込む。
    戻り値: (words: 対象語のリスト, matrix: shape=(len(words), len(doc_tokens))のbool行列)
    """
    doc_word_sets = []
    for tokens in doc_tokens:
        words = set()
        for t in tokens:
            cat = map_pos(t)
            if included_categories is not None and cat not in included_categories:
                continue
            if stopwords and t.normalized in stopwords:
                continue
            words.add(t.normalized)
        doc_word_sets.append(words)

    doc_freq: dict[str, int] = {}
    for words in doc_word_sets:
        for w in words:
            doc_freq[w] = doc_freq.get(w, 0) + 1

    candidates = [w for w, f in doc_freq.items() if f >= min_doc_freq]
    candidates.sort(key=lambda w: doc_freq[w], reverse=True)
    candidates = candidates[:top_n]

    matrix = np.zeros((len(candidates), len(doc_tokens)), dtype=bool)
    for i, w in enumerate(candidates):
        for j, words in enumerate(doc_word_sets):
            matrix[i, j] = w in words

    return candidates, matrix


def compute_linkage(matrix: np.ndarray, method: str = 'ward') -> np.ndarray:
    """
    Jaccard距離＋Ward法で階層的クラスタリングを行う。
    Ward法は本来ユークリッド距離を前提とするが、KH Coderもこの組み合わせ（Ward+Jaccard）を
    選択可能にしており、本ツールも同じ組み合わせを既定として踏襲する
    （厳密な統計的最適性よりKH Coderとの再現性を優先する設計判断）。
    """
    if matrix.shape[0] < 2:
        raise ValueError('クラスタリングには2語以上が必要です')
    distances = pdist(matrix, metric='jaccard')
    return linkage(distances, method=method)


def render_dendrogram(words: list[str], linkage_matrix: np.ndarray, n_clusters: int | None = None,
                       label_fontsize: int = 10):
    """デンドログラムをmatplotlibの図として返す（st.pyplotで表示する想定）"""
    fig, ax = plt.subplots(figsize=(8, max(3, len(words) * 0.28)))

    color_threshold = None
    if n_clusters and n_clusters > 1:
        heights = np.sort(linkage_matrix[:, 2])
        idx = len(heights) - (n_clusters - 1)
        if 0 <= idx < len(heights):
            color_threshold = heights[idx]

    dendrogram(linkage_matrix, labels=words, orientation='right', ax=ax, color_threshold=color_threshold,
               leaf_font_size=label_fontsize)
    ax.set_xlabel('距離（Jaccard × Ward法）')
    fig.tight_layout()
    return fig


def figure_to_png_bytes(fig, dpi: int = 300) -> bytes:
    """図をPNGバイト列に変換する（ダウンロード用、解像度指定可）"""
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    return buf.getvalue()


def figure_to_svg_bytes(fig) -> bytes:
    """図をSVGバイト列に変換する（ベクター形式、Illustrator等で編集可能）"""
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format='svg', bbox_inches='tight')
    return buf.getvalue()
