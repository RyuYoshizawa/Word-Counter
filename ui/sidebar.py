"""
sidebar.py
設定サイドバー：プロジェクト管理、テキスト/Excelアップロード、Sudachi辞書選択、品詞フィルタ。
"""

import pandas as pd
import streamlit as st

from core.pos_rules import CATEGORY_ORDER, DEFAULT_INCLUDED_CATEGORIES
from core.project import build_project, deserialize_project, serialize_project
from core.tokenizer import available_dict_types
from ui.auth import render_logout_button

INPUT_METHODS = ['テキストファイル', '貼り付け', 'Excel（ID・属性列あり）']

# 新規プロジェクト開始時にクリアすべきsession_stateキー（APIキーは意図的に含めない）
_PROJECT_RESET_KEYS = [
    'input_method', 'pasted_text_input', 'dict_type', 'forced_terms_text', 'stopwords_text',
    'xlsx_documents', 'xlsx_text_col', 'xlsx_id_col', 'xlsx_attr_cols',
    '_restored_documents', '_restored_joined_text', '_loaded_project_file_id',
    'variant_map', 'pending_variant_groups', 'codebook_text',
    'new_project_name', 'new_project_description',
    '_forced_terms_text_pending', '_forced_terms_text_loaded_file_id',
    '_stopwords_text_pending', '_stopwords_text_loaded_file_id',
]


def render_sidebar() -> dict:
    st.sidebar.title('Word_Counter')
    st.sidebar.caption('日本語テキストマイニングツール')
    st.sidebar.divider()

    st.session_state.setdefault('project', None)

    if st.session_state['project'] is None:
        _render_project_start()
    else:
        _render_project_name_header(st.session_state['project'])

    st.sidebar.divider()
    st.sidebar.subheader('データ')
    input_method = st.sidebar.radio('入力方法', INPUT_METHODS, key='input_method')

    if input_method == 'Excel（ID・属性列あり）':
        documents = _render_excel_upload()
    else:
        documents = _render_text_input(input_method)

    st.sidebar.divider()
    st.sidebar.subheader('形態素解析')
    dict_type = st.sidebar.selectbox('Sudachi辞書', available_dict_types(), index=0, key='dict_type',
                                      help='coreは一般語彙とサイズのバランス重視。'
                                           'fullは固有名詞・専門用語に強いが辞書サイズが大きい'
                                           '（未インストールの環境では選択肢に出ません）')

    st.sidebar.divider()
    st.sidebar.subheader('強制抽出')
    _render_list_upload_download('forced_terms_text', '強制抽出リスト', 'forced_terms')
    forced_terms_text = st.sidebar.text_area(
        '強制抽出リスト（1行1語句、上ほど優先）', height=100, key='forced_terms_text',
        help='語句をトークナイザの分割に優先して1語として扱う。'
             'リストの上にある語句ほど優先され、重なる語句は下側が無視される。',
    )
    forced_terms = [line.strip() for line in forced_terms_text.splitlines() if line.strip()]

    st.sidebar.divider()
    st.sidebar.subheader('ストップワード')
    _render_list_upload_download('stopwords_text', 'ストップワードリスト', 'stopwords')
    stopwords_text = st.sidebar.text_area(
        'ストップワード（1行1語、正規化した見出し語で指定）', height=100, key='stopwords_text',
        help='ここに書いた語は、出現語一覧・ワードクラウド・共起ネットワーク・クラスター分析の'
             '集計から除外されます（原文表示・強制抽出には影響しません）。',
    )
    stopwords = {line.strip() for line in stopwords_text.splitlines() if line.strip()}

    st.sidebar.divider()
    st.sidebar.subheader('品詞フィルタ（分析対象に含める）')
    included_categories = set()
    for cat in CATEGORY_ORDER:
        default = cat in DEFAULT_INCLUDED_CATEGORIES
        if st.sidebar.checkbox(cat, value=default, key=f'pos_cat_{cat}'):
            included_categories.add(cat)

    st.sidebar.divider()
    st.sidebar.subheader('LLM設定（表記ゆれ統合用）')
    api_key = st.sidebar.text_input(
        'Anthropic APIキー', type='password',
        help='データ準備タブの「LLMによる表記ゆれ統合」機能でのみ使用します。保存はセッション中のみ。',
    )

    _sync_or_create_project(input_method, documents, dict_type, forced_terms, included_categories, stopwords)
    if st.session_state['project'] is not None:
        st.sidebar.divider()
        _render_project_actions(st.session_state['project'])

    st.sidebar.divider()
    with st.sidebar:
        render_logout_button()

    return {
        'documents': documents,
        'dict_type': dict_type,
        'forced_terms': forced_terms,
        'stopwords': stopwords,
        'included_categories': included_categories,
        'api_key': api_key,
    }


def _render_list_upload_download(text_area_key: str, label: str, file_stem: str) -> None:
    """
    強制抽出・ストップワードのテキストエリアに、txtでのダウンロード/アップロードを追加する。
    アップロードは既存の内容を丸ごと上書きするため、プロジェクトJSONアップロード
    （`_render_project_start`）と同じfile_id追跡パターンで「既に処理済みの同一ファイルか」を
    判定した上で、件数を添えた警告＋明示的な確認/キャンセルボタンを挟んでから反映する
    （誤操作で既存リストを失わないため）。
    """
    current_text = st.session_state.get(text_area_key, '')
    st.sidebar.download_button(
        f'💾 {label}をダウンロード', data=current_text, file_name=f'{file_stem}.txt',
        mime='text/plain', disabled=not current_text.strip(),
        key=f'{text_area_key}_download', use_container_width=True,
    )

    uploaded = st.sidebar.file_uploader(
        f'{label}をアップロード（.txt、1行1語句）', type=['txt'], key=f'{text_area_key}_uploader',
    )
    pending_key = f'_{text_area_key}_pending'
    loaded_id_key = f'_{text_area_key}_loaded_file_id'
    if uploaded is not None and uploaded.file_id != st.session_state.get(loaded_id_key):
        st.session_state[loaded_id_key] = uploaded.file_id
        st.session_state[pending_key] = uploaded.read().decode('utf-8-sig')

    pending = st.session_state.get(pending_key)
    if pending is not None:
        current_count = len([line for line in current_text.splitlines() if line.strip()])
        new_count = len([line for line in pending.splitlines() if line.strip()])
        st.sidebar.warning(
            f'⚠️ アップロードすると現在の{label}（{current_count}件）を、'
            f'アップロードした内容（{new_count}件）で上書きします。'
        )
        with st.sidebar.expander('アップロード内容を確認', expanded=False):
            st.text(pending)
        col_ok, col_cancel = st.sidebar.columns(2)
        with col_ok:
            if st.button('✅ 上書きする', key=f'{text_area_key}_confirm', use_container_width=True):
                st.session_state[text_area_key] = pending
                st.session_state[pending_key] = None
                st.rerun()
        with col_cancel:
            if st.button('❌ キャンセル', key=f'{text_area_key}_cancel', use_container_width=True):
                st.session_state[pending_key] = None
                # このcallback内で完結するst.rerun()は、text_areaウィジェット自体が
                # この実行中に一度も呼ばれないまま中断される（_render_list_upload_downloadは
                # text_area呼び出しより前に置かれているため）。Streamlitは「その回の実行で
                # 登録されなかったウィジェットの値」を次の実行までに破棄してしまうため、
                # 何もせず単にrerunするとキャンセルのはずが既存の入力内容を消してしまう
                # （実機で確認した実際の不具合）。現在値をそのまま書き戻して明示的に
                # 「登録済み」の状態を維持してからrerunする。
                st.session_state[text_area_key] = current_text
                st.rerun()


def _render_project_start() -> None:
    st.sidebar.subheader('プロジェクト')
    with st.sidebar.expander('📂 既存プロジェクトを開く'):
        project_file = st.file_uploader('プロジェクトファイル（.json）', type=['json'], key='project_file_uploader')
        # st.file_uploaderはアップロード後も値を保持し続けるため、file_idで
        # 「既に処理済みか」を判定しないと、rerunのたびに復元処理を繰り返してしまい、
        # プロジェクト作成に到達する前に無限ループしてしまう。
        if project_file is not None and project_file.file_id != st.session_state.get('_loaded_project_file_id'):
            st.session_state['_loaded_project_file_id'] = project_file.file_id
            try:
                project = deserialize_project(project_file.read().decode('utf-8'))
            except ValueError as e:
                st.error(f'読み込みに失敗しました: {e}')
            else:
                _restore_project_state(project)
                st.rerun()

    st.sidebar.text_input('プロジェクト名', key='new_project_name')
    st.sidebar.text_area('概要（任意）', key='new_project_description', height=80)
    st.sidebar.caption('プロジェクト名を入力し、下記でデータを読み込むと分析が始まります。')


def _restore_project_state(project: dict) -> None:
    """プロジェクトファイルの内容を各widgetのsession_stateに復元する（入力方法は貼り付けとして復元）"""
    joined_text = '\n'.join(d['text'] for d in project['documents'])
    st.session_state['new_project_name'] = project['name']
    st.session_state['new_project_description'] = project['description']
    st.session_state['input_method'] = '貼り付け'
    st.session_state['pasted_text_input'] = joined_text
    st.session_state['_restored_documents'] = project['documents']
    st.session_state['_restored_joined_text'] = joined_text
    # 保存時にfullを選んでいても、復元先の環境にsudachidict_fullが無ければ
    # selectboxの選択肢に無い値になってしまう（Streamlitがエラーになる）ため、
    # その環境で実際に使える辞書種別に丸める。
    restored_dict_type = project['dict_type']
    if restored_dict_type not in available_dict_types():
        restored_dict_type = 'core'
    st.session_state['dict_type'] = restored_dict_type
    st.session_state['forced_terms_text'] = '\n'.join(project['forced_terms'])
    st.session_state['stopwords_text'] = '\n'.join(project.get('stopwords', []))
    for cat in CATEGORY_ORDER:
        st.session_state[f'pos_cat_{cat}'] = cat in project['included_categories']
    st.session_state['variant_map'] = project.get('variant_map', {})
    st.session_state['pending_variant_groups'] = None
    st.session_state['codebook_text'] = project.get('codebook', '')
    # project本体は、データ読み込みセクション実行後にdocumentsが揃ってから_sync_or_create_projectで作る


def _render_project_name_header(project: dict) -> None:
    st.sidebar.subheader(f'📁 {project["name"]}')
    with st.sidebar.expander('✏️ プロジェクト名・概要を編集'):
        new_name = st.text_input('プロジェクト名', value=project['name'], key='edit_project_name')
        new_desc = st.text_area('概要', value=project['description'], key='edit_project_description', height=80)
        project['name'] = new_name
        project['description'] = new_desc


def _render_project_actions(project: dict) -> None:
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.download_button(
            '💾 ダウンロード', data=serialize_project(project),
            file_name=f'{project["name"] or "project"}.json', mime='application/json',
            key='download_project', use_container_width=True,
        )
    with col2:
        if st.button('🆕 新規開始', key='new_project_button', use_container_width=True):
            for key in _PROJECT_RESET_KEYS:
                st.session_state.pop(key, None)
            st.session_state['project'] = None
            st.rerun()


def _sync_or_create_project(input_method: str, documents: list[dict], dict_type: str,
                             forced_terms: list[str], included_categories: set[str],
                             stopwords: set[str]) -> None:
    """documents等が揃った時点でプロジェクトを新規作成し、以降は毎レンダリング最新状態に同期する"""
    project = st.session_state['project']
    variant_map = st.session_state.get('variant_map', {})
    codebook_text = st.session_state.get('codebook_text', '')

    if project is None:
        new_name = st.session_state.get('new_project_name', '').strip()
        if new_name and documents:
            st.session_state['project'] = build_project(
                name=new_name,
                description=st.session_state.get('new_project_description', '').strip(),
                input_method=input_method, documents=documents, dict_type=dict_type,
                forced_terms=forced_terms, included_categories=sorted(included_categories),
                variant_map=variant_map, stopwords=sorted(stopwords), codebook=codebook_text,
            )
            st.rerun()
        return

    project.update({
        'input_method': input_method,
        'documents': documents,
        'dict_type': dict_type,
        'forced_terms': forced_terms,
        'included_categories': sorted(included_categories),
        'variant_map': variant_map,
        'stopwords': sorted(stopwords),
        'codebook': codebook_text,
    })


def _render_text_input(input_method: str) -> list[dict]:
    """テキストファイル/貼り付け入力から documents（改行区切り＝1文書）を作る"""
    if input_method == 'テキストファイル':
        uploaded = st.sidebar.file_uploader('テキストファイル（.txt）', type=['txt'])
        raw_text = uploaded.read().decode('utf-8', errors='ignore') if uploaded is not None else ''
    else:
        raw_text = st.sidebar.text_area('テキストを貼り付け', height=150, key='pasted_text_input')
        # プロジェクト復元直後で、まだテキストエリアが編集されていない間は、
        # 復元時のdocuments（id・attrsを保持したもの）をそのまま使う。
        if ('_restored_documents' in st.session_state
                and raw_text == st.session_state.get('_restored_joined_text')):
            return st.session_state['_restored_documents']
        st.session_state.pop('_restored_documents', None)
        st.session_state.pop('_restored_joined_text', None)

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return [{'id': f'L{i + 1:04d}', 'text': line, 'attrs': {}} for i, line in enumerate(lines)]


def _render_excel_upload() -> list[dict]:
    """
    ID・属性列付きExcelから documents を作る。After Coderの列マッピングUIを踏襲：
    列選択は即session_stateに反映されるが、documentsへの実際の変換は
    「この内容で読み込む」ボタンで明示的に確定するまで行われない。
    """
    uploaded = st.sidebar.file_uploader('Excelファイル（.xlsx）', type=['xlsx'], key='xlsx_uploader')
    if uploaded is None:
        return st.session_state.get('xlsx_documents', [])

    df = pd.read_excel(uploaded)
    with st.sidebar.expander('プレビュー（先頭5行）', expanded=False):
        st.dataframe(df.head())

    text_col = st.sidebar.selectbox('自由記述の列', df.columns, key='xlsx_text_col')
    id_col = st.sidebar.selectbox('IDの列（任意）', ['(なし・自動採番)'] + list(df.columns), key='xlsx_id_col')
    attr_options = [c for c in df.columns if c not in {text_col, id_col}]
    attr_cols = st.sidebar.multiselect(
        '属性として使う列（複数選択可・任意。年代・部署など）', attr_options, key='xlsx_attr_cols',
        help='属性は集計・共起ネットワークでのマッピングに使われ、単語の判定自体には使われません。',
    )

    if st.sidebar.button('この内容で読み込む', key='xlsx_confirm'):
        documents = []
        for i, row in df.iterrows():
            text = str(row[text_col]).strip() if pd.notna(row[text_col]) else ''
            if id_col != '(なし・自動採番)' and pd.notna(row[id_col]):
                doc_id = str(row[id_col]).strip()
            else:
                doc_id = f'L{i + 1:04d}'
            attrs = {c: str(row[c]).strip() for c in attr_cols if pd.notna(row[c])}
            documents.append({'id': doc_id, 'text': text, 'attrs': attrs})
        st.session_state['xlsx_documents'] = documents

    return st.session_state.get('xlsx_documents', [])
