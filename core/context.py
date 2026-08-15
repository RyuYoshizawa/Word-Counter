"""
context.py
単語一覧・複合語一覧タブで「語をクリック→原文の該当箇所一覧」を表示するための、
その語を含む文（文末記号区切り）単位のコンテキスト抽出。
"""

from .tokenizer import SENTENCE_END_MARKS, Token


def find_word_contexts(word: str, doc_tokens: list[list[Token]], doc_ids: list[str]) -> list[dict]:
    """
    指定した語（見出し語=normalizedで一致）の全ての出現箇所について、その語を含む文
    （直前の文末記号の直後〜次の文末記号まで、文末記号自体を含む）をコンテキストとして
    抽出する。文末記号が無い文書/文末（例: 記号の無い短い自由記述）では、文書の先頭/末尾を
    文の境界とみなす。1文書内に複数回出現する場合は出現ごとに1件を返す。
    戻り値: [{'doc_id': str, 'before': str, 'matched': str, 'after': str}, ...]
    """
    results = []
    for doc_id, tokens in zip(doc_ids, doc_tokens):
        for i, t in enumerate(tokens):
            if t.normalized != word:
                continue
            start = i
            while start > 0 and tokens[start - 1].surface not in SENTENCE_END_MARKS:
                start -= 1
            end = i
            while end < len(tokens) - 1 and tokens[end].surface not in SENTENCE_END_MARKS:
                end += 1
            before = ''.join(tok.surface for tok in tokens[start:i])
            after = ''.join(tok.surface for tok in tokens[i + 1:end + 1])
            results.append({
                'doc_id': doc_id,
                'before': before,
                'matched': t.surface,
                'after': after,
            })
    return results
