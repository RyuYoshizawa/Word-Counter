# Word_Counter 仕様書

## 1. 概要

KH Coder（日本語テキストマイニングツール）の使用実績のうち、実際によく使う機能に絞って再現する独自のStreamlitアプリ。姉妹プロジェクト「After Coder」（`C:\Users\ryu\Documents\after-coding-demo\`）とアーキテクチャ・設計思想を揃え、将来的な連携を見据える。

## 2. 全体構成（ファイル構成）

```
app.py            薄いオーケストレーター（page_config, session_state初期化, sidebar呼び出し, tabs振り分け）
main.py           uv init 定型（未使用）
llm_client.py     After Coderからコピーしたプロバイダ非依存LLM呼び出しモジュール
core/             分析ロジック（Streamlit非依存、単体テスト可能）
  tokenizer.py      Sudachiラッパー（Mode A/C、強制抽出の保護/復元、複合語検出、表記ゆれ適用）
  pos_rules.py      Sudachi品詞タグ → カテゴリのマッピング、既定除外セット
  frequency.py      単語頻度、品詞別語彙リスト、複合語頻度
  network.py        共起行列、Jaccard係数（単語×単語・単語×属性値）、networkx→Plotly変換
  clustering.py     Jaccard距離、scipy linkage/dendrogram
  wordcloud_gen.py  wordcloud.WordCloudラッパー
  crosstab.py       GTインポート解析、クロス集計
  variant_grouping.py  LLM表記ゆれ統合プロンプト/スキーマ
  fonts.py          日本語フォント解決（wordcloud・matplotlibで共有）
  project.py        プロジェクトファイル（.json）のシリアライズ/デシリアライズ
ui/               画面（core/の結果をStreamlitで表示するだけ）
  sidebar.py        設定サイドバー（プロジェクト管理、入力方法3択：テキストファイル/貼り付け/Excel）
  tab_*.py          機能別タブ
                  （日本語フォントはWindows標準搭載のNotoSansJP-VF.ttf等を実行時に解決、同梱ファイルなし）
```

**注**: 当初計画していた`core/jobs.py`（汎用バッチジョブ状態マシン）は、Phase 7のLLM表記ゆれ統合が単発呼び出しで済んだため未作成（5.2節参照、必要になった時点で追加）。

## 3. 依存ライブラリ

| ライブラリ | 用途 |
|---|---|
| streamlit | UIフレームワーク |
| sudachipy + sudachidict_core | 形態素解析 |
| pandas / openpyxl | 表形式データのI/O |
| networkx / plotly | 共起ネットワークの計算・描画 |
| scipy / matplotlib | クラスター分析（Ward法・Jaccard距離・デンドログラム） |
| wordcloud | ワードクラウド生成 |
| anthropic | LLM呼び出し（表記ゆれ統合） |

## 4. 機能仕様

### 4.0 プロジェクト管理

Word_Counterの作業単位は「プロジェクト」。`st.session_state['project']`が`None`の間はプロジェクト名・概要の入力欄とデータ入力セクションのみが表示され、**プロジェクト名とデータの両方が揃うまで分析タブ（品詞別語彙リスト以降）は一切描画されない**（`app.py`が`st.stop()`でロックする）。プロジェクトが始まったら、サイドバー上部にプロジェクト名を常時表示し、名前・概要はいつでも編集エキスパンダーから変更できる。

- **保存する内容**: `name`・`description`・`input_method`・`documents`（属性込み）・`dict_type`・`forced_terms`・`included_categories`・確定済み`variant_map`。
- **保存しないもの**: APIキー（セキュリティ上、`ui/sidebar.py`の他の設定と違いプロジェクトオブジェクトに含めていない）、トークナイズ結果などの計算済みキャッシュ（`documents`と設定さえあれば毎回安価に再計算でき、古い結果が残るリスクも避けられる）、未確定のLLM提案（`pending_variant_groups`）。
- **形式**: JSON（`.json`）。人が読める、`st.download_button`/`st.file_uploader`と相性が良い。`schema_version`・`saved_at`を含み、将来の形式変更に備える。実装は[core/project.py](core/project.py)の`build_project`/`serialize_project`/`deserialize_project`（Streamlit非依存）。
- **ダウンロード**: サイドバーの「💾 ダウンロード」ボタンで、その時点の全設定・`documents`を反映したJSONを取得できる（毎レンダリングで`st.session_state['project']`を最新状態に同期してからボタンを描画）。
- **再開（アップロード）**: サイドバーの「📂 既存プロジェクトを開く」から`.json`をアップロードすると復元される。ブラウザの仕様上`st.file_uploader`に元のファイルを再セットすることはできないため、**再開時は入力方法によらず一律「貼り付け」として復元する**（`documents`のテキストを改行結合してテキストエリアに事前セット）。ただし「貼り付け」の通常実装はテキストエリアの内容から毎回`documents`を作り直す（属性`attrs`もカスタムIDも失われる）ため、復元直後は`st.session_state['_restored_documents']`（元の`id`/`attrs`を保持）をそのまま使い、ユーザーがテキストエリアを実際に編集した時点で通常の行分割ロジックにフォールバックする（`ui/sidebar.py`の`_render_text_input`）。これにより、手を加えない限り属性情報を含めて完全に復元される。
- **新規開始**: 「🆕 新規開始」ボタンで`project`と関連session_stateをクリア（After Coderの既存リセットボタンと同様、APIキーは保持）。

### 4.1 データアップロード・クリーニング

サイドバーの「入力方法」で3択（テキストファイル/貼り付け/Excel）を切り替える。入力方法によらず、内部では統一形状`documents: list[{'id': str, 'text': str, 'attrs': dict}]`に変換してから後続処理（トークナイズ以降）に渡す（`ui/sidebar.py`）。テキストファイル/貼り付けは改行区切りの各行を1文書とし、`id`は`L0001`形式の自動採番、`attrs`は空dict。

#### 4.1.0 Excelアップロード（ID・属性列あり）
After Coderの「自由回答一覧 Chunk A」列マッピングUIを踏襲。Excelファイルをアップロード → 先頭5行プレビュー → 自由記述列（selectbox）・IDの列（任意、selectbox、未選択なら`L0001`形式で自動採番）・属性として使う列（multiselect、複数選択可・任意）を選択 → 「この内容で読み込む」ボタンで明示的に確定（列選択自体は都度session_stateに反映されるが、`documents`への変換はボタン確定時のみ発生し、After Coderと同じ「選択即反映ではなく明示確定」パターン）。属性値は文字列化して保持し、欠損セルは`attrs`から除外する。属性は集計・共起ネットワークでのマッピングに使われ、単語の判定自体には使われない（After Coderの`attrs`と同じ位置づけ）。実装は[ui/sidebar.py](ui/sidebar.py)の`_render_excel_upload`。

#### 4.1.1 強制抽出（Phase 2）
トークナイズ前の文字列保護方式。強制抽出リストの語句をUnicode私用領域のプレースホルダに置換 → Sudachiでトークナイズ → プレースホルダを元の語句（単一トークン、品詞カテゴリ「強制抽出」）に復元。リストの上にある語句ほど優先され、一度プレースホルダ化された箇所は後続の語句の置換対象にならない（最長一致ではなくリスト順で重なりを解決する、KH Coderの仕様を踏襲）。実装は[core/tokenizer.py](core/tokenizer.py)の`protect_forced_terms`/`restore_forced_tokens`。

#### 4.1.2 LLMによる表記ゆれ・同義語統合（Phase 7）
頻出語（品詞フィルタ適用後の出現数上位80語）をLLMに渡し、表記ゆれ・同義語のグルーピングを提案させる → After Coderの`pending_edit`と同じ「提案 → 内容表示 → ✅確定/❌キャンセル」UIで人が確認してから適用（自動適用しない）。実装は[core/variant_grouping.py](core/variant_grouping.py)（プロンプト・スキーマ・`llm_client.call_llm`呼び出し）と[core/tokenizer.py](core/tokenizer.py)の`apply_variant_map`（確定済みマッピングをトークンの`normalized`フィールドに適用、`surface`/品詞情報は変更しない）。確定した統合ルールは`st.session_state['variant_map']`に蓄積され、以降の全タブの集計に反映される（`app.py`で毎レンダリング時にキャッシュ済みトークンへ適用、再トークナイズ不要）。使用モデルは`claude-haiku-4-5`固定（コスト重視、コーディングモデルほどの精度は不要なタスクのため）。

### 4.2 形態素解析（Sudachi）
sudachidict_core使用（サイドバーでfullに切替可能）。Mode A（短単位、通常の単語）を基本とし、複合語検出にはMode Cとの差分を用いる。

### 4.3 品詞別語彙リスト・単語の出現数（Phase 1、原文コンテキスト表示はPhase 9）
Sudachi品詞タグを`pos_rules.py`でKH Coder風カテゴリにマッピング。助詞・助動詞等は既定で除外、ひらがなのみの語は「-B」区分としてまとめて除外可能にする（KH Coderの設計を踏襲）。全タブ共通で品詞フィルタの内容を`ui/common.py`の`pos_filter_caption`でキャプション表示する。

**原文コンテキスト表示（Phase 9）**: 左に「単語・品詞・出現数」の表（`st.dataframe(on_select='rerun', selection_mode='single-row')`で行クリックを検知）、右に選択語を含む原文一覧（[core/context.py](core/context.py)の`find_word_contexts`で前後20語を切り出し、該当語を太字表示）。「複合語を混在表示する」チェックボックスで複合語も同じ表に含められる（品詞カテゴリに「（複）」を付記、[core/pos_rules.py](core/pos_rules.py)の`display_category`）。

### 4.4 複合語の出現数（Phase 3、原文コンテキスト表示はPhase 9）
同一テキストをMode AとMode Cでそれぞれトークナイズし、Cのスパンが複数のAトークンにまたがる箇所を複合語候補として頻度集計。実装は[core/tokenizer.py](core/tokenizer.py)の`detect_compounds`（Sudachiの`begin()`/`end()`文字オフセットで両モードの範囲を突き合わせる）。強制抽出済みの語句はプレースホルダ1文字としてMode A/C双方に同一に現れるため、複合語候補としては検出されない。複合語も実際のSudachi品詞（`is_compound=True`、品詞情報自体は保持）を持つため、他タブと同じ品詞フィルタが適用される。単語一覧タブと同じクリック→原文コンテキスト表示に対応（前後の文脈にはMode Cでの通しトークン列を使う——複合語だけの抜粋では前後の普通の単語が分からないため）。

### 4.5 ワードクラウド（Phase 1、マスク/色分け/太字/高解像度出力はPhase 10）
`wordcloud`ライブラリ。日本語フォント未指定だと文字化け（豆腐）するため、[core/fonts.py](core/fonts.py)の`resolve_japanese_font`でフォントを解決する。Windows標準搭載の`C:\Windows\Fonts\NotoSansJP-VF.ttf`（無ければ`meiryo.ttc`→`msgothic.ttc`の順にフォールバック）を利用し、無断でのフォントファイルダウンロード・同梱は行わない。同じ関数をクラスター分析のmatplotlibデンドログラム（4.7節）でも共有している。

**マスク形状（Phase 10）**: 円・正方形・長方形・横長楕円・ひし形の5種類（[core/mask_shapes.py](core/mask_shapes.py)、PILで生成、白=除外/黒=描画可能というwordcloudの慣例に合わせる）。

**品詞別4色塗分け（Phase 10）**: After Coderの`CHART_COLORS`（10色）から4色を選び、それぞれに品詞カテゴリを割り当てる（[core/wordcloud_gen.py](core/wordcloud_gen.py)の`make_pos_color_func`、語→カテゴリの対応は`core/frequency.py`の`word_category_map`）。

**モノクロ3段階ネガポジ（Phase 10、実験的機能）**: 単語感情極性対応表（高村ら、`data/pn_ja.dic`、cp932、55125語）による辞書ベースの判定。[core/sentiment.py](core/sentiment.py)の`lookup_polarity`で語の極性値（-1〜1）を引き、しきい値（スライダーで調整可）でポジ＝グレー・ネガ＝ブラック・ニュートラル（辞書に無い語を含む）＝ライトグレーの3色に区分する（`make_sentiment_color_func`）。文脈を考慮したLLM判定（回答単位でのネガポジ）は将来の拡張候補（7節）。

**太字表示（Phase 10）**: NotoSansJP-VF.ttf（可変フォント）はwordcloudの`font_path`が都度読み込むため実行時のウェイト切り替えが効かない。fontToolsの`varLib.instancer`でweight=700の静的インスタンスを生成しテンポラリディレクトリにキャッシュする（[core/fonts.py](core/fonts.py)の`resolve_bold_japanese_font`）。非可変フォント（meiryo.ttc等）は隣接するBold版ファイル（meiryob.ttc）があればそれを使う。

**高解像度出力（Phase 10）**: `WordCloud(scale=...)`で標準/2倍/4倍を選択し、PNGバイト列として`st.download_button`で提供（`core/wordcloud_gen.py`の`to_png_bytes`）。

### 4.6 共起ネットワークマップ（Phase 4、属性マッピング・バグ修正・デザイン刷新はPhase 11）
文書（行 or Excel行）ごとの語の出現有無からJaccard係数を計算、networkxでグラフ構築、Plotlyでインタラクティブに描画。実装は[core/network.py](core/network.py)。サイドバーの「表示設定」で最低出現文書数・対象語数（文書頻度上位）・最大エッジ数・表示幅/高さ（Phase 11で追加）を調整可能。

**単語×属性値マッピング**: Excel入力で属性列が指定されている場合、「属性でマッピング」selectboxが現れる。属性値を単語と同じ土俵の追加ノードとして扱い、語×属性値のJaccard係数エッジも計算する（属性値どうしのペアは計算しない——語を介した関係性の可視化に絞る設計判断）。

**Phase 11でのバグ修正**: (1) 語×語エッジと語×属性値エッジを同じ`max_edges`打ち切りプールで競わせると、属性値エッジ（候補数が少なくJaccard係数も低くなりがち）が埋もれて消える不具合があった（実データで属性値ノードが1個しか出ない事例）→ `build_cooccurrence_edges`が語×語エッジと語×属性値エッジを別々のリストで返し、`build_graph`は語×語エッジのみ`max_word_edges`で絞り込み、語×属性値エッジは全て採用するよう変更。(2) ノードサイズが`10 + freq*2`という無制限の線形式で、出現文書数が多いノードが異常に巨大化する不具合があった → グラフ内最大頻度に対する相対スケール（12〜40px）に変更。

**Phase 11でのデザイン刷新（KH Coderの共起ネットワーク出力を参考）**: 属性値ノードは赤い四角（`#F08080`、`symbol='square'`）。単語ノードは接続している属性値ノードの種類数（Degree）で色分け（0=青、1=オレンジ、2=黄緑、3以上=ティール）。ノードサイズの凡例（ダミートレースでFrequency目盛りを表示）。エッジはJaccard係数で4段階（四分位）にビン分けし太さを変え、各エッジ中点に係数の数値ラベルを表示（トグルで切替可）。属性値ノードが無い場合は単一色・凡例なしの従来表示のまま（完全に後方互換）。実装は[core/network.py](core/network.py)の`_node_trace`/`_bin_edges_by_weight`/`_size_legend_traces`。

### 4.7 クラスター分析（Phase 5、文字サイズ調整・PNG/SVGダウンロードはPhase 12）
Ward法 + Jaccard距離（scipy.cluster.hierarchy）。共起ネットワークと同じ語×文書の出現有無行列を使用。デンドログラムはmatplotlib（`st.pyplot`）で表示、色分けはクラスタ数の目安から閾値を逆算。実装は[core/clustering.py](core/clustering.py)。Ward法は本来ユークリッド距離が前提だが、KH Coderと同じ組み合わせ（Ward＋Jaccard）を再現性のため踏襲している。

**Phase 12での追加**: 文字サイズスライダー（matplotlib標準の`leaf_font_size`）。PNG（DPI 150/300/600から選択）・SVG（ベクター形式、Illustrator等で編集可能）のダウンロードボタン（`figure_to_png_bytes`/`figure_to_svg_bytes`）。

### 4.8 クロス集計（Phase 6は外部GTファイル方式、Phase 13でコードブック方式に全面刷新）
**Phase 13で全面刷新**: 当初（Phase 6）は`document_id, category`形式の外部CSV/Excelをインポートする方式だったが、ユーザーの実際の想定（単語・語群にコードブックを策定して割り振り、既存の属性=Excel由来の`attrs`とクロス集計したい）と乖離していたため、外部ファイル方式（[core/crosstab.py](core/crosstab.py)）を削除し、アプリ内でコードブックを作る方式（新規[core/codebook.py](core/codebook.py)）に置き換えた。

**コードブックの書式**: 「コード名: トリガー1, トリガー2, ...」（1行1コード、`parse_codebook`）。**トリガーの判定は2種類を自動判定**——(1) トリガーが正規化語（`dictionary_form`）の集合に含まれていれば正規化語一致（例: 「教師: 先生, 教員, 教師」でこの3語のいずれかを含む文書がヒット、表記ゆれ・同義語のグルーピングに使う）、(2) それ以外は原文への部分文字列一致（例: 「食べない: 食べない」と「食べたい: 食べたい」は形態素解析の正規化ではどちらも「食べる」に統合されてしまうため、原文の文字列一致で活用の違いを区別する——ユーザーとの相談で「妥協」として合意した設計）。`apply_codebook`が両方式を実装。

**クロス集計**: コードごとに該当する文書集合を`crosstab_codes_by_attr`で属性値ごとの件数表に変換（[core/network.py](core/network.py)の`attr_value_doc_sets`を再利用）。属性情報（Excel由来の`attrs`）が無い場合はその旨を案内するのみで、コードブック機能自体は使えない。

## 5. 裏側の共通基盤

### 5.1 LLM呼び出し（llm_client.py）
After Coderから流用。`make_client`/`call_llm`/`_call_anthropic`/`_parse_json_text`/`calc_cost_jpy`。プロンプトキャッシュ（`cache_control: ephemeral`）、temperature再試行`[0, 0.5]`。Word_Counter固有の変更なし。

### 5.2 バッチジョブ状態マシン（未使用）
1リランにつき1バッチ処理 → `st.rerun()` → 進捗バー＋中断ボタン。Streamlitの同期実行モデルで中断可能なバッチ処理を実現する唯一の方法（After Coderで確立されたパターン）。Phase 7では表記ゆれ統合の候補語を80語に絞り込み単発のLLM呼び出しで完結させたため、このジョブ状態マシンは未使用（7節「今後の計画」参照）。

### 5.3 pending_edit 提案/確認/キャンセルパターン（Phase 7で使用）
LLM提案を`st.session_state['pending_variant_groups']`に保持し、内容表示 → 「✅ 確定する」/「❌ キャンセル」ボタンで人が確認してから`variant_map`に適用。After Coderの`result['pending_edit']`と同じ設計思想（LLM提案を自動適用しない）。

## 5.4 文書リスト中心のトークン化（`documents` → `doc_tokens`）

サイドバーは入力方法（テキストファイル/貼り付け/Excel）によらず統一形状`documents: list[{'id','text','attrs'}]`を返す（4.1節）。`app.py`はこれを唯一の入力源とし、**文書ごとに**`protect_forced_terms`→`tokenize`→`restore_forced_tokens`を行って`doc_tokens`（文書ごとのトークンリスト）を構築する。プレースホルダは文書ごとに独立処理してよい（U+E000から文書内で完結するため文書間の衝突はない）。Phase 1〜3の集計（品詞別語彙リスト、単語の出現数、複合語）が使う全体向けの`tokens`は、`doc_tokens`を連結して導出する（かつてはテキスト全体を別途まるごとトークナイズしていたが、この二重トークナイズは2026-08-13にExcel対応と合わせて解消した）。複合語検出（`detect_compounds`）は全文書の保護済みテキストを改行で結合したものに対して1回だけ実行する（文書境界をまたいだ複合語は通常発生しないため、結合前の挙動と同じ）。`doc_ids`・`doc_attrs`も`documents`から直接導出され、共起ネットワーク（4.6節）の属性マッピングやGTクロス集計（4.8節）で使われる。

## 6. 開発の背景・設計判断メモ

- **形態素解析エンジン**: MeCabではなくSudachiを採用。複合語（Mode A/C差分）の扱いに強みがあるため。
- **強制抽出の実装方式**: Sudachiユーザー辞書（ビルドが必要）ではなく文字列保護方式を選択。Streamlitの「編集したらすぐ再実行」というUXに合わせるため。
- **共起ネットワークの描画**: pyvis（iframe埋め込み）ではなくPlotly（After Coderと同じスタック）を選択。テーマの一貫性とインタラクティブ性を両立。

## 7. 今後の計画

- TermExtract相当の統計的複合語抽出（Mode A/C差分で拾えない新語対応）
- 強制抽出リストのセッション間永続化
- Excelレポートのエクスポート（After Coderの`create_excel`パターンを参考）
- After Coderとの実データ連携（GTインポートの自動変換アダプタ）
- 表記ゆれ統合の候補語数が大きく増えた場合（数百語規模）のバッチジョブ状態マシン対応（5.2節、現状は80語の単発呼び出しで十分なため未実装）
- LLM表記ゆれ統合の実APIキーによるライブ動作確認（この開発環境にAnthropic APIキーが無いため、プロンプト構築・スキーマ・`variant_map`適用ロジックはスクリプトでモック検証済みだが、実際のLLM応答での動作は未確認 — After Coderと同じ「ブラウザE2Eは実際のAPIキーが無いと検証できない」という制約を踏襲）

## 8. 変更履歴

- 2026-08-12: プロジェクト開始。Phase 0（土台構築）完了：`uv init`、依存関係インストール（streamlit, sudachipy, sudachidict_core, pandas, openpyxl, networkx, plotly, scipy, matplotlib, wordcloud, anthropic）、`llm_client.py`をAfter Coderからコピー、`core`/`ui`のディレクトリ構成、`app.py`の骨組み。
- 2026-08-12（続き）: Phase 1（MVP縦スライス）完了。アップロード（.txt/貼り付け）→クリーニング→Sudachi Mode A解析→品詞マッピング→品詞別語彙リスト・単語の出現数・ワードクラウドが一気通貫で動作。ブラウザで実際に日本語テキストを入力して動作確認済み。
  - 単語の見出し語には`normalized_form()`ではなく`dictionary_form()`を採用。検証中に`normalized_form()`が「とても→迚も」「また→又」「いろいろ→色々」「たくさん→沢山」「すぐ→直ぐ」「やっぱり→矢張り」のように常用外の漢字表記へ変換することを発見（動詞・形容詞の活用統合自体は両者とも同じ結果）。`dictionary_form()`なら活用統合はそのままに、この望ましくない漢字化が起きないため切り替えた（[core/tokenizer.py](core/tokenizer.py)）。
  - ワードクラウド用の日本語フォントはWindows標準搭載の`NotoSansJP-VF.ttf`を実行時に解決する方式とし、フォントファイルの同梱・ダウンロードは行わなかった。
- 2026-08-12（続き）: Phase 2（強制抽出）完了。`core/tokenizer.py`の`protect_forced_terms`/`restore_forced_tokens`でUnicode私用領域プレースホルダによる文字列保護方式を実装、サイドバーに強制抽出リストUI、データ準備タブに検出結果（見つかった/見つからなかった語句）のサマリを追加。優先順位（リストの先頭が勝つ、最長一致ではない）・未検出語句の扱いをスクリプトで検証後、ブラウザでも実データにて動作確認。
- 2026-08-12（続き）: Phase 3（複合語の出現数）完了。`core/tokenizer.py`の`detect_compounds`でMode A/C差分による複合語検出を実装、`core/frequency.py`に`compound_frequency_table`を追加、複合語タブに接続。強制抽出との組み合わせ（強制抽出済みの語は複合語として重複検出されないこと）をスクリプトで検証後、ブラウザでも実データにて動作確認。
  - 開発メモ: この環境では`uv run streamlit run`のホットリロードが新規関数の追加を正しく拾わないことがあり（`ImportError`が発生）、`__pycache__`削除＋サーバー再起動で解消することを確認。以降、コア関数を追加した際はサーバーを再起動してから検証する。
- 2026-08-12（続き）: Phase 4（共起ネットワークマップ）完了。文書（行）単位のトークン化基盤（`_doc_tokens_cache`/`_doc_ids_cache`、5.4節参照）を新設し、`core/network.py`でJaccard係数の計算・networkxグラフ構築・Plotly図への変換を実装。5文書のサンプルデータでJaccard係数の計算結果をスクリプト検証後、ブラウザでも実データ（5文書・改行区切り）で動作確認（ノード数6/エッジ数14）。
- 2026-08-12（続き）: Phase 5（クラスター分析）完了。`core/clustering.py`でWard法＋Jaccard距離の階層的クラスタリング（scipy）とデンドログラム描画（matplotlib）を実装。検証中、matplotlibの既定フォント（DejaVu Sans）が日本語グリフを持たずラベルが文字化けすることが判明したため、ワードクラウドと共通の`core/fonts.py`（新設、`wordcloud_gen.py`からフォント解決ロジックを切り出し）を使ってNotoSansJP-VF.ttfをmatplotlibに登録する修正を実施。修正前後で警告の有無をスクリプトで比較検証、実際に生成した画像で日本語ラベルの表示も目視確認してからブラウザでも動作確認（対象語数7/文書数6）。
- 2026-08-12（続き）: Phase 6（GTとのクロス集計）完了。`core/crosstab.py`で`document_id`（行番号ベース）の正規化とGTインポート・クロス集計を実装。数値/文字列/`L`接頭辞ありなしの各表記でのID正規化、列不足時のエラー、実際の集計結果をスクリプトで検証。ブラウザ側はファイル選択ダイアログの自動操作が困難なため、アップロード前の空状態表示とエラーなく動作することのみ確認（パース・集計ロジック自体はスクリプト検証で担保）。
- 2026-08-12（続き）: Phase 7（LLM表記ゆれ統合）完了。`core/variant_grouping.py`（プロンプト・スキーマ・`llm_client.call_llm`呼び出し）と`core/tokenizer.py`の`apply_variant_map`を実装、`tab_cleaning.py`にpending_edit型の提案/確認/キャンセルUIを追加、サイドバーにAPIキー入力欄を新設。`app.py`側では確定済み`variant_map`を毎レンダリング時にキャッシュ済みトークン（`tokens`/`compounds`/`doc_tokens`）へ適用する設計とした（再トークナイズ不要）。この開発環境にAnthropic APIキーが無いため、`groups_to_variant_map`（canonical自己参照の除外を含む）・`apply_variant_map`・プロンプト構築をモックデータでスクリプト検証し、ブラウザでは「APIキー未設定時にボタンが正しく無効化され、クリックしても何も起きない」ことを確認。実LLM応答での動作は未検証（7節）。
- 2026-08-13（新セッション）: ユーザーが実際にアプリを試し、「初号でここまでできるのはすごい」と好評。新要望として、After Coderと同様のID・属性列付きExcelアップロード＋共起ネットワークでの単語×属性マッピングを依頼された。EnterPlanModeで設計（After Coderの`app.py:2141-2220`「自由回答一覧 Chunk A」列マッピングUIを調査した上で計画）。実装内容：
  - **アーキテクチャ変更**: サイドバーが入力方法（テキストファイル/貼り付け/Excel）によらず統一形状`documents: list[{'id','text','attrs'}]`を返すよう`ui/sidebar.py`を全面改修（3択`st.radio`、Excel分岐は列マッピング＋明示確定ボタン）。`app.py`のトークナイズ処理を`documents`中心に再構成し、従来「テキスト全体を別途まるごとトークナイズ」＋「行ごとに再トークナイズ」していた二重処理を解消（5.4節）。
  - **共起ネットワークの属性マッピング**: `core/network.py`の`build_cooccurrence_edges`に`attr_doc_sets`引数を追加し、語×属性値のJaccardエッジを計算できるようにした（属性値どうしのペアは対象外——語を介した関係性の可視化に絞る設計判断）。新規ヘルパー`attr_value_doc_sets`。`to_plotly_figure`は単語（青丸）と属性値（オレンジ菱形）を別トレースで描画し、属性値が存在する場合のみ凡例表示（属性なし時は完全に後方互換）。`tab_network.py`に属性選択selectboxを追加。
  - **検証**: `attr_value_doc_sets`・拡張後の`build_cooccurrence_edges`（word-word/word-attrエッジの存在、attr-attrペアが無いこと）をスクリプト検証。Excel→documents変換ロジック（欠損値の扱い、ID自動採番）を再現テスト。実際にxlsxファイルを書き出し→読み込み→documents変換→トークナイズ→属性付きネットワーク計算まで一気通貫の結合テストをスクリプトで実施、全て成功。ブラウザでは（1）貼り付け入力の回帰確認（データ準備タブが新しい`documents`ベースの文書数/合計文字数表示に切り替わっていることも含む）、（2）Excel選択時の列マッピングUIがエラーなく表示されることを確認（ファイル選択ダイアログの自動操作は引き続き不可のため、実アップロードのブラウザ確認はユーザー自身に委ねる）。
- 2026-08-13（続き）: ユーザーが実際に属性付きExcelをアップロードしたところ`sudachipy.errors.SudachiError: Input is too long, it can't be more than 49149 bytes`でクラッシュ。原因：`app.py`の複合語検出が全文書の保護済みテキストを改行で結合した1本の巨大な文字列を`tok.tokenize()`に一括で渡していたが、**SudachiPyは1回のtokenize呼び出しにつき入力バイト数の上限（約49149バイト、UTF-8換算）を持つ**——スクリプト検証だけで使っていたサンプルテキストは短く、この制限に気づけなかった。Excelの行数が増えると結合テキストが上限を超えて実データで初めて顕在化する典型的な「テスト規模と実データ規模の差」バグ。
  - **修正**: [core/tokenizer.py](core/tokenizer.py)に`_chunk_text_for_sudachi`（安全マージンを取った45000バイト単位で文字境界に沿って分割）を新設し、`tokenize()`・`detect_compounds()`の両方に適用——`detect_compounds`だけでなく、文書ごとに呼ばれる`tokenize()`自体も1文書・1行が極端に長い場合に同じ例外を起こしうるため、根本原因（Sudachiの入力上限という下位ライブラリの制約）に対して両関数を防御的に修正した。分割位置をまたぐ複合語は検出されなくなるが、これは元々存在した「文書境界をまたぐ複合語は検出しない」という設計上の許容範囲と同じ性質の制約。
  - **検証**: 通常サイズのテキスト（1チャンクのまま、分割前と同じ出力になること）と、元のエラーを再現する135000バイトのテキスト（3チャンクに分割され、全チャンクが上限以下、トークナイズ・複合語検出ともにクラッシュしないこと）をスクリプトで確認。
- 2026-08-13（続き）: ユーザーから「プロジェクト」概念の導入を依頼——作業状態を伝える単位が無く、中断・再開もできなかったため。EnterPlanModeで設計（ユーザーの希望を反映し2点確認：①プロジェクト名未入力時は分析タブもロック、②再開時の入力方法保持は不要で「貼り付け」相当への復元で可）。実装内容（4.0節に詳細）：
  - 新規[core/project.py](core/project.py)：`build_project`/`serialize_project`/`deserialize_project`（JSON、`schema_version`検証、APIキー・計算済みキャッシュ・未確定LLM提案は保存対象外）。
  - `ui/sidebar.py`にプロジェクト状態管理を追加：未作成時は「既存プロジェクトを開く」アップロードと名前/概要入力欄、作成後はヘッダー表示・編集・ダウンロード・新規開始ボタン。復元時は`_restored_documents`/`_restored_joined_text`の仕組みで、テキストエリア未編集の間だけ元の`id`/`attrs`を保持した`documents`をそのまま使う（編集した瞬間に通常の行分割にフォールバック）。ついでに、もう使われていなかった`raw_text`関連の配線（`settings['raw_text']`、`st.session_state['raw_text']`）を削除。
  - `app.py`に`if st.session_state.get('project') is None: st.stop()`のロックを追加。
  - **検証**: `serialize_project`/`deserialize_project`の往復・不正入力（壊れたJSON、キー欠損、未来のschema_version）をスクリプトで確認。復元時のテキスト結合・編集検知ロジックもスクリプトで再現テスト。ブラウザでは実際にプロジェクト名+テキストを入力→分析タブがロック解除されることを確認、ダウンロードボタンをクリックして実際にブラウザのネットワークリクエストからJSONの中身を取得し内容が完全に正しいことを確認、「新規開始」ボタンで初期状態に戻ることも確認。アップロードによる実際の再開操作はファイル選択ダイアログの自動操作が引き続き不可のため、ロジックのスクリプト検証に留める。
- 2026-08-13（続き）: ユーザーが実際にダウンロードしたプロジェクトファイル（338文書、教員アンケートの実データ、Excel由来・強制抽出/表記ゆれ統合ルール込み）で「読み込んで再開ができない」と報告。ファイル自体を直接読み込んで検証したところJSONとして完全に正常（`deserialize_project`も問題なく通る）——原因はファイルではなくコード側にあった。
  - **原因**: `st.file_uploader`はアップロード済みファイルをリラン後も保持し続ける仕様のため、`_render_project_start`内で「ファイルがある→復元処理→`st.rerun()`」という条件分岐をファイルの有無だけで判定していると、rerun後も同じファイルが検出され続けて復元処理が繰り返され、`st.session_state['project']`が実際に作られる（`_sync_or_create_project`はこの関数より後で呼ばれる）前に無限ループしてしまう。ボタン（`st.button`はクリックの瞬間だけTrueを返す）で確定させていたExcel読み込みフロー（4.1.0節）には無かった、file_uploaderの状態永続性特有の不具合。
  - **修正**: [ui/sidebar.py](ui/sidebar.py)の`_render_project_start`で、`UploadedFile.file_id`（アップロードごとに一意なID、Streamlit内部実装で確認）を`st.session_state['_loaded_project_file_id']`に記録し、同じfile_idの間は復元処理をスキップするよう修正。新規開始時のリセット対象にも追加。
  - **検証**: ユーザー提供の実ファイルを直接`deserialize_project`に通し、338文書・強制抽出リスト・表記ゆれ統合ルールまで含めて正しくパースされることを確認（バグはファイルではなくコード側にあったことの裏付け）。修正後、クリーンな`streamlit run`起動でエラーが無いことを確認。実際のアップロード操作でのループ再現・解消は、ファイル選択ダイアログの自動操作が不可なためユーザーによる再確認待ち。
- 2026-08-13（続き）: ユーザーが実際にプロジェクトファイルの復元まで確認し、続けて各データ加工タブへの詳細な要望を一括で伝えた。EnterPlanModeで5フェーズ（Phase 9〜13）に分けて設計・実装。

**Phase 9（単語一覧・複合語一覧の原文コンテキスト表示）**: 複合語検出を全文書結合の1本のリストから文書ごとの検出（`doc_compounds`）に変更（原文コンテキスト表示に文書境界の情報が必要なため）。`Token`に`is_compound`フィールドを追加し、複合語も実際のSudachi品詞を保持するよう変更（`pos_rules.display_category`で表示名にのみ「（複）」を付記、フィルタ判定は基本カテゴリのまま）。新規`core/context.py`の`find_word_contexts`で前後20語のコンテキスト抽出。複合語一覧の原文表示にはMode Cでの通しトークン列（`doc_tokens_mode_c`、新規キャッシュ）を使う設計に落ち着いた（`doc_compounds`は複合語だけの抜粋のため前後の普通の単語が分からない、という初期設計の見落としに気づいてその場で修正）。

**Phase 10（ワードクラウド拡張）**: マスク5形状、After Coderの`CHART_COLORS`から品詞別4色塗分け、ユーザー提供の単語感情極性対応表（`pn_ja.dic`、cp932、55125語、`data/`に同梱）によるモノクロ3段階ネガポジ（実験的機能、後日ユーザーから追加要望のあった閾値調整可能な3段階版）、太字表示（可変フォントをfontToolsで静的Bold instanceに変換）、高解像度PNGダウンロード。

**Phase 11（共起ネットワークの修正とデザイン刷新）**: ユーザーが送ってくれたスクリーンショット2枚（現状の不具合＝属性値ノードが1個しか出ず巨大化、希望＝KH Coder風の見た目）を元に診断・設計。語×語エッジと語×属性値エッジの打ち切りプールを分離するバグ修正、ノードサイズの相対スケール化、属性値ノード=赤い四角、単語ノード=Degree（接続属性数）で色分け、サイズ/エッジ太さの凡例、エッジ数値ラベル、表示サイズ指定を実装。

**Phase 12（クラスター分析の出力オプション）**: 文字サイズスライダー、PNG（DPI指定）/SVG（ベクター）ダウンロード。

**Phase 13（クロス集計のコードブック方式への刷新）**: ユーザーから「想定イメージがズレていると思う」と説明を受け、当初の外部GTファイル方式から、アプリ内でコードブックを作りExcel由来の属性とクロス集計する方式に全面刷新。「食べない」「食べたい」のように形態素解析の正規化で区別が消える活用差への対応が課題として挙がり、ユーザーと相談の上「トリガーが正規化語なら見出し語一致、それ以外は原文への部分文字列一致」という自動判定の妥協案で合意（`core/codebook.py`）。旧`core/crosstab.py`は削除。

**共通**: 全タブに品詞フィルタの内容を示すキャプション（`ui/common.py`の`pos_filter_caption`）を追加。実装の過程で複合語タブが品詞フィルタを一切適用していなかった既存の不整合（Phase 3由来）に気づき、`compound_frequency_table`に`included_categories`引数を追加して修正した。

**検証**: 各`core/*.py`の新規/変更関数はスタンドアロンスクリプトで検証（`find_word_contexts`の前後20語切り出し、`is_compound`混在時の表示、複合語のコンテキストにMode Cを使うことの妥当性、感情極性辞書の読み込みと閾値判定、マスク形状生成、太字フォントのfontTools静的インスタンス化、ネットワークの属性値ノード欠落バグ・ノードサイズ上限バグの再現と修正確認、デンドログラムのPNG/SVG出力、コードブックの正規化語一致/部分文字列一致の両方＋クロス集計表）。ブラウザでは各Phase完了ごとにクリーンな`streamlit run`起動でエラーが無いことと、新規UIコントロールが正しくレンダリングされることを確認（キャンバスベースの表クリック操作・ファイルアップロードダイアログは引き続き自動操作不可のため、それらに依存する部分はスクリプト検証で担保）。
- 2026-08-13（続き）: ユーザーが実際にPhase 9〜13を試し、細かな修正依頼を一括で受けた。
  - **出現語一覧**（旧「品詞別語彙リスト・単語の出現数」、タブ名を短縮）: 左右カラムを等幅から`st.columns([1, 2])`に変更し、原文表示側を広く確保（該当する原文の後半が読みにくいという指摘は、前後20語のトークン数自体は`find_word_contexts`をスクリプトで再検証し正確であることを確認済みで、カラム幅の問題だった可能性が高い）。「複合語を混在表示する」チェックボックスを廃止し、「表示: 単語／複合語／混在」のラジオボタンに統一（複合語タブの削除に伴う統合）。複合語のみ表示時、原文コンテキストの検索先を`doc_tokens_mode_c`（Mode Cの通しトークン列）に切り替え——複合語だけの抜粋である`doc_compounds`のまま検索すると前後の文脈が全く別の場所から拾われてしまう不具合があったため。
  - **複合語の出現数タブを削除**。`core/frequency.py`の`compound_frequency_table`（呼び出し元が無くなったため）と`core/crosstab.py`相当の旧関数も整理。`pos_rules.display_category`は複合語の品詞を基本カテゴリ＋「（複）」から、一律「（複）」表記に単純化（フィルタ判定は引き続き基本カテゴリで行う）。
  - **ワードクラウド**: マスク形状の輪郭に沿ってランダムな円を重ね描きし、雲のような凹凸のある輪郭にする`_add_cloud_bumps`を追加（[core/mask_shapes.py](core/mask_shapes.py)）。`prefer_horizontal=1.0`で縦書きを禁止。色選択UIを刷新——16進コードのselectbox＋`st.color_picker(disabled=True)`のプレビューが機能していなかったため、色見本を番号付きで常時表示する`_render_color_legend`（HTML/CSSの静的スウォッチ）に置き換え、色は番号で選択する方式にした。品詞の割当も単一selectboxから`st.multiselect`に変更し、1色に複数品詞を割り当てられるようにした。太字の既定ウェイトを700→600に変更（キャッシュファイル名にウェイト値を含め、古いキャッシュを誤って使い回さないようにした）。
  - **共起ネットワーク**: ノードのテキストラベルを`textposition='top center'`（円の外側）から`'middle center'`（円の中央）に変更し、ノードサイズも文字が収まりやすいよう拡大（12〜40px→22〜60px）。語の文字数に応じてフォントサイズを可変にする調整も追加。「表示設定」エキスパンダー内のコントロールを3列×2行＋単独行×2から、4列×2行に再配置し、縦方向のスペースをおよそ半分以下に圧縮。
  - **検証**: 各変更をスタンドアロンスクリプトで検証（前後20語のトークン数の正確性、複合語の統一表記、色の複数品詞割当、太字ウェイトのキャッシュファイル名、縦書き禁止設定、ノードのテキスト位置とフォントサイズ）。マスク形状は実際に画像として保存し目視で「雲っぽさ」を確認。ブラウザでは全タブがエラー無く新しいUIで表示されることを確認。
  - **副次的な発見**: ユーザーから「既存プロジェクトを開くしかメニューに表示されない」という報告があったが、クリーンなブラウザセッションでは再現せず、ポート8502で2プロセス確認されたものの実際は1つのStreamlitサーバーの親子プロセス（正常）と判明。今日何度もコード変更・サーバー再起動を行った影響で、開きっぱなしのブラウザタブに古いセッション状態が残っていた可能性が高いと判断し、ハードリロードを案内した。
- 2026-08-13（続き）: 本日最後の2件の要望に対応。
  - **アイコン追加**: サイドバー最上部のタイトルを`st.sidebar.title('Word_Counter')`から`st.sidebar.title('👾 Word_Counter')`に変更（ユーザーの指定は画面左最上段）。あわせて`app.py`の`st.set_page_config`に`page_icon='👾'`を追加し、ブラウザタブのファビコンにも同じ絵文字を反映。
  - **ストップワード**: サイドバーに強制抽出と同じ`st.text_area`パターンで「ストップワード」入力欄を新設（強制抽出の直後、品詞フィルタの前）。除外は正規化した見出し語（`Token.normalized`）の完全一致で行う。`core/frequency.py`の`_filter_tokens`（およびそれを使う`pos_frequency_table`/`word_frequency_table`/`word_category_map`）、`core/network.py`の`_doc_word_sets`（`build_cooccurrence_edges`経由）、`core/clustering.py`の`build_word_doc_matrix`に`stopwords`引数を追加し、出現語一覧・ワードクラウド・共起ネットワーク・クラスター分析の集計から除外されるようにした。原文コンテキスト表示（`core/context.py`の`find_word_contexts`が使う`doc_tokens`/`doc_tokens_mode_c`）とクロス集計（コードブックのトリガーは明示的な語なのでストップワードの対象外という設計判断）には適用していない。プロジェクトファイル（`core/project.py`）にも`stopwords`フィールドを追加したが、旧バージョンのプロジェクトファイルとの後方互換のため必須キーには含めず、読み込み時は`project.get('stopwords', [])`で欠損時は空リスト扱いにしている。
  - **検証**: `_filter_tokens`/`_doc_word_sets`/`build_word_doc_matrix`それぞれについて、ストップワード指定前後で対象語が期待通り増減することをスタンドアロンスクリプトで確認（例: 「天気」を4回含むサンプル文書でストップワード指定前は出現語一覧に行があり指定後は消えること、共起ネットワーク・クラスター分析の対象語集合からも除外されること）。ブラウザでも新しいサイドバーUI（ストップワード入力欄が強制抽出の直後に表示されること）とアイコン表示（サイドバータイトル・ブラウザタブ）をクリーンな`streamlit run`起動後に確認、エラー無し。
