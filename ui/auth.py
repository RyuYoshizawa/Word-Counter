"""
auth.py
簡易ユーザー名/パスワード認証（After Coderと同じUX）。認証情報はコードに書かず、
st.secrets（ローカルでは.streamlit/secrets.toml、Streamlit CloudではSecrets管理画面で
設定）の[credentials]セクションから読む——公開リポジトリに平文パスワードが残ることを避ける。
"""

import streamlit as st


def _load_credentials() -> dict[str, str]:
    """
    st.secretsの[credentials]セクションを{ユーザーID: パスワード}として返す。
    secrets.toml自体が無い環境（ローカルで未設定のまま等）ではStreamlitSecretNotFoundErrorに
    なるため、その場合は空辞書を返す——fail-closed（誰もログインできない）にするためで、
    誤って認証をスキップする（誰でも入れる）方向にはしない。
    """
    try:
        return dict(st.secrets.get('credentials', {}))
    except Exception:
        return {}


def _authenticate(username: str, password: str) -> bool:
    if not username:
        return False
    return _load_credentials().get(username) == password


def _render_login() -> None:
    st.markdown('## Word_Counter')
    st.caption('ログインしてください')
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        with st.form('login_form'):
            username = st.text_input('ユーザーID')
            password = st.text_input('パスワード', type='password')
            submitted = st.form_submit_button('ログイン', type='primary', use_container_width=True)
            if submitted:
                if _authenticate(username, password):
                    st.session_state['authenticated'] = True
                    st.session_state['username'] = username
                    st.rerun()
                else:
                    st.error('ユーザーIDまたはパスワードが正しくありません')


def require_login() -> None:
    """未ログインならログインフォームを表示してst.stop()する。app.pyの先頭近くで呼ぶ。"""
    st.session_state.setdefault('authenticated', False)
    st.session_state.setdefault('username', None)
    if not st.session_state['authenticated']:
        _render_login()
        st.stop()


def render_logout_button() -> None:
    """サイドバー下部等に置くログアウトボタン。session_stateを全消去して再実行する。"""
    st.caption(f'👤 ログイン中: {st.session_state.get("username")}')
    if st.button('🚪 ログアウト', use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
