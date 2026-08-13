"""
codebook.py
クロス集計用のコードブック：単語・語群にコードを割り振り、既存の属性（年代・学校・職位など）
とクロス集計する。トリガーは (1) 正規化語（dictionary_form）一致、(2) 原文への部分文字列一致
のどちらかで自動判定する——(1)は先生/教員/教師のような同義語グルーピング、(2)は「食べない」
「食べたい」のように形態素解析の正規化で区別が消える活用差を拾うための妥協案。
"""

import pandas as pd

from .network import attr_value_doc_sets
from .tokenizer import Token


def parse_codebook(text: str) -> list[dict]:
    """
    「コード名: トリガー1, トリガー2, ...」形式（1行1コード）をパースする。
    形式に合わない行（コロンが無い、コード名/トリガーが空）は無視する。
    """
    codes = []
    for line in text.splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        name, triggers_str = line.split(':', 1)
        name = name.strip()
        triggers = [t.strip() for t in triggers_str.split(',') if t.strip()]
        if name and triggers:
            codes.append({'name': name, 'triggers': triggers})
    return codes


def apply_codebook(codes: list[dict], doc_tokens: list[list[Token]],
                    documents: list[dict]) -> dict[str, set[int]]:
    """コードごとに、トリガーが一致する文書indexの集合を返す（{コード名: {文書index, ...}}）"""
    normalized_docs: dict[str, set[int]] = {}
    for i, tokens in enumerate(doc_tokens):
        for t in tokens:
            normalized_docs.setdefault(t.normalized, set()).add(i)

    result: dict[str, set[int]] = {}
    for code in codes:
        matched: set[int] = set()
        for trigger in code['triggers']:
            if trigger in normalized_docs:
                matched |= normalized_docs[trigger]
            else:
                matched |= {i for i, d in enumerate(documents) if trigger in d['text']}
        result[code['name']] = matched
    return result


def crosstab_codes_by_attr(code_doc_sets: dict[str, set[int]], doc_attrs: list[dict],
                            attr_key: str) -> pd.DataFrame:
    """コード×属性値の文書数クロス集計表を作る（列は属性値、最後に合計列）"""
    attr_sets = attr_value_doc_sets(doc_attrs, attr_key)
    attr_values = sorted(attr_sets, key=lambda v: len(attr_sets[v]), reverse=True)

    rows = []
    for code_name, doc_set in code_doc_sets.items():
        row = {'コード': code_name}
        for v in attr_values:
            row[v] = len(doc_set & attr_sets[v])
        row['合計'] = len(doc_set)
        rows.append(row)
    return pd.DataFrame(rows, columns=['コード', *attr_values, '合計'])
