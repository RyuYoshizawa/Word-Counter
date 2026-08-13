"""
common.py
複数タブで共有する小さな表示ヘルパー。
"""

from core.pos_rules import CATEGORY_ORDER


def pos_filter_caption(included_categories: set[str]) -> str:
    """現在の品詞フィルタをコンパクトな一行にまとめる（各タブの結果表示の直前に出す想定）"""
    if not included_categories:
        return '品詞: （フィルタで何も選択されていません）'
    ordered = [c for c in CATEGORY_ORDER if c in included_categories]
    return '品詞: ' + '・'.join(ordered)
