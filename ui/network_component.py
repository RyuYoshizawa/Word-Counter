"""
network_component.py
共起ネットワークマップのD3.js可視化をStreamlit上に埋め込むためのHTML生成。
network_template.htmlのプレースホルダをグラフデータ・サイズで置換して
単一のHTML文字列を組み立てる（st.iframeにそのまま渡す）。
"""

import json
from pathlib import Path

_UI_DIR = Path(__file__).parent
_TEMPLATE_PATH = _UI_DIR / 'network_template.html'
_D3_PATH = _UI_DIR.parent / 'data' / 'vendor' / 'd3.v7.min.js'

# 印刷を前提にした利用を想定し、常にライト配色を使う（ダークモード追従は行わない）。
_BG, _FG = '#FFFFFF', '#222222'


def build_network_html(payload: dict, width: int, height: int, show_edge_labels: bool = True,
                        label_font_size: int = 11, node_size_scale: float = 1.5,
                        title: str = '共起ネットワーク', subtitle: str = '',
                        attr_kind_label: str = '属性値', attr_degree_label: str = '接続属性数') -> str:
    """
    グラフのJSONペイロードとサイズからD3可視化の完全なHTML文字列を組み立てる。
    D3本体はCDN参照ではなくローカルの静的ファイル（data/vendor/d3.v7.min.js）をそのまま
    <script>タグにインライン埋め込みする——外部ネットワークリクエストを一切発生させないため。
    titleは太字1段目、subtitle（例: プロジェクト名）は指定時のみレギュラーウェイトで2段目に表示する。
    attr_*_labelは、node_type='attr'のノード（属性値ハブ）に関するツールチップ・凡例の表示文言。
    共起ネットワークマップタブでは既定のまま（「属性値」）でよいが、コーディング集計タブでは
    属性値ではなくコードをこの'attr'枠に流用するため「コード」等に差し替える（core/network.py
    自体はattrが実際に何を表すか関知しない汎用設計——詳細はcore/codebook.pyのlabel_codes参照）。
    """
    template = _TEMPLATE_PATH.read_text(encoding='utf-8')
    d3_source = _D3_PATH.read_text(encoding='utf-8')
    # </script>によるスクリプトタグの早期終了を防ぐ（JSONは通常のJSリテラルとして埋め込む）
    payload_json = json.dumps(payload).replace('</script>', '<\\/script>')
    title_json = json.dumps(title)
    subtitle_json = json.dumps(subtitle)

    return (
        template
        .replace('__WC_D3_SOURCE__', d3_source)
        .replace('__WC_GRAPH_DATA_JSON__', payload_json)
        .replace('__WC_WIDTH__', str(width))
        .replace('__WC_HEIGHT__', str(height))
        .replace('__WC_SHOW_EDGE_LABELS__', 'true' if show_edge_labels else 'false')
        .replace('__WC_LABEL_FONT_SIZE__', str(label_font_size))
        .replace('__WC_NODE_SIZE_SCALE__', str(node_size_scale))
        .replace('__WC_TITLE_JSON__', title_json)
        .replace('__WC_SUBTITLE_JSON__', subtitle_json)
        .replace('__WC_ATTR_KIND_LABEL_JSON__', json.dumps(attr_kind_label))
        .replace('__WC_ATTR_DEGREE_LABEL_JSON__', json.dumps(attr_degree_label))
        .replace('__WC_BG__', _BG)
        .replace('__WC_FG__', _FG)
    )
