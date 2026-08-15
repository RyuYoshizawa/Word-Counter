"""
project.py
プロジェクトファイル（.json）のシリアライズ/デシリアライズ。
APIキーや計算済みキャッシュ（トークナイズ結果等）は保存しない——
documentsと設定さえあれば毎回安価に再計算できるため、ファイルを軽く保てる。
"""

import json
from datetime import datetime, timezone

PROJECT_SCHEMA_VERSION = 1

_REQUIRED_KEYS = {
    'schema_version', 'name', 'description', 'input_method',
    'documents', 'dict_type', 'forced_terms', 'included_categories', 'variant_map',
}


def build_project(name: str, description: str, input_method: str, documents: list[dict],
                   dict_type: str, forced_terms: list[str], included_categories: list[str],
                   variant_map: dict[str, str], stopwords: list[str] | None = None,
                   codebook: str = '') -> dict:
    """プロジェクトdictを組み立てる"""
    return {
        'schema_version': PROJECT_SCHEMA_VERSION,
        'saved_at': datetime.now(timezone.utc).isoformat(),
        'name': name,
        'description': description,
        'input_method': input_method,
        'documents': documents,
        'dict_type': dict_type,
        'forced_terms': forced_terms,
        'included_categories': included_categories,
        'variant_map': variant_map,
        'stopwords': stopwords or [],
        'codebook': codebook,
    }


def serialize_project(project: dict) -> str:
    """プロジェクトdictをJSON文字列に変換する"""
    return json.dumps(project, ensure_ascii=False, indent=2)


def deserialize_project(raw: str) -> dict:
    """
    JSON文字列からプロジェクトdictを復元する。
    必須キーの欠損やJSON構文エラーの場合は分かりやすいメッセージのValueErrorを送出する。
    """
    try:
        project = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f'JSONとして読み込めませんでした: {e}') from e

    if not isinstance(project, dict):
        raise ValueError('プロジェクトファイルの形式が不正です（オブジェクトではありません）')

    missing = _REQUIRED_KEYS - project.keys()
    if missing:
        raise ValueError(f'プロジェクトファイルに必要な項目がありません: {", ".join(sorted(missing))}')

    if project['schema_version'] > PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f'このプロジェクトファイルは新しいバージョン（schema_version={project["schema_version"]}）で'
            f'保存されています。アプリを更新してください。'
        )

    return project
