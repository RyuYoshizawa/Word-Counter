"""
tokenizer.py
Sudachiラッパー。Mode A/Cでのトークナイズと、強制抽出の文字列保護/復元を担う。
"""

from dataclasses import dataclass
from functools import lru_cache

from sudachipy import dictionary, tokenizer as sudachi_tokenizer

SPLIT_MODE_A = sudachi_tokenizer.Tokenizer.SplitMode.A
SPLIT_MODE_C = sudachi_tokenizer.Tokenizer.SplitMode.C

# SudachiPyは1回のtokenize()呼び出しにつき入力バイト数の上限（約49149バイト、UTF-8換算）を
# 持ち、超えると SudachiError で例外になる。安全マージンを取って45000バイトを上限とし、
# 超える場合は文字単位で分割して複数回に分けてトークナイズする。
_MAX_SUDACHI_BYTES = 45000


def _chunk_text_for_sudachi(text: str, max_bytes: int = _MAX_SUDACHI_BYTES) -> list[str]:
    """SudachiPyの入力バイト数上限を超えないよう、テキストを文字単位で分割する"""
    if len(text.encode('utf-8')) <= max_bytes:
        return [text]
    chunks = []
    current: list[str] = []
    current_bytes = 0
    for ch in text:
        ch_bytes = len(ch.encode('utf-8'))
        if current_bytes + ch_bytes > max_bytes and current:
            chunks.append(''.join(current))
            current = []
            current_bytes = 0
        current.append(ch)
        current_bytes += ch_bytes
    if current:
        chunks.append(''.join(current))
    return chunks


@dataclass
class Token:
    surface: str            # 表層形
    normalized: str          # 見出し語（dictionary_form）。activeな正規化形として使う。
                              # normalized_form()は「とても→迚も」のような常用外の漢字表記に
                              # 変換することがあり単語頻度の表示には不向きなため使わない。
    pos_major: str            # 品詞大分類（名詞/動詞など、Sudachiタグそのまま）
    pos_tags: tuple            # Sudachiの品詞タプル全体（6要素）
    is_compound: bool = False  # Mode A/C差分で検出された複合語かどうか（品詞フィルタの判定には使わず、表示専用）


@lru_cache(maxsize=4)
def _get_dictionary(dict_type: str = "core"):
    """SudachiのDictionaryオブジェクトを辞書種別ごとにキャッシュして生成する"""
    return dictionary.Dictionary(dict=dict_type)


def get_tokenizer_obj(dict_type: str = "core"):
    return _get_dictionary(dict_type).create()


def tokenize(text: str, mode=SPLIT_MODE_A, dict_type: str = "core") -> list[Token]:
    """テキストをトークナイズしてTokenのリストを返す（長文はSudachiの入力上限に合わせて自動分割する）"""
    tok = get_tokenizer_obj(dict_type)
    tokens = []
    for chunk in _chunk_text_for_sudachi(text):
        for m in tok.tokenize(chunk, mode):
            tokens.append(Token(
                surface=m.surface(),
                normalized=m.dictionary_form(),
                pos_major=m.part_of_speech()[0],
                pos_tags=m.part_of_speech(),
            ))
    return tokens


# 強制抽出: Unicode私用領域（U+E000〜）の1文字を語句ごとのプレースホルダとして使う。
# トークナイズ前に語句をプレースホルダへ置換しておけば、Sudachiの通常の分割処理を
# 経由しても語句の境界が保たれ、後段でプレースホルダを元の語句に復元できる。
_PUA_START = 0xE000
_PUA_END = 0xF8FF
FORCED_POS_MAJOR = '強制抽出'


def protect_forced_terms(text: str, forced_terms: list[str]) -> tuple[str, dict[str, str]]:
    """
    強制抽出リストの語句をプレースホルダ文字に置換する。
    リストの先頭に近い語句ほど優先される（一度プレースホルダ化された箇所は、
    後続の語句の置換対象にはならないため、重なりはリスト順で解決される）。
    """
    placeholder_map: dict[str, str] = {}
    protected = text
    code = _PUA_START
    for term in forced_terms:
        term = term.strip()
        if not term or term not in protected:
            continue
        if code > _PUA_END:
            break  # プレースホルダに使える私用領域の文字を使い切った場合はそれ以降を無視
        placeholder = chr(code)
        protected = protected.replace(term, placeholder)
        placeholder_map[placeholder] = term
        code += 1
    return protected, placeholder_map


def restore_forced_tokens(tokens: list[Token], placeholder_map: dict[str, str]) -> list[Token]:
    """プレースホルダトークンを元の語句（品詞カテゴリ「強制抽出」）に復元する"""
    if not placeholder_map:
        return tokens
    restored = []
    for t in tokens:
        term = placeholder_map.get(t.surface)
        if term is not None:
            restored.append(Token(
                surface=term,
                normalized=term,
                pos_major=FORCED_POS_MAJOR,
                pos_tags=(FORCED_POS_MAJOR, '*', '*', '*', '*', '*'),
            ))
        else:
            restored.append(t)
    return restored


# 複合語検出: Mode A（短単位）とMode C（長単位）を同じテキストに対して実行し、
# Mode Cのトークンが複数のMode Aトークンにまたがっていれば複合語候補とみなす。
# 統計的抽出ライブラリを使わず、Sudachi辞書自身の単位差分だけで判定する。


def detect_compounds(text: str, dict_type: str = "core") -> list[Token]:
    """
    Mode A/C分割の差分から複合語候補のTokenリストを返す（見つからなければ空リスト）。
    長文はSudachiの入力上限に合わせて自動分割する（分割位置をまたぐ複合語は検出されないが、
    文書境界をまたいだ複合語をそもそも検出しない既存の設計と同じ許容範囲の制約）。
    """
    compounds = []
    for chunk in _chunk_text_for_sudachi(text):
        compounds.extend(_detect_compounds_in_chunk(chunk, dict_type))
    return compounds


def _detect_compounds_in_chunk(text: str, dict_type: str) -> list[Token]:
    tok = get_tokenizer_obj(dict_type)
    a_tokens = list(tok.tokenize(text, SPLIT_MODE_A))
    c_tokens = list(tok.tokenize(text, SPLIT_MODE_C))

    compounds = []
    a_index = 0
    for c in c_tokens:
        while a_index < len(a_tokens) and a_tokens[a_index].end() <= c.begin():
            a_index += 1
        j = a_index
        covered = 0
        while j < len(a_tokens) and a_tokens[j].begin() < c.end():
            covered += 1
            j += 1
        if covered >= 2:
            # 複合語も実際のSudachi品詞（名詞・動詞など）をそのまま保持する——
            # 品詞別語彙リストへの混在表示（表示名に「（複）」を付記）に品詞情報が必要なため。
            compounds.append(Token(
                surface=c.surface(),
                normalized=c.dictionary_form(),
                pos_major=c.part_of_speech()[0],
                pos_tags=c.part_of_speech(),
                is_compound=True,
            ))
        a_index = j
    return compounds


def apply_variant_map(tokens: list[Token], variant_map: dict[str, str]) -> list[Token]:
    """
    表記ゆれ統合（LLM提案を人が確定したもの）をトークンのnormalizedフィールドに適用する。
    surface/pos_major/pos_tagsは変更しない（品詞分類・元の表記はそのまま保持する）。
    """
    if not variant_map:
        return tokens
    return [
        Token(
            surface=t.surface,
            normalized=variant_map.get(t.normalized, t.normalized),
            pos_major=t.pos_major,
            pos_tags=t.pos_tags,
            is_compound=t.is_compound,
        )
        for t in tokens
    ]
