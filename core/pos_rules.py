"""
pos_rules.py
Sudachiの品詞タグをKH Coder風のカテゴリにマッピングする。
ひらがなのみの語（名詞/動詞/形容詞）は「too general」として一括除外しやすいよう
「-B」区分に分け、既定で除外対象とする（KH Coderの設計を踏襲）。
"""

import re
from .tokenizer import FORCED_POS_MAJOR, Token

_HIRAGANA_ONLY = re.compile(r'^[ぁ-ゖー]+$')

# 表示順（サイドバーのチェックボックス順にも使う）
CATEGORY_ORDER = [
    '強制抽出',
    '名詞', '固有名詞', 'サ変名詞', '名詞B',
    '動詞', '動詞B',
    '形容詞', '形容詞B', '形状詞（ナ形容詞）',
    '副詞', '感動詞', '否定助動詞',
    'その他',
]

# 既定でチェックを入れる（＝分析対象に含める）カテゴリ
DEFAULT_INCLUDED_CATEGORIES = {
    '強制抽出',
    '名詞', '固有名詞', 'サ変名詞',
    '動詞',
    '形容詞', '形状詞（ナ形容詞）',
    '副詞', '感動詞', '否定助動詞',
}

_NEGATIVE_AUX_FORMS = {'ない', 'ぬ', 'ん'}


def _is_hiragana_only(s: str) -> bool:
    return bool(_HIRAGANA_ONLY.match(s))


def map_pos(token: Token) -> str:
    """SudachiのTokenをKH Coder風のカテゴリ名にマッピングする"""
    major = token.pos_major
    sub1 = token.pos_tags[1] if len(token.pos_tags) > 1 else ''

    if major == FORCED_POS_MAJOR:
        return FORCED_POS_MAJOR

    if major == '名詞':
        if sub1 == '固有名詞':
            return '固有名詞'
        if sub1 == 'サ変可能':
            return 'サ変名詞'
        return '名詞B' if _is_hiragana_only(token.surface) else '名詞'

    if major == '動詞':
        return '動詞B' if _is_hiragana_only(token.surface) else '動詞'

    if major == '形容詞':
        return '形容詞B' if _is_hiragana_only(token.surface) else '形容詞'

    if major == '形状詞':
        return '形状詞（ナ形容詞）'

    if major == '副詞':
        return '副詞'

    if major == '感動詞':
        return '感動詞'

    if major == '助動詞' and token.normalized in _NEGATIVE_AUX_FORMS:
        return '否定助動詞'

    # 助詞・助動詞（否定以外）・記号・補助記号・接続詞・連体詞・空白など
    return 'その他'


def display_category(token: Token) -> str:
    """
    表示用のカテゴリ名を返す。複合語トークンは基本品詞（名詞/動詞など）にかかわらず
    一律「（複）」表記に統一する（品詞フィルタの判定自体はmap_pos()の基本カテゴリで行うため、
    複合語も対応する基本カテゴリのチェックボックスでON/OFFされる——表示ラベルのみの変更）。
    """
    return '（複）' if token.is_compound else map_pos(token)
