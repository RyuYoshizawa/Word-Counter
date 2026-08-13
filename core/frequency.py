"""
frequency.py
品詞別語彙リスト・単語の出現数の集計。複合語頻度はPhase 3で追加予定。
"""

from collections import Counter

import pandas as pd

from .pos_rules import display_category, map_pos
from .tokenizer import Token


def _filter_tokens(tokens: list[Token], included_categories: set[str] | None,
                    stopwords: set[str] | None = None) -> list[tuple[Token, str]]:
    """トークンにカテゴリを付与し、対象カテゴリかつストップワードでない語のみ残す"""
    tagged = [(t, map_pos(t)) for t in tokens]
    if included_categories is not None:
        tagged = [(t, c) for t, c in tagged if c in included_categories]
    if stopwords:
        tagged = [(t, c) for t, c in tagged if t.normalized not in stopwords]
    return tagged


def pos_frequency_table(tokens: list[Token], included_categories: set[str] | None = None,
                         stopwords: set[str] | None = None) -> pd.DataFrame:
    """
    品詞カテゴリ別の語彙頻度表（語×品詞カテゴリごとに出現回数）。
    複合語トークン（is_compound=True）が混ざっている場合、対象カテゴリの判定はmap_pos()の
    基本カテゴリで行うが、表示上のカテゴリ名はdisplay_category()で「（複）」を付記する。
    """
    tagged = _filter_tokens(tokens, included_categories, stopwords)
    counts = Counter((t.normalized, display_category(t)) for t, _ in tagged)
    rows = [
        {'語': word, '品詞カテゴリ': cat, '出現回数': n}
        for (word, cat), n in counts.items()
    ]
    df = pd.DataFrame(rows, columns=['語', '品詞カテゴリ', '出現回数'])
    if df.empty:
        return df
    return df.sort_values(['品詞カテゴリ', '出現回数'], ascending=[True, False]).reset_index(drop=True)


def word_frequency_table(tokens: list[Token], included_categories: set[str] | None = None,
                          stopwords: set[str] | None = None) -> pd.DataFrame:
    """品詞を問わない単語の出現回数表（見出し語で集計）"""
    tagged = _filter_tokens(tokens, included_categories, stopwords)
    counts = Counter(t.normalized for t, _ in tagged)
    df = pd.DataFrame(counts.items(), columns=['語', '出現回数'])
    if df.empty:
        return df
    return df.sort_values('出現回数', ascending=False).reset_index(drop=True)


def word_category_map(tokens: list[Token], included_categories: set[str] | None = None,
                       stopwords: set[str] | None = None) -> dict[str, str]:
    """
    {語: 品詞カテゴリ} を返す（ワードクラウドの品詞別色分け用）。
    同じ語が複数の品詞カテゴリで出現する場合は、最も出現回数が多いカテゴリを採用する。
    """
    tagged = _filter_tokens(tokens, included_categories, stopwords)
    counts: dict[str, Counter] = {}
    for t, cat in tagged:
        counts.setdefault(t.normalized, Counter())[cat] += 1
    return {word: c.most_common(1)[0][0] for word, c in counts.items()}
