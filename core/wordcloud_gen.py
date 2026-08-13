"""
wordcloud_gen.py
単語頻度表からワードクラウド画像を生成する。マスク形状・品詞別/ネガポジ色分け・
太字表示・高解像度出力に対応する。
"""

from typing import Callable

from wordcloud import WordCloud

from .fonts import resolve_bold_japanese_font
from .mask_shapes import generate_mask
from .sentiment import lookup_polarity

# After Coderと共有するグラフカラーパレット（10色）
CHART_COLORS = ['0068C9', '83C9FF', 'FF2B2B', 'FFABAB', '29B09D',
                 '7DEFA1', 'FF8700', 'FFD16A', '6D3FC0', 'D5DAE5']


def generate_wordcloud(freq: dict[str, int], width: int = 900, height: int = 500,
                        mask_shape: str | None = None, color_func: Callable | None = None,
                        bold: bool = True, scale: float = 1.0) -> WordCloud:
    """
    {語: 出現回数} からWordCloudオブジェクトを生成する。
    mask_shape指定時はその形状の輪郭に緩くフィットさせる。color_func未指定時は既定配色。
    scaleは高解像度出力用の倍率（画像サイズ・解像度をscale倍にする）。
    """
    font_path = resolve_bold_japanese_font() if bold else None
    if font_path is None:
        from .fonts import resolve_japanese_font
        font_path = resolve_japanese_font()

    kwargs = dict(
        font_path=font_path,
        width=width,
        height=height,
        background_color='white',
        prefer_horizontal=1.0,  # 縦書きを禁止し横書きに統一する
        scale=scale,
    )
    if mask_shape:
        # マスク使用時はwordcloud側がmaskのサイズに合わせて描画するため、width/heightは無視される
        kwargs['mask'] = generate_mask(mask_shape, size=max(width, height))
        del kwargs['width']
        del kwargs['height']
    if color_func:
        kwargs['color_func'] = color_func

    wc = WordCloud(**kwargs)
    wc.generate_from_frequencies(freq)
    return wc


def make_pos_color_func(word_categories: dict[str, str], category_colors: dict[str, str]) -> Callable:
    """
    品詞別4色塗分け用のcolor_funcを作る。word_categoriesは{語: 品詞カテゴリ}、
    category_colorsは{品詞カテゴリ: '#RRGGBB'}（未割当のカテゴリはグレー既定色）。
    """
    default_color = '#999999'

    def _color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        cat = word_categories.get(word)
        return category_colors.get(cat, default_color)

    return _color_func


def make_sentiment_color_func(neg_threshold: float, pos_threshold: float) -> Callable:
    """
    モノクロ3段階ネガポジ色分け用のcolor_func（実験的機能）。
    pn_ja.dicの極性値をしきい値で3区分し、ポジ=グレー・ネガ=ブラック・ニュートラル=ライトグレー。
    辞書に無い語もニュートラル扱いにする。
    """
    def _color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        score = lookup_polarity(word)
        if score is None:
            return '#BBBBBB'
        if score >= pos_threshold:
            return '#808080'
        if score <= neg_threshold:
            return '#000000'
        return '#BBBBBB'

    return _color_func


def to_png_bytes(wc: WordCloud) -> bytes:
    """WordCloudオブジェクトをPNGバイト列に変換する（ダウンロード用）"""
    import io
    buf = io.BytesIO()
    wc.to_image().save(buf, format='PNG')
    return buf.getvalue()
