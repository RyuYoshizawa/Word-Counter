"""
tab_pos_freq.py
出現語一覧タブ。左に語×品詞×出現数の表、右に選択した語を含む原文の該当箇所
（その語を含む文単位、該当語は太字）を一覧表示する。単語/複合語/混在の表示モードを切り替えられる。
"""

import streamlit as st

from core.context import find_word_contexts
from core.frequency import pos_frequency_table
from ui.common import pos_filter_caption

DISPLAY_MODES = ['単語', '複合語', '混在']


def render(tokens: list, doc_tokens: list, doc_ids: list, doc_compounds: list,
           doc_tokens_mode_c: list, included_categories: set, stopwords: set[str] | None = None) -> None:
    st.subheader('出現語一覧')

    flat_compounds = [t for dc in doc_compounds for t in dc]
    if not tokens and not flat_compounds:
        st.info('データ準備タブでテキストを読み込んでください。')
        return

    st.caption(pos_filter_caption(included_categories))
    display_mode = st.radio('表示', DISPLAY_MODES, horizontal=True, key='word_list_display_mode')

    if display_mode == '単語':
        display_tokens = tokens
    elif display_mode == '複合語':
        display_tokens = flat_compounds
    else:
        display_tokens = tokens + flat_compounds

    # 左（単語・品詞・出現数）は語自体は短く、品詞カテゴリ・出現数（最大6桁）も幅が読めるため
    # 狭くてよい。原文の表示に幅を回すため、右カラムを広く取る。
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown('##### 単語・品詞・出現数')
        word_df = pos_frequency_table(display_tokens, included_categories, stopwords)
        event = st.dataframe(
            word_df, height=500, use_container_width=True,
            on_select='rerun', selection_mode='single-row', key='word_freq_table',
        )

    with col2:
        st.markdown('##### 該当する原文')
        selected_rows = event.selection.rows if event and event.selection else []
        if not selected_rows:
            st.info('左の表から語を選択すると、その語を含む原文がここに表示されます。')
        else:
            row = word_df.iloc[selected_rows[0]]
            selected_word = row['語']
            # 複合語（表示カテゴリが「（複）」）は、複合語だけの抜粋であるdoc_compoundsではなく
            # Mode Cの通しトークン列で探す——前後の普通の単語も含めて正しい順序で見つかるため。
            # 単語（Mode Aのdoc_tokens由来）はそのままdoc_tokensで探す。
            is_compound_row = row['品詞カテゴリ'] == '（複）'
            context_source = doc_tokens_mode_c if is_compound_row else doc_tokens
            contexts = find_word_contexts(selected_word, context_source, doc_ids)
            st.caption(f'「{selected_word}」を含む原文: {len(contexts)}件（該当語を含む文、該当語は赤字太字）')
            with st.container(height=460):
                for c in contexts:
                    st.markdown(f"`{c['doc_id']}` {c['before']}:red[**{c['matched']}**]{c['after']}")
