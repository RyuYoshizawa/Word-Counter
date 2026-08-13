"""
network_viz.py
networkxグラフをJSON化可能な辞書に変換する。色・サイズなどの視覚エンコーディングは
ここでは決めない——ui/network_component.py側（D3.js）の責務とし、このモジュールは
core/の設計原則通りStreamlit/ブラウザに依存しない純粋なデータ整形のみを行う。
"""

import networkx as nx


def graph_to_json_dict(g: nx.Graph) -> dict:
    """
    nx.Graphを {nodes, links, max_freq} のJSON化可能な辞書に変換する。
    nodes: {id, node_type, freq, attr_degree}（attr_degreeは単語ノードのみ、属性値ノードはNone）
    links: {source, target, weight}
    """
    nodes = [
        {
            'id': n,
            'node_type': g.nodes[n].get('node_type', 'word'),
            'freq': int(g.nodes[n].get('freq', 1)),
            'attr_degree': (int(g.nodes[n]['attr_degree'])
                             if g.nodes[n].get('node_type') == 'word' and 'attr_degree' in g.nodes[n]
                             else None),
        }
        for n in g.nodes()
    ]
    links = [
        {'source': u, 'target': v, 'weight': float(g.edges[u, v]['weight'])}
        for u, v in g.edges()
    ]
    return {'nodes': nodes, 'links': links, 'max_freq': int(g.graph.get('max_freq', 1))}
