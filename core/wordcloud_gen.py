"""
wordcloud_gen.py
単語頻度表からワードクラウド画像を生成する。マスク形状・品詞別/ネガポジ色分け・
太字表示・高解像度出力に対応する。
"""

import html
import random
from typing import Callable

from wordcloud import WordCloud

from .fonts import resolve_weighted_japanese_font
from .mask_shapes import generate_mask
from .sentiment import lookup_polarity

# After Coderと共有するグラフカラーパレット（10色）
CHART_COLORS = ['0068C9', '83C9FF', 'FF2B2B', 'FFABAB', '29B09D',
                 '7DEFA1', 'FF8700', 'FFD16A', '6D3FC0', 'D5DAE5']

# 「多色ランダム」用に選べる3種の10色パレット（初期値、ユーザーがUI上で自由に編集できる）。
# パレット1は既定色（CHART_COLORS）をそのまま初期値にし、2・3は編集の出発点となる
# 別テイストの案（パステル・ビビッド）を用意した。
DEFAULT_PALETTES = [
    list(CHART_COLORS),
    ['FFB3BA', 'FFDFBA', 'FFFFBA', 'BAFFC9', 'BAE1FF', 'D4BAFF', 'FFBAF0', 'C9C9FF', 'B3FFD9', 'FFE4B3'],
    ['E63946', 'F4A261', '2A9D8F', '264653', 'E76F51', '8338EC', 'FB5607', '3A86FF', 'FFBE0B', '06D6A0'],
]
PALETTE_LABELS = ['パレット1', 'パレット2', 'パレット3']


def generate_wordcloud(freq: dict[str, int], width: int = 900, height: int = 500,
                        mask_shape: str | None = None, color_func: Callable | None = None,
                        font_weight: int = 600, scale: float = 1.0,
                        max_font_size_ratio: float = 0.32, relative_scaling: float = 0.4) -> WordCloud:
    """
    {語: 出現回数} からWordCloudオブジェクトを生成する。
    mask_shape指定時はその形状の輪郭に緩くフィットさせる。color_func未指定時は既定配色。
    scaleは高解像度出力用の倍率（画像サイズ・解像度をscale倍にする）。
    font_weightは文字の太さ（OpenTypeのwght値、100〜900）。NotoSansJP-VFが可変フォント
    であることを活かし、Bold/Regularの二値ではなく任意のウェイトを指定できる。
    max_font_size_ratioは最大フォントサイズのheightに対する比率（実データで最頻語が
    突出しすぎるとの指摘を受け、既定はNone＝上位2語から自動算出ではなく明示上限にした）。
    relative_scalingは最大〜最小フォントサイズのカーブ——0に近いほど頻度差を無視した
    ランク基準（差が均される）、1に近いほど頻度に比例（差が強調される）。
    """
    font_path = resolve_weighted_japanese_font(font_weight)

    kwargs = dict(
        font_path=font_path,
        width=width,
        height=height,
        background_color='white',
        prefer_horizontal=1.0,  # 縦書きを禁止し横書きに統一する
        scale=scale,
        relative_scaling=relative_scaling,
        margin=4,  # 語同士の間隔を広めにし、詰まった印象を避ける（既定2px）
        max_font_size=int(height * max_font_size_ratio),
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


def make_multicolor_color_func(palette: list[str] | None = None) -> Callable:
    """
    多色ランダム配色用のcolor_func。品詞やカテゴリに関係なく、指定パレット（10色、'#'無し
    16進表記）から語ごとにランダムに色を割り当てる（見本画像のような、彩り豊かで賑やかな
    配色を再現する）。palette未指定時は既定のCHART_COLORSを使う。
    """
    colors = palette if palette else CHART_COLORS

    def _color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        idx = (random_state or random).randint(0, len(colors) - 1)
        return f'#{colors[idx]}'

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


def to_svg_outlined(wc: WordCloud) -> str:
    """
    WordCloudのレイアウト結果を、文字をアウトライン（パス）化したSVG文字列にする。
    WordCloud.to_svg()は文字を<text>のままフォント名で参照するため、フォントが無い環境
    （PowerPoint・Illustrator等）で別フォントに置き換わり字形・位置がずれる——ここでは
    fontToolsでグリフの輪郭を直接取り出して<path>にするので、フォント無しで同じ見た目になる
    （代わりに文字としては編集できない）。座標はto_image()の貼り付け位置と一致するよう
    求める（下記コメント参照）。横書きのみ対応（generate_wordcloudが
    prefer_horizontal=1.0で縦書きを禁止しているため）。字間はhmtxの送り幅のみ（カーニング無し）。
    """
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    from PIL import ImageFont

    if wc.mask is not None:
        height, width = wc.mask.shape[:2]
    else:
        height, width = wc.height, wc.width
    scale = wc.scale

    font = TTFont(wc.font_path, fontNumber=0)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    units_per_em = font['head'].unitsPerEm

    def ntos(v: float) -> str:
        return f'{v:.2f}'.rstrip('0').rstrip('.')

    out_w, out_h = ntos(width * scale), ntos(height * scale)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{out_w}" height="{out_h}" '
        f'viewBox="0 0 {out_w} {out_h}">'
    ]
    if wc.background_color is not None:
        parts.append(f'<rect width="{out_w}" height="{out_h}" fill="{html.escape(wc.background_color)}"/>')

    for (word, _count), font_size, (row, col), _orientation, color in wc.layout_:
        size = int(font_size * scale)
        px_per_unit = size / units_per_em
        pil_font = ImageFont.truetype(wc.font_path, size)
        ascent = pil_font.getmetrics()[0]
        # to_image()はTransposedFont経由でアンカーが効かず、語ごとのマスク（getbbox()の
        # 左上=語の外接矩形の左上）を(col, row)に貼る——そのため原点・ベースラインは
        # 貼り付け位置からbboxのオフセット分を引いて求める（WordCloud.to_svg()と同じ式）。
        bbox_left, bbox_top = pil_font.getbbox(word)[:2]
        pen_x = col * scale - bbox_left
        baseline_y = row * scale + ascent - bbox_top

        pen = SVGPathPen(glyph_set, ntos=ntos)
        for ch in word:
            name = cmap.get(ord(ch), '.notdef')
            if name not in glyph_set:
                continue
            glyph = glyph_set[name]
            glyph.draw(TransformPen(pen, (px_per_unit, 0, 0, -px_per_unit, pen_x, baseline_y)))
            pen_x += glyph.width * px_per_unit

        commands = pen.getCommands()
        if commands:
            parts.append(f'<path fill="{html.escape(color)}" d="{commands}"/>')

    parts.append('</svg>')
    return '\n'.join(parts)


def to_png_bytes(wc: WordCloud) -> bytes:
    """WordCloudオブジェクトをPNGバイト列に変換する（ダウンロード用）"""
    import io
    buf = io.BytesIO()
    wc.to_image().save(buf, format='PNG')
    return buf.getvalue()
