"""
variant_grouping.py
LLMによる表記ゆれ・同義語のグルーピング提案。頻出語候補をLLMに渡し、
統合すべきグループ（代表語＋表記ゆれメンバー）を提案させる。
提案は必ず人が確認・確定してから適用する（自動適用しない、After Coderのpending_editパターンを踏襲）。
"""

from llm_client import call_llm

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


def groups_to_variant_map(groups: list[dict]) -> dict[str, str]:
    """グループリストを {語: 代表語} のマッピングに変換する（canonical自身の自己参照は含めない）"""
    variant_map = {}
    for g in groups:
        canonical = g['canonical']
        for member in g.get('members', []):
            if member != canonical:
                variant_map[member] = canonical
    return variant_map
