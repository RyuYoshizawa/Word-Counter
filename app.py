"""
app.py
Word_Counter: 薄いオーケストレーター。page_config・session_state初期化・
サイドバー呼び出し・タブ振り分けのみを担う。分析ロジックはcore/、画面はui/に分離。
"""

import streamlit as st

from core.tokenizer import (
    SPLIT_MODE_A,
    SPLIT_MODE_C,
    apply_variant_map,
    detect_compounds,
    protect_forced_terms,
    restore_forced_tokens,
    tokenize,
)
from ui import (
    sidebar,
    tab_cleaning,
    tab_clustering,
    tab_crosstab,
    tab_network,
    tab_pos_freq,
    tab_wordcloud,
)

st.set_page_config(page_title='Word_Counter', page_icon='👾', layout='wide')

st.session_state.setdefault('_tokenize_cache_key', None)
st.session_state.setdefault('_doc_tokens_cache', [])
st.session_state.setdefault('_doc_compounds_cache', [])
st.session_state.setdefault('_doc_tokens_mode_c_cache', [])
st.session_state.setdefault('_forced_found_cache', [])
st.session_state.setdefault('_doc_ids_cache', [])
st.session_state.setdefault('_doc_attrs_cache', [])

settings = sidebar.render_sidebar()

if st.session_state.get('project') is None:
    st.info('サイドバーでプロジェクト名を入力し、データを読み込んでプロジェクトを開始してください。')
    st.stop()

documents = settings['documents']

cache_key = (
    tuple((d['id'], d['text']) for d in documents),
    settings['dict_type'],
    tuple(settings['forced_terms']),
)
if cache_key != st.session_state['_tokenize_cache_key']:
    dict_type = settings['dict_type']
    forced_terms = settings['forced_terms']

    doc_tokens = []
    doc_compounds = []
    doc_tokens_mode_c = []
    forced_found_all: set[str] = set()
    for d in documents:
        protected, placeholder_map = protect_forced_terms(d['text'], forced_terms)
        forced_found_all |= set(placeholder_map.values())
        raw_tokens = tokenize(protected, mode=SPLIT_MODE_A, dict_type=dict_type)
        doc_tokens.append(restore_forced_tokens(raw_tokens, placeholder_map))
        # 複合語も文書ごとに検出する（単語一覧・複合語一覧の「原文コンテキスト表示」に
        # どの文書の出現かという情報が必要なため、文書をまたいだ結合検出はしない）。
        doc_compounds.append(detect_compounds(protected, dict_type=dict_type))
        # 複合語一覧タブの原文コンテキスト表示用に、Mode Cでの通しトークン列も保持する
        # （doc_compoundsは複合語のみの抜粋なので、前後の単語が分からないため）。
        raw_tokens_c = tokenize(protected, mode=SPLIT_MODE_C, dict_type=dict_type)
        doc_tokens_mode_c.append(restore_forced_tokens(raw_tokens_c, placeholder_map))

    st.session_state['_doc_tokens_cache'] = doc_tokens
    st.session_state['_doc_compounds_cache'] = doc_compounds
    st.session_state['_doc_tokens_mode_c_cache'] = doc_tokens_mode_c
    st.session_state['_forced_found_cache'] = sorted(forced_found_all)
    st.session_state['_doc_ids_cache'] = [d['id'] for d in documents]
    st.session_state['_doc_attrs_cache'] = [d['attrs'] for d in documents]

    st.session_state['_tokenize_cache_key'] = cache_key

st.session_state.setdefault('variant_map', {})
variant_map = st.session_state['variant_map']

# LLM表記ゆれ統合（Phase 7）は再トークナイズ不要な後処理のため、_tokenize_cache_keyには
# 含めず、確定済みvariant_mapを毎回のレンダリングでキャッシュ済みトークンに適用する。
doc_tokens = [apply_variant_map(dt, variant_map) for dt in st.session_state['_doc_tokens_cache']]
tokens = [t for dt in doc_tokens for t in dt]  # Phase1〜3用の全体トークン列（doc_tokensの連結）
forced_found = st.session_state['_forced_found_cache']
doc_compounds = [apply_variant_map(dc, variant_map) for dc in st.session_state['_doc_compounds_cache']]
doc_tokens_mode_c = [apply_variant_map(dt, variant_map) for dt in st.session_state['_doc_tokens_mode_c_cache']]
doc_ids = st.session_state['_doc_ids_cache']
doc_attrs = st.session_state['_doc_attrs_cache']
included_categories = settings['included_categories']
stopwords = settings['stopwords']

tabs = st.tabs([
    'データ準備',
    '出現語一覧',
    'ワードクラウド',
    '共起ネットワークマップ',
    'クラスター分析',
    'クロス集計',
])

with tabs[0]:
    tab_cleaning.render(documents, tokens, settings['forced_terms'], forced_found, settings['api_key'])
with tabs[1]:
    tab_pos_freq.render(tokens, doc_tokens, doc_ids, doc_compounds, doc_tokens_mode_c,
                         included_categories, stopwords)
with tabs[2]:
    tab_wordcloud.render(tokens, included_categories, stopwords)
with tabs[3]:
    tab_network.render(doc_tokens, doc_attrs, included_categories, stopwords)
with tabs[4]:
    tab_clustering.render(doc_tokens, included_categories, stopwords)
with tabs[5]:
    tab_crosstab.render(doc_tokens, documents, doc_attrs)
