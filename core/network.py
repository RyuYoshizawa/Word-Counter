"""
network.py
共起ネットワークマップ：文書-単語の出現有無からJaccard係数を計算し、networkxでグラフを構築する。
属性値（例：年代・部署など）を追加のノードとしてマッピングすることもできる。
可視化（色・サイズ・レイアウト等）はこのモジュールの責務外——core/network_viz.pyでJSON化した後、
ui/network_component.pyがD3.js（ブラウザ側）でエンコーディングを決めて描画する。
"""

from itertools import combinations
from typing import Literal

import networkx as nx

from .pos_rules import map_pos
from .tokenizer import Token

NodeType = Literal['word', 'attr']


def _doc_word_sets(doc_tokens: list[list[Token]], included_categories: set[str] | None,
                    stopwords: set[str] | None = None) -> list[set[str]]:
    """文書ごとの語集合（出現有無のみ、文書内での頻度は問わない）を返す"""
    sets = []
    for tokens in doc_tokens:
        words = set()
        for t in tokens:
            cat = map_pos(t)
            if included_categories is not None and cat not in included_categories:
                continue
            if stopwords and t.normalized in stopwords:
                continue
            words.add(t.normalized)
        sets.append(words)
    return sets


def attr_value_doc_sets(doc_attrs: list[dict], attr_key: str) -> dict[str, set[int]]:
    """指定した属性キーについて、属性値（文字列化）ごとに出現する文書indexの集合を返す（欠損値は除外）"""
    sets: dict[str, set[int]] = {}
    for i, attrs in enumerate(doc_attrs):
        val = attrs.get(attr_key)
        if val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue
        sets.setdefault(val_str, set()).add(i)
    return sets


def build_cooccurrence_edges(
    doc_tokens: list[list[Token]], included_categories: set[str] | None,
    min_doc_freq: int = 2, top_n: int = 60,
    attr_doc_sets: dict[str, set[int]] | None = None,
    attr_min_doc_freq: int = 1, attr_top_n: int = 20,
    stopwords: set[str] | None = None,
) -> tuple[dict[str, int], list[tuple[str, str, float]], list[tuple[str, str, float]], dict[str, NodeType]]:
    """
    Jaccard係数に基づく共起エッジを計算する。
    語×語エッジと語×属性値エッジは別々に返す——同じプールでJaccard係数順に競わせると、
    属性値エッジ（対象語数×対象属性値数で候補は少なく、Jaccard係数も語×語より低くなりがち）が
    語×語エッジに埋もれて消えてしまう不具合があったため（実データで属性値ノードが1個しか
    出ない事例で発覚）。語×属性値エッジは既にtop_n/attr_top_nで候補が絞られているため、
    後段のbuild_graphでは打ち切らず全て採用する。
    戻り値: (freq, word_word_edges, word_attr_edges, node_types)
    """
    doc_sets = _doc_word_sets(doc_tokens, included_categories, stopwords)

    doc_freq: dict[str, int] = {}
    word_docs: dict[str, set[int]] = {}
    for i, words in enumerate(doc_sets):
        for w in words:
            doc_freq[w] = doc_freq.get(w, 0) + 1
            word_docs.setdefault(w, set()).add(i)

    word_candidates = [w for w, f in doc_freq.items() if f >= min_doc_freq]
    word_candidates.sort(key=lambda w: doc_freq[w], reverse=True)
    word_candidates = word_candidates[:top_n]

    freq = {w: doc_freq[w] for w in word_candidates}
    all_docs = {w: word_docs[w] for w in word_candidates}
    node_types: dict[str, NodeType] = {w: 'word' for w in word_candidates}

    attr_candidates: list[str] = []
    if attr_doc_sets:
        attr_candidates = [v for v, docs in attr_doc_sets.items() if len(docs) >= attr_min_doc_freq]
        attr_candidates.sort(key=lambda v: len(attr_doc_sets[v]), reverse=True)
        attr_candidates = attr_candidates[:attr_top_n]
        for v in attr_candidates:
            freq[v] = len(attr_doc_sets[v])
            all_docs[v] = attr_doc_sets[v]
            node_types[v] = 'attr'

    word_word_edges = []
    for w1, w2 in combinations(word_candidates, 2):
        d1, d2 = all_docs[w1], all_docs[w2]
        inter = len(d1 & d2)
        if inter == 0:
            continue
        union = len(d1 | d2)
        word_word_edges.append((w1, w2, inter / union))

    word_attr_edges = []
    for w in word_candidates:
        for v in attr_candidates:
            d1, d2 = all_docs[w], all_docs[v]
            inter = len(d1 & d2)
            if inter == 0:
                continue
            union = len(d1 | d2)
            word_attr_edges.append((w, v, inter / union))

    return freq, word_word_edges, word_attr_edges, node_types


def build_graph(freq: dict[str, int], word_word_edges: list[tuple[str, str, float]],
                 word_attr_edges: list[tuple[str, str, float]] | None = None,
                 node_types: dict[str, NodeType] | None = None,
                 edge_threshold: float = 0.0, max_word_edges: int | None = 100) -> nx.Graph:
    """
    共起エッジからnetworkxグラフを構築する。語×語エッジのみJaccard係数上位max_word_edges本に
    絞り込み、語×属性値エッジは（既に候補数が絞られているため）全て採用する。
    """
    filtered_ww = [e for e in word_word_edges if e[2] >= edge_threshold]
    filtered_ww.sort(key=lambda e: e[2], reverse=True)
    if max_word_edges is not None:
        filtered_ww = filtered_ww[:max_word_edges]

    filtered_wa = [e for e in (word_attr_edges or []) if e[2] >= edge_threshold]

    g = nx.Graph()
    for w1, w2, jac in filtered_ww + filtered_wa:
        g.add_edge(w1, w2, weight=jac)

    node_types = node_types or {}
    for node in g.nodes():
        g.nodes[node]['freq'] = freq.get(node, 1)
        g.nodes[node]['node_type'] = node_types.get(node, 'word')

    for node in g.nodes():
        if g.nodes[node]['node_type'] != 'word':
            continue
        attr_degree = sum(1 for nb in g.neighbors(node) if g.nodes[nb].get('node_type') == 'attr')
        g.nodes[node]['attr_degree'] = attr_degree

    g.graph['max_freq'] = max((g.nodes[n]['freq'] for n in g.nodes()), default=1)
    return g

