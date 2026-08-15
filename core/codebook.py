"""
codebook.py
クロス集計用のコードブック：単語・語群にコードを割り振り、既存の属性（年代・学校・職位など）
とクロス集計する。トリガーは (1) 正規化語（dictionary_form）一致、(2) 原文への部分文字列一致
のどちらかで自動判定する——(1)は先生/教員/教師のような同義語グルーピング、(2)は「食べない」
「食べたい」のように形態素解析の正規化で区別が消える活用差を拾うための妥協案。
"""

import numpy as np
import pandas as pd

from .network import attr_value_doc_sets
from .tokenizer import Token

# コードを共起ネットワーク・クラスター分析（本来は語彙向けの分析）に混ぜる際、コード名が
# 素の語彙と文字列として衝突しうる（例: コード「年配」のトリガーに「年配」という語自体が
# 含まれる）。衝突するとfreq/node_typesが上書きされ、語とコードが同一ノードとして混ざって
# しまうため、常に一意な記号を付けて区別する。「［コード］」のような文言だと、共起ネット
# ワークのノードラベルや（将来的な）ワードクラウド表示で場所を取りすぎるため、通常の日本語
# 文章にはまず登場しない短い記号（ダガー、†）を採用した。
_CODE_LABEL_SUFFIX = '†'


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


def label_codes(code_doc_sets: dict[str, set[int]]) -> dict[str, set[int]]:
    """コード名に一意な記号（_CODE_LABEL_SUFFIX）を付け、素の語彙と文字列衝突しないようにする
    （例: コード「年配」のトリガーに「年配」という語自体が含まれる場合の対策）。共起ネット
    ワーク・クラスター分析にコードを混ぜる直前にのみ使う——出現率・属性クロス集計など
    コード単体で完結する表示には適用しない（コード名をそのまま見せたいため）。"""
    return {f'{name}{_CODE_LABEL_SUFFIX}': doc_set for name, doc_set in code_doc_sets.items()}


def code_occurrence_rates(code_doc_sets: dict[str, set[int]], n_docs: int) -> dict[str, float]:
    """各コードの出現率（該当文書数 / 総文書数）を返す。n_docs=0なら空辞書。"""
    if n_docs == 0:
        return {}
    return {name: len(doc_set) / n_docs for name, doc_set in code_doc_sets.items()}


def code_doc_matrix(code_doc_sets: dict[str, set[int]], n_docs: int) -> tuple[list[str], np.ndarray]:
    """コードの文書別マッチ集合を、クラスター分析が使う語×文書出現有無行列
    （core/clustering.pyのbuild_word_doc_matrixと同じ形、bool ndarray shape=(len(labels), n_docs)）
    に変換する。ラベルにはlabel_codesで衝突防止の記号を付与する。"""
    labeled = label_codes(code_doc_sets)
    labels = list(labeled.keys())
    matrix = np.zeros((len(labels), n_docs), dtype=bool)
    for i, name in enumerate(labels):
        for doc_idx in labeled[name]:
            if 0 <= doc_idx < n_docs:
                matrix[i, doc_idx] = True
    return labels, matrix
