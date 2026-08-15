"""
tab_wordcloud.py
ワードクラウドタブ。マスク形状（雲のような輪郭）、品詞別4色塗分け／モノクロ3段階
ネガポジ（実験）、太字、高解像度ダウンロードに対応する。
"""

import streamlit as st

from core.fonts import resolve_japanese_font
from core.frequency import word_category_map, word_frequency_table
from core.mask_shapes import MASK_SHAPES
from core.pos_rules import CATEGORY_ORDER
from core.wordcloud_gen import (
    CHART_COLORS,
    DEFAULT_PALETTES,
    PALETTE_LABELS,
    generate_wordcloud,
    make_multicolor_color_func,
    make_pos_color_func,
    make_sentiment_color_func,
    to_png_bytes,
)
from ui.common import pos_filter_caption

COLOR_MODES = ['品詞別4色', '多色ランダム', 'モノクロ3段階ネガポジ（実験）']
RESOLUTION_OPTIONS = {'標準': 1.0, '高解像度（2倍）': 2.0, '最高解像度（4倍）': 4.0}
_POS_ASSIGNABLE_CATEGORIES = [c for c in CATEGORY_ORDER if c not in {'その他'}]
_DEFAULT_SLOT_CATEGORIES = ['名詞', '動詞', '形容詞', '固有名詞']


def render(tokens: list, included_categories: set, stopwords: set[str] | None = None) -> None:
    st.subheader('ワードクラウド')

    if not tokens:
        st.info('データ準備タブでテキストを読み込んでください。')
        return

    st.caption(pos_filter_caption(included_categories))

    if resolve_japanese_font() is None:
        st.error('日本語フォントが見つかりませんでした。日本語が文字化けする可能性があります。')

    max_words = st.slider('最大語数', min_value=20, max_value=300, value=100, step=10)
    mask_choice = st.selectbox('マスク形状', ['なし'] + MASK_SHAPES)
    font_weight = st.slider(
        '文字の太さ（ウェイト）', min_value=100, max_value=900, value=600, step=50,
        help='400が標準的な太さ、700がBold相当。Noto Sans JPが可変フォントであることを'
             '活かし、100（極細）〜900（極太）まで自由に調整できる。',
    )
    color_mode = st.selectbox('色分けモード', COLOR_MODES)

    col_size, col_curve = st.columns(2)
    with col_size:
        max_font_size_ratio = st.slider(
            '最大文字サイズ', min_value=0.15, max_value=0.6, value=0.32, step=0.01,
            help='最も頻度が高い語の文字サイズ（表示エリアの高さに対する比率）。',
        )
    with col_curve:
        relative_scaling = st.slider(
            '文字サイズのメリハリ', min_value=0.0, max_value=1.0, value=0.4, step=0.05,
            help='0に近いほど頻度差が均され語ごとの大きさが揃う。1に近いほど頻度差がそのまま'
                 'サイズ差になり、最頻語が際立つ。',
        )

    if color_mode == '品詞別4色':
        color_func = _render_pos_color_controls(tokens, included_categories, stopwords)
    elif color_mode == '多色ランダム':
        color_func = _render_multicolor_color_controls()
    else:
        color_func = _render_sentiment_color_controls()

    word_df = word_frequency_table(tokens, included_categories, stopwords)
    if word_df.empty:
        st.warning('対象となる語がありません。品詞フィルタを見直してください。')
        return

    freq = dict(zip(word_df['語'].head(max_words), word_df['出現回数'].head(max_words)))
    mask_shape = None if mask_choice == 'なし' else mask_choice
    wc = generate_wordcloud(freq, mask_shape=mask_shape, color_func=color_func, font_weight=font_weight,
                             max_font_size_ratio=max_font_size_ratio, relative_scaling=relative_scaling)
    st.image(wc.to_array(), use_container_width=True)

    resolution_label = st.selectbox('ダウンロード解像度', list(RESOLUTION_OPTIONS.keys()))
    if st.button('PNGを生成してダウンロード'):
        scale = RESOLUTION_OPTIONS[resolution_label]
        wc_hires = generate_wordcloud(freq, mask_shape=mask_shape, color_func=color_func, font_weight=font_weight,
                                       scale=scale, max_font_size_ratio=max_font_size_ratio,
                                       relative_scaling=relative_scaling)
        png_bytes = to_png_bytes(wc_hires)
        st.download_button('💾 ダウンロード', data=png_bytes, file_name='wordcloud.png', mime='image/png')


def _render_color_legend() -> None:
    """10色パレットを番号付きで一覧表示する（色選択の参照用のスウォッチ）"""
    cols = st.columns(len(CHART_COLORS))
    for i, (col, hex_code) in enumerate(zip(cols, CHART_COLORS), start=1):
        with col:
            st.markdown(
                f'<div style="width:100%;height:28px;background-color:#{hex_code};'
                f'border-radius:4px;border:1px solid #999;"></div>'
                f'<div style="text-align:center;font-size:12px;">{i}</div>',
                unsafe_allow_html=True,
            )


def _render_pos_color_controls(tokens: list, included_categories: set,
                                stopwords: set[str] | None = None) -> callable:
    """品詞別4色塗分け：色見本の番号で4色を選び、それぞれに複数の品詞カテゴリを割り当てる"""
    st.caption('下の色見本の番号を参考に、4つの色を選んでください。各色には複数の品詞を割り当てられます。')
    _render_color_legend()

    category_colors: dict[str, str] = {}
    cols = st.columns(4)
    for i, col in enumerate(cols):
        with col:
            color_num = st.selectbox(
                f'色{i + 1}（番号）', list(range(1, len(CHART_COLORS) + 1)),
                index=min(i, len(CHART_COLORS) - 1), key=f'wc_color_num_{i}',
            )
            default_cats = [_DEFAULT_SLOT_CATEGORIES[i]] if i < len(_DEFAULT_SLOT_CATEGORIES) else []
            cats = st.multiselect(
                f'品詞{i + 1}（複数選択可）', _POS_ASSIGNABLE_CATEGORIES,
                default=default_cats, key=f'wc_cats_{i}',
            )
            color_hex = CHART_COLORS[color_num - 1]
            for cat in cats:
                category_colors[cat] = f'#{color_hex}'

    word_categories = word_category_map(tokens, included_categories, stopwords)
    return make_pos_color_func(word_categories, category_colors)


def _render_multicolor_color_controls() -> callable:
    """
    多色ランダム配色：3つまでの10色パレットを切り替えて使える。各パレットの色は
    st.color_pickerで自由に編集・保存でき（session_stateに保持、次のワードクラウド生成に
    即反映）、パレット1の初期値は既定のCHART_COLORS。
    """
    st.caption('品詞やカテゴリに関係なく、選んだパレットから語ごとにランダムに配色します。')
    palettes = st.session_state.setdefault('wc_palettes', [list(p) for p in DEFAULT_PALETTES])

    palette_idx = st.selectbox(
        '使用するパレット', list(range(len(palettes))), format_func=lambda i: PALETTE_LABELS[i],
    )

    with st.expander('パレットの色を編集', expanded=False):
        tabs = st.tabs(PALETTE_LABELS)
        for p_idx, tab in enumerate(tabs):
            with tab:
                cols = st.columns(10)
                for i, col in enumerate(cols):
                    with col:
                        color = st.color_picker(
                            f'色{i + 1}', value=f'#{palettes[p_idx][i]}',
                            key=f'wc_palette_{p_idx}_{i}', label_visibility='collapsed',
                        )
                        palettes[p_idx][i] = color.lstrip('#').upper()

    return make_multicolor_color_func(palettes[palette_idx])


def _render_sentiment_color_controls() -> callable:
    """モノクロ3段階ネガポジ（実験的機能）：pn_ja.dicの極性値をしきい値で3区分する"""
    st.caption(
        '単語感情極性対応表（pn_ja.dic）による実験的機能です。ポジ＝グレー、ネガ＝ブラック、'
        'ニュートラル（辞書に無い語を含む）＝ライトグレーで表示します。'
    )
    col1, col2 = st.columns(2)
    with col1:
        pos_threshold = st.slider('ポジティブしきい値', min_value=0.0, max_value=1.0, value=0.3, step=0.05)
    with col2:
        neg_threshold = st.slider('ネガティブしきい値', min_value=-1.0, max_value=0.0, value=-0.3, step=0.05)
    return make_sentiment_color_func(neg_threshold=neg_threshold, pos_threshold=pos_threshold)
