"""
network_component.py
共起ネットワークマップのD3.js可視化をStreamlit上に埋め込むためのHTML生成。
network_template.htmlのプレースホルダをグラフデータ・サイズ・テーマ色で置換して
単一のHTML文字列を組み立てる（st.iframeにそのまま渡す）。
"""

import json
from pathlib import Path

_UI_DIR = Path(__file__).parent
_TEMPLATE_PATH = _UI_DIR / 'network_template.html'
_D3_PATH = _UI_DIR.parent / 'data' / 'vendor' / 'd3.v7.min.js'

_LIGHT_BG, _LIGHT_FG = '#FFFFFF', '#222222'
_DARK_BG, _DARK_FG = '#0E1117', '#FAFAFA'


def build_network_html(payload: dict, width: int, height: int,
                        show_edge_labels: bool = True, theme_type: str | None = None) -> str:
    """
    グラフのJSONペイロードとサイズ・テーマからD3可視化の完全なHTML文字列を組み立てる。
    D3本体はCDN参照ではなくローカルの静的ファイル（data/vendor/d3.v7.min.js）をそのまま
    <script>タグにインライン埋め込みする——外部ネットワークリクエストを一切発生させないため。
    """
    template = _TEMPLATE_PATH.read_text(encoding='utf-8')
    d3_source = _D3_PATH.read_text(encoding='utf-8')
    # </script>によるスクリプトタグの早期終了を防ぐ（JSONは通常のJSリテラルとして埋め込む）
    payload_json = json.dumps(payload).replace('</script>', '<\\/script>')

    bg, fg = (_DARK_BG, _DARK_FG) if theme_type == 'dark' else (_LIGHT_BG, _LIGHT_FG)

    return (
        template
        .replace('__WC_D3_SOURCE__', d3_source)
        .replace('__WC_GRAPH_DATA_JSON__', payload_json)
        .replace('__WC_WIDTH__', str(width))
        .replace('__WC_HEIGHT__', str(height))
        .replace('__WC_SHOW_EDGE_LABELS__', 'true' if show_edge_labels else 'false')
        .replace('__WC_BG__', bg)
        .replace('__WC_FG__', fg)
    )
