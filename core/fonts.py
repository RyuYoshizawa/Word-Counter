"""
fonts.py
日本語フォントの解決。wordcloud・matplotlib（クラスター分析のデンドログラム）で共有する。
Noto Sans JP（SIL Open Font License、再配布可）を`data/fonts/`に同梱し最優先で使う——
Streamlit Community Cloud等のLinux環境にはWindows標準フォントが存在しないため、OS非依存の
同梱フォントを主とし、Windows標準搭載フォントは同梱ファイルが無い場合の保険として残す。
"""

import tempfile
from pathlib import Path

_BUNDLED_FONT_PATH = Path(__file__).resolve().parent.parent / 'data' / 'fonts' / 'NotoSansJP-VF.ttf'

_FONT_CANDIDATES = [
    _BUNDLED_FONT_PATH,
    Path(r"C:\Windows\Fonts\NotoSansJP-VF.ttf"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\msgothic.ttc"),
]

_BOLD_SIBLINGS = {
    r"C:\Windows\Fonts\meiryo.ttc": r"C:\Windows\Fonts\meiryob.ttc",
}

# NotoSansJP-VFのwghtスケール（Thin=100〜Black=900、OpenTypeの標準ウェイト値）を
# そのままスライダーの値として使う。非可変フォント（meiryo.ttc等）でBold版を使うか
# どうかの閾値にも流用する。
_WEIGHT_BOLD_THRESHOLD = 600


def resolve_japanese_font() -> str | None:
    """利用可能な日本語フォントのパスを返す。見つからなければNone"""
    for path in _FONT_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def resolve_weighted_japanese_font(weight: int) -> str | None:
    """
    指定ウェイト（100〜900、OpenTypeのwght値）の日本語フォントパスを返す
    （ワードクラウドの「文字の太さ」スライダー用）。
    可変フォント（NotoSansJP-VF.ttf）は fontTools でweight値の静的インスタンスを
    生成しウェイトごとにキャッシュして使う（wordcloudは font_path を都度読み込むため、
    可変フォントの実行時ウェイト切り替えは効かず、静的ファイルに変換する必要がある）。
    非可変フォントの場合はweightが_WEIGHT_BOLD_THRESHOLD以上なら隣接するBold版ファイル
    （例: meiryob.ttc）があればそれを使い、それ未満は通常のフォントを返す
    （非可変フォントは中間的なウェイトを持たないため、二値での近似にとどまる）。
    失敗時は通常の太さのフォントにフォールバックする。
    """
    base = resolve_japanese_font()
    if base is None:
        return None

    if base in _BOLD_SIBLINGS:
        if weight >= _WEIGHT_BOLD_THRESHOLD and Path(_BOLD_SIBLINGS[base]).exists():
            return _BOLD_SIBLINGS[base]
        return base

    cache_path = Path(tempfile.gettempdir()) / f'word_counter_ja_w{weight}.ttf'
    if cache_path.exists():
        return str(cache_path)

    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer

        font = TTFont(base)
        if 'fvar' not in font:
            return base
        # instancerは軸の実際の最小/最大値に自動でクランプするため、フォントの
        # 実際のwght軸範囲がNoto Sans JPの想定（100-900）と異なっていても安全。
        instantiated = instancer.instantiateVariableFont(font, {'wght': weight})
        instantiated.save(str(cache_path))
        return str(cache_path)
    except Exception:
        return base
