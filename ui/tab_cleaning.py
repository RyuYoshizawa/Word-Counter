"""
tab_cleaning.py
データ準備タブ：アップロード状況・トークナイズ結果・強制抽出・LLM表記ゆれ統合の概要表示。
"""

import streamlit as st

import llm_client
from core.frequency import word_frequency_table
from core.pos_rules import DEFAULT_INCLUDED_CATEGORIES
from core.variant_grouping import groups_to_variant_map, propose_variant_groups

VARIANT_MODEL = 'claude-haiku-4-5'
CANDIDATE_TOP_N = 80


def render(documents: list[dict], tokens: list, forced_terms: list[str], forced_found: list[str], api_key: str) -> None:
    st.subheader('データ準備')

    if not documents:
        st.info('サイドバーからテキストファイル・貼り付け・Excelのいずれかでデータを読み込んでください。')
        return

    n_chars = sum(len(d['text']) for d in documents)
    st.metric('文書数', f'{len(documents):,}')
    st.metric('合計文字数', f'{n_chars:,}')
    st.metric('トークン数', f'{len(tokens):,}')

    with st.expander('テキストプレビュー（先頭5文書）'):
        for d in documents[:5]:
            st.text(d['text'][:200])

    attr_keys = sorted({k for d in documents for k in d['attrs']})
    if attr_keys:
        st.markdown('##### 属性')
        for key in attr_keys:
            values = sorted({d['attrs'][key] for d in documents if key in d['attrs']})
            st.caption(f'{key}: {len(values)}種類の値（例: {"、".join(values[:5])}）')

    if forced_terms:
        not_found = [t for t in forced_terms if t not in forced_found]
        st.markdown('##### 強制抽出')
        st.write(f'テキスト中で見つかった語句: {len(forced_found)} / {len(forced_terms)}')
        if forced_found:
            st.caption('見つかった語句: ' + '、'.join(forced_found))
        if not_found:
            st.caption('⚠️ テキスト中に見つからなかった語句: ' + '、'.join(not_found))

    st.divider()
    _render_variant_grouping(tokens, api_key)


def _render_variant_grouping(tokens: list, api_key: str) -> None:
    st.markdown('##### LLMによる表記ゆれ統合')
    st.caption('頻出語の中から表記ゆれ・同義語をLLMに提案させ、内容を確認してから統合します（自動適用はしません）。')

    st.session_state.setdefault('variant_map', {})
    st.session_state.setdefault('pending_variant_groups', None)

    variant_map = st.session_state['variant_map']
    if variant_map:
        with st.expander(f'適用中の統合ルール（{len(variant_map)}件）', expanded=False):
            for member, canonical in variant_map.items():
                st.caption(f'{member} → {canonical}')
        if st.button('統合ルールをすべて解除', key='clear_variant_map'):
            st.session_state['variant_map'] = {}
            st.rerun()

    pending = st.session_state['pending_variant_groups']

    if pending is None:
        if st.button('候補を提案', key='propose_variant_groups', disabled=not api_key):
            word_df = word_frequency_table(tokens, DEFAULT_INCLUDED_CATEGORIES)
            candidates = word_df['語'].head(CANDIDATE_TOP_N).tolist()
            client = llm_client.make_client('Anthropic', api_key)
            with st.spinner('LLMに提案を依頼しています...'):
                groups = propose_variant_groups(client, candidates, VARIANT_MODEL)
            if groups is None:
                st.error(f'提案の取得に失敗しました: {llm_client.get_last_error()}')
            elif not groups:
                st.info('統合すべき表記ゆれ・同義語は見つかりませんでした。')
            else:
                st.session_state['pending_variant_groups'] = groups
            st.rerun()
        if not api_key:
            st.caption('サイドバーでAPIキーを設定すると利用できます。')
        return

    st.write(f'{len(pending)}件のグループが提案されました。内容を確認してください。')
    for g in pending:
        members = '、'.join(g.get('members', []))
        st.markdown(f"**{g['canonical']}** ← {members}")
        reason = g.get('reason', '')
        if reason:
            st.caption(reason)

    col1, col2 = st.columns(2)
    with col1:
        if st.button('✅ 確定する', key='confirm_variant_groups'):
            new_map = groups_to_variant_map(pending)
            st.session_state['variant_map'] = {**st.session_state['variant_map'], **new_map}
            st.session_state['pending_variant_groups'] = None
            st.rerun()
    with col2:
        if st.button('❌ キャンセル', key='cancel_variant_groups'):
            st.session_state['pending_variant_groups'] = None
            st.rerun()
