"""
sentiment.py
単語感情極性対応表（高村ら, pn_ja.dic）による単語単位のネガポジ判定。
ワードクラウドのモノクロ3段階表示（実験的機能）で使用する。
"""

from functools import lru_cache
from pathlib import Path

_DIC_PATH = Path(__file__).parent.parent / 'data' / 'pn_ja.dic'


@lru_cache(maxsize=1)
def load_polarity_dict() -> dict[str, float]:
    """
    pn_ja.dic（表層形:読み:品詞:極性値、cp932）を読み込み {表層形: 極性値[-1, 1]} を返す。
    同じ表層形が複数回出現する場合は最初に出てきたものを優先する。
    """
    polarity: dict[str, float] = {}
    if not _DIC_PATH.exists():
        return polarity
    with open(_DIC_PATH, encoding='cp932') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) != 4:
                continue
            surface, _reading, _pos, score = parts
            if surface in polarity:
                continue
            try:
                polarity[surface] = float(score)
            except ValueError:
                continue
    return polarity


def lookup_polarity(word: str) -> float | None:
    """指定した語の極性値（-1〜1）を返す。辞書に無ければNone"""
    return load_polarity_dict().get(word)
