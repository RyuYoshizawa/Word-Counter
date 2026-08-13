"""
tab_crosstab.py
クロス集計タブ：単語・語群にコードを割り振るコードブックを作成し、既存の属性
（年代・学校・職位など、Excel入力由来）とクロス集計する。
"""

import streamlit as st

from core.codebook import apply_codebook, crosstab_codes_by_attr, parse_codebook


def render(doc_tokens: list, documents: list, doc_attrs: list[dict]) -> None:
    st.subheader('クロス集計')
    st.caption(
        'コードブック（1行1コード、「コード名: トリガー1, トリガー2, ...」形式）を作成し、'
        '既存の属性（年代・学校・職位など）とクロス集計します。トリガーが単語の見出し語と'
        '一致すれば表記ゆれ（例: 先生／教員／教師）をまとめて拾い、それ以外は原文への'
        '部分文字列一致になります（「食べない」「食べたい」のように活用の違いを区別したい'
        '場合は、そのままの形で書いてください）。'
    )

    if not doc_tokens:
        st.info('データ準備タブでテキストを読み込んでください。')
        return

    attr_keys = sorted({k for attrs in doc_attrs for k in attrs})
    if not attr_keys:
        st.info('属性情報がありません。Excel入力で属性列（年代・学校・職位など）を指定すると、ここでクロス集計できます。')
        return

    codebook_text = st.text_area(
        'コードブック（1行1コード）', height=150,
        placeholder='教師: 先生, 教員, 教師\n食べない: 食べない\n食べたい: 食べたい',
    )
    codes = parse_codebook(codebook_text)
    if not codes:
        st.info('コードブックを入力してください。')
        return

    attr_key = st.selectbox('クロス集計する属性', attr_keys)

    code_doc_sets = apply_codebook(codes, doc_tokens, documents)
    df = crosstab_codes_by_attr(code_doc_sets, doc_attrs, attr_key)
    if df.empty:
        st.warning('集計結果がありません。')
        return
    st.dataframe(df, height=400, use_container_width=True)

    with st.expander('各コードの該当状況'):
        for code in codes:
            n = len(code_doc_sets.get(code['name'], set()))
            st.caption(f"「{code['name']}」: {n}文書で該当（トリガー: {', '.join(code['triggers'])}）")
