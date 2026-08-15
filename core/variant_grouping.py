"""
variant_grouping.py
表記ゆれ・同義語のグルーピング提案。TANSI表記ゆれ辞書（辞書ベース、無料・即時）とLLM
（辞書でカバーしきれない語のみ対象）を組み合わせて、統合すべきグループ（代表語＋表記ゆれ
メンバー）を提案する。提案は必ず人が確認・確定してから適用する（自動適用しない、
After Coderのpending_editパターンを踏襲）。
"""

from functools import lru_cache
from pathlib import Path

from llm_client import call_llm

# KH Coder付属のTANSI表記ゆれ辞書（約30万件、表記×読み×発音×品詞×活用形×同義語グループ列の
# タブ区切り）。このユーザーのマシン固有の外部パスを直接参照する——プロジェクトには同梱しない
# （37MBあり、汎用の一般語彙辞書のためgit管理には不向き）。core/fonts.pyのWindows標準フォント
# 解決と同じ、固定パス＋ファイルが無い環境ではNoneを返すグレースフルデグレードのパターン。
_TANSI_DICT_PATH = Path(
    r"C:\Users\ryu\Documents\C_Storage\■MJ吉澤研究\【重要】■■テキストマイニング"
    r"\【重要】■■KH_Coder\KH Corder\TANSI_v110\TANSI_v110.txt"
)

VARIANT_GROUPING_SCHEMA = {
    'type': 'object',
    'properties': {
        'groups': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'canonical': {'type': 'string', 'description': '統合後の代表語'},
                    'members': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'canonicalに統合すべき表記ゆれ・同義語のリスト（canonical自身は含めない）',
                    },
                    'reason': {'type': 'string', 'description': '統合理由の簡潔な説明'},
                },
                'required': ['canonical', 'members'],
            },
        },
    },
    'required': ['groups'],
}

_PROMPT_TEMPLATE = """以下は日本語テキストから抽出した頻出語のリストです。

【対象語リスト】
{word_list}

このリストの中から、表記ゆれ（全角/半角、送り仮名の違い、略称/正式名称、ひらがな/カタカナ/漢字の違いなど）や
明らかな同義語とみなせるものをグループ化してください。

【指示】
- 明らかに同一の対象・概念を指す表記ゆれ・同義語のみをグループ化すること。意味が異なる語は統合しないこと。
- 各グループには統合後の代表語（canonical）と、そこに統合すべき語のリスト（members）を含めること。
- 迷う場合は無理に統合せず、グループに含めないこと（過剰統合より見落としの方が安全）。
- 統合の必要がない語についてはグループを作らなくてよい（全語を無理にグループ化する必要はない）。
"""


def build_prompt(candidate_words: list[str]) -> str:
    return _PROMPT_TEMPLATE.format(word_list='、'.join(candidate_words))


def propose_variant_groups(client, candidate_words: list[str], model: str) -> list[dict] | None:
    """
    LLMに表記ゆれ・同義語のグルーピングを提案させる。
    戻り値: [{'canonical': str, 'members': [str, ...], 'reason': str}, ...] または失敗時None。
    members が空のグループは除外して返す。
    """
    if not candidate_words:
        return []
    prompt = build_prompt(candidate_words)
    result = call_llm(client, prompt, VARIANT_GROUPING_SCHEMA, 'Anthropic', model)
    if not result:
        return None
    groups = result.get('groups', [])
    return [g for g in groups if g.get('members')]


@lru_cache(maxsize=1)
def _load_tansi_reading_map() -> dict[str, str] | None:
    """
    TANSI表記ゆれ辞書を {表記: 発音（長音正規化済みの読み）} に変換して読み込む（プロセス内で
    1回だけ、以降はキャッシュを再利用——30万行・37MBの逐次パースはコストが高いため）。
    ファイルが見つからない環境ではNoneを返し、辞書ベース検出を静かに無効化する。
    """
    if not _TANSI_DICT_PATH.exists():
        return None
    reading_map: dict[str, str] = {}
    with open(_TANSI_DICT_PATH, encoding='utf-8') as f:
        for line in f:
            cols = line.rstrip('\n').split('\t')
            if len(cols) < 3:
                continue
            surface, pronunciation = cols[0], cols[2]
            reading_map.setdefault(surface, pronunciation)
    return reading_map


def propose_dictionary_variant_groups(candidate_words: list[str]) -> list[dict]:
    """
    TANSI表記ゆれ辞書の「発音」（長音正規化済みの読み）が一致する語をグループ化する。
    candidate_wordsは頻度降順を想定——各グループの代表語（canonical）は、その中で
    最初に登場した語（＝最も頻度が高い語）にする。辞書が利用できない環境では空リストを返す。
    戻り値の各要素にはLLM提案と揃えて 'source': '辞書' を含める。
    """
    reading_map = _load_tansi_reading_map()
    if not reading_map:
        return []

    words_by_reading: dict[str, list[str]] = {}
    for word in candidate_words:
        reading = reading_map.get(word)
        if reading is None:
            continue
        words_by_reading.setdefault(reading, []).append(word)

    groups = []
    for reading, words in words_by_reading.items():
        if len(words) < 2:
            continue
        canonical, *members = words
        groups.append({
            'canonical': canonical,
            'members': members,
            'reason': f'辞書（読み「{reading}」が一致）',
            'source': '辞書',
        })
    return groups


def groups_to_variant_map(groups: list[dict]) -> dict[str, str]:
    """グループリストを {語: 代表語} のマッピングに変換する（canonical自身の自己参照は含めない）"""
    variant_map = {}
    for g in groups:
        canonical = g['canonical']
        for member in g.get('members', []):
            if member != canonical:
                variant_map[member] = canonical
    return variant_map
