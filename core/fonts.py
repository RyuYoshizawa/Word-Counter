"""
fonts.py
日本語フォントの解決。wordcloud・matplotlib（クラスター分析のデンドログラム）で共有する。
Windows標準搭載フォントを実行時に解決し、フォントファイルの同梱・ダウンロードは行わない。
"""

import tempfile
from pathlib import Path

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\NotoSansJP-VF.ttf"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\msgothic.ttc"),
]

_BOLD_SIBLINGS = {
    r"C:\Windows\Fonts\meiryo.ttc": r"C:\Windows\Fonts\meiryob.ttc",
}

# 700（Bold）は太すぎるとの実使用フィードバックを受けて600（SemiBold相当）に調整。
# ウェイト値をキャッシュファイル名に含めることで、将来値を変えた際に古いキャッシュを
# 誤って使い回さないようにする。
_BOLD_WEIGHT = 600
_BOLD_CACHE_PATH = Path(tempfile.gettempdir()) / f'word_counter_ja_bold_{_BOLD_WEIGHT}.ttf'


def resolve_japanese_font() -> str | None:
    """利用可能な日本語フォントのパスを返す。見つからなければNone"""
    for path in _FONT_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def resolve_bold_japanese_font() -> str | None:
    """
    太字表示用の日本語フォントパスを返す（ワードクラウドの「文字を太く」要望用）。
    可変フォント（NotoSansJP-VF.ttf）は fontTools で weight=_BOLD_WEIGHT の静的インスタンスを
    生成しキャッシュして使う（wordcloudは font_path を都度読み込むため、可変フォントの
    実行時ウェイト切り替えは効かず、静的ファイルに変換する必要がある）。
    非可変フォントの場合は隣接するBold版ファイル（例: meiryob.ttc）があればそれを使う。
    失敗時は通常の太さのフォントにフォールバックする。
    """
    base = resolve_japanese_font()
    if base is None:
        return None

    if base in _BOLD_SIBLINGS and Path(_BOLD_SIBLINGS[base]).exists():
        return _BOLD_SIBLINGS[base]

    if _BOLD_CACHE_PATH.exists():
        return str(_BOLD_CACHE_PATH)

    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer

        font = TTFont(base)
        if 'fvar' not in font:
            return base
        instantiated = instancer.instantiateVariableFont(font, {'wght': _BOLD_WEIGHT})
        instantiated.save(str(_BOLD_CACHE_PATH))
        return str(_BOLD_CACHE_PATH)
    except Exception:
        return base
