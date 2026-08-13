"""
context.py
単語一覧・複合語一覧タブで「語をクリック→原文の該当箇所一覧」を表示するための、
前後n語のコンテキスト抽出。
"""

from .tokenizer import Token

DEFAULT_WINDOW = 20


def find_word_contexts(word: str, doc_tokens: list[list[Token]], doc_ids: list[str],
                        window: int = DEFAULT_WINDOW) -> list[dict]:
    """
    指定した語（見出し語=normalizedで一致）の全ての出現箇所について、前後window語の
    コンテキストを抽出する。1文書内に複数回出現する場合は出現ごとに1件を返す。
    戻り値: [{'doc_id': str, 'before': str, 'matched': str, 'after': str}, ...]
    """
    results = []
    for doc_id, tokens in zip(doc_ids, doc_tokens):
        for i, t in enumerate(tokens):
            if t.normalized != word:
                continue
            start = max(0, i - window)
            end = min(len(tokens), i + window + 1)
            before = ''.join(tok.surface for tok in tokens[start:i])
            after = ''.join(tok.surface for tok in tokens[i + 1:end])
            results.append({
                'doc_id': doc_id,
                'before': before,
                'matched': t.surface,
                'after': after,
            })
    return results
