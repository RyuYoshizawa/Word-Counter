"""
tab_cleaning.py
データ準備タブ：アップロード状況・トークナイズ結果・強制抽出・LLM表記ゆれ統合の概要表示。
"""

import streamlit as st

import llm_client
from core.frequency import word_frequency_table
from core.pos_rules import DEFAULT_INCLUDED_CATEGORIES
from core.variant_grouping import (
    groups_to_variant_map,
    propose_dictionary_variant_groups,
    propose_variant_groups,
)

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
    st.markdown('##### 表記ゆれ統合')
    st.caption('頻出語の中から表記ゆれ・同義語を、辞書（無料・即時）とLLM（辞書でカバーしき'
               'れない語のみ）を併用して提案し、内容を確認してから統合します（自動適用はしません）。')

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
        if st.button('候補を提案', key='propose_variant_groups'):
            word_df = word_frequency_table(tokens, DEFAULT_INCLUDED_CATEGORIES)
            candidates = word_df['語'].head(CANDIDATE_TOP_N).tolist()

            dict_groups = propose_dictionary_variant_groups(candidates)
            covered = {w for g in dict_groups for w in [g['canonical'], *g['members']]}
            llm_candidates = [w for w in candidates if w not in covered]

            groups = list(dict_groups)
            if llm_candidates and api_key:
                client = llm_client.make_client('Anthropic', api_key)
                with st.spinner('LLMに提案を依頼しています...'):
                    llm_groups = propose_variant_groups(client, llm_candidates, VARIANT_MODEL)
                if llm_groups is None:
                    st.error(f'LLM提案の取得に失敗しました: {llm_client.get_last_error()}'
                             '（辞書ベースの提案のみ表示します）')
                else:
                    for g in llm_groups:
                        g['source'] = 'LLM'
                    groups.extend(llm_groups)
            elif llm_candidates and not api_key:
                st.caption('サイドバーでAPIキーを設定すると、辞書でカバーしきれない語もLLMが'
                           '追加で提案します（今回は辞書ベースの提案のみです）。')

            if not groups:
                st.info('統合すべき表記ゆれ・同義語は見つかりませんでした。')
            else:
                st.session_state['pending_variant_groups'] = groups
            st.rerun()
        return

    st.write(f'{len(pending)}件のグループが提案されました。内容を確認し、チェックを付けてから'
             '下のボタンで処理してください（チェックした項目のみが対象です）。')
    checked_flags = []
    for i, g in enumerate(pending):
        members = '、'.join(g.get('members', []))
        reason = g.get('reason', '')
        source = g.get('source', '')
        badge = f'`{source}` ' if source else ''
        label = f"{badge}**{g['canonical']}** ← {members}"
        checked = st.checkbox(label, value=True, key=f'variant_check_{i}')
        checked_flags.append(checked)
        if reason:
            st.caption(reason)

    col1, col2 = st.columns(2)
    with col1:
        if st.button('チェックした項目を「同義語とする」', key='approve_checked_variant_groups'):
            approved = [g for g, checked in zip(pending, checked_flags) if checked]
            remaining = [g for g, checked in zip(pending, checked_flags) if not checked]
            if approved:
                new_map = groups_to_variant_map(approved)
                st.session_state['variant_map'] = {**st.session_state['variant_map'], **new_map}
            st.session_state['pending_variant_groups'] = remaining or None
            st.rerun()
    with col2:
        if st.button('チェックした項目を「同義語としない」', key='reject_checked_variant_groups'):
            remaining = [g for g, checked in zip(pending, checked_flags) if not checked]
            st.session_state['pending_variant_groups'] = remaining or None
            st.rerun()
