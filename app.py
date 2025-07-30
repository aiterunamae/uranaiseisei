import streamlit as st
import os
import pandas as pd
import csv
from datetime import datetime
import pytz
import itertools
import toml
import json
import hashlib
import hmac
import time

# Google GenAI SDKのインポート
try:
    import google.genai as genai
    from google.genai import types
    NEW_SDK = True
except ImportError:
    try:
        import google.generativeai as genai
        NEW_SDK = False
        st.warning("古いライブラリを使用しています。pip install google-genai で新しいライブラリに更新してください。")
    except ImportError:
        st.error("Google GenAI ライブラリがインストールされていません。pip install google-genai を実行してください。")
        st.stop()

# Vertex AI用のインポート
try:
    from google.auth import default
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False

# ページ設定
st.set_page_config(
    page_title="汎用占い生成アプリ",
    page_icon="🔮",
    layout="wide"
)

# 日本時間を取得する関数
def get_japan_time():
    japan_tz = pytz.timezone('Asia/Tokyo')
    return datetime.now(japan_tz).strftime('%Y-%m-%d %H:%M:%S')

# Basic認証関数
def check_password():
    """Basic認証をチェックする関数"""
    def password_entered():
        """パスワードが入力されたときの処理"""
        username = st.session_state["username"]
        password = st.session_state["password"]
        
        # 設定ファイルまたは環境変数から認証情報を取得
        config = load_config()
        
        # デフォルト値
        admin_user = "admin"
        admin_pass = ""
        user_user = "user"
        user_pass = ""
        
        # 設定ファイルから取得
        if config and "auth" in config:
            admin_user = config["auth"].get("admin_username", admin_user)
            admin_pass = config["auth"].get("admin_password", admin_pass)
            user_user = config["auth"].get("user_username", user_user)
            user_pass = config["auth"].get("user_password", user_pass)
        
        # 環境変数またはStreamlit Secretsから取得（優先）
        admin_pass = os.getenv("ADMIN_PASSWORD", admin_pass)
        user_pass = os.getenv("USER_PASSWORD", user_pass)
        
        # Streamlit Secretsから取得（TOML形式）
        if not admin_pass and hasattr(st, 'secrets'):
            try:
                if "auth" in st.secrets and "admin_password" in st.secrets["auth"]:
                    admin_pass = st.secrets["auth"]["admin_password"]
                elif "ADMIN_PASSWORD" in st.secrets:
                    admin_pass = st.secrets["ADMIN_PASSWORD"]
            except:
                pass
        
        if not user_pass and hasattr(st, 'secrets'):
            try:
                if "auth" in st.secrets and "user_password" in st.secrets["auth"]:
                    user_pass = st.secrets["auth"]["user_password"]
                elif "USER_PASSWORD" in st.secrets:
                    user_pass = st.secrets["USER_PASSWORD"]
            except:
                pass
        
        if (username == admin_user and password == admin_pass and admin_pass):
            st.session_state["password_correct"] = True
            st.session_state["user_role"] = "admin"
            del st.session_state["password"]  # パスワードを削除
        elif (username == user_user and password == user_pass and user_pass):
            st.session_state["password_correct"] = True
            st.session_state["user_role"] = "user"
            del st.session_state["password"]  # パスワードを削除
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 初回または認証失敗時
        st.title("ログイン")
        st.text_input("ユーザー名", key="username")
        st.text_input("パスワード", type="password", key="password", on_change=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        # 認証失敗
        st.title("ログイン")
        st.text_input("ユーザー名", key="username")
        st.text_input("パスワード", type="password", key="password", on_change=password_entered)
        st.error("ユーザー名またはパスワードが正しくありません")
        return False
    else:
        # 認証成功
        return True

# 設定ファイル読み込み関数
@st.cache_data
def load_config():
    config = {}
    base_path = os.path.dirname(__file__)
    config_path = os.path.join(base_path, "config.toml")
    
    try:
        if os.path.exists(config_path):
            config = toml.load(config_path)
    except Exception as e:
        pass
    
    return config


# 設定読み込み
config = load_config()

# API Provider設定（デフォルトはVertex AI）
USE_VERTEX_AI = True
vertex_project = ""
vertex_location = "us-central1"

# 設定ファイルまたは環境変数からAPIキーとVertex AI設定を取得
default_api_key = ""
if config and "api" in config:
    if "gemini_api_key" in config["api"]:
        default_api_key = config["api"]["gemini_api_key"]
    if "use_vertex_ai" in config["api"]:
        USE_VERTEX_AI = config["api"]["use_vertex_ai"]
    if "vertex_project" in config["api"]:
        vertex_project = config["api"]["vertex_project"]
    if "vertex_location" in config["api"]:
        vertex_location = config["api"]["vertex_location"]

# Streamlit Secrets、環境変数、設定ファイルの順でAPIキーを取得
api_key = default_api_key

# Streamlit Secretsから取得（最優先）
if hasattr(st, 'secrets'):
    try:
        if "api" in st.secrets:
            if "gemini_api_key" in st.secrets["api"]:
                api_key = st.secrets["api"]["gemini_api_key"]
            if "use_vertex_ai" in st.secrets["api"]:
                USE_VERTEX_AI = st.secrets["api"]["use_vertex_ai"]
            if "vertex_project" in st.secrets["api"]:
                vertex_project = st.secrets["api"]["vertex_project"]
            if "vertex_location" in st.secrets["api"]:
                vertex_location = st.secrets["api"]["vertex_location"]
        elif "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except:
        pass

# 環境変数から取得（次に優先）
if not api_key:
    api_key = os.getenv("GEMINI_API_KEY", "")
if os.getenv("USE_VERTEX_AI", "").lower() == "true":
    USE_VERTEX_AI = True
if os.getenv("VERTEX_PROJECT"):
    vertex_project = os.getenv("VERTEX_PROJECT")
if os.getenv("VERTEX_LOCATION"):
    vertex_location = os.getenv("VERTEX_LOCATION")

# 設定ファイルから取得（最後の手段）
if not api_key:
    api_key = default_api_key

# モデル選択（Google AI用）
google_ai_models = {
    "Gemini 1.5 Flash": "gemini-1.5-flash",
    "Gemini 1.5 Pro": "gemini-1.5-pro",
    "Gemini 2.0 Flash Experimental": "gemini-2.0-flash-exp",
    "Gemini 2.5 Flash Preview 05-20 (無料版)": "models/gemini-2.5-flash-preview-05-20"
}

# モデル選択（Vertex AI用）
vertex_ai_models = {
    "Gemini 1.5 Flash": "gemini-1.5-flash-002",
    "Gemini 1.5 Pro": "gemini-1.5-pro-002",
    "Gemini 2.0 Flash Experimental": "gemini-2.0-flash-exp",
    "Gemini 2.5 Flash Preview 05-20 (従量課金)": "gemini-2.5-flash-preview-05-20",
    "Gemini 2.5 Pro Preview 03-25": "gemini-2.5-pro-preview-03-25"
}

# デフォルトモデルオプション（自動選択モード用）
default_model_options = {**google_ai_models, 
                        "Gemini 2.5 Flash Preview 05-20 (従量課金)": vertex_ai_models["Gemini 2.5 Flash Preview 05-20 (従量課金)"],
                        "Gemini 2.5 Pro Preview 03-25": vertex_ai_models["Gemini 2.5 Pro Preview 03-25"]}

# 初期設定
model_options = default_model_options

# 管理者ツール（adminでログインした時のみ表示）
with st.sidebar:
    if "user_role" in st.session_state and st.session_state["user_role"] == "admin":
        if st.checkbox("管理者ツール", key="admin_mode"):
            st.header("管理者設定")
            
            # API Provider選択
            st.subheader("API Provider設定")
            
            # 自動選択モード
            auto_select_provider = st.checkbox(
                "APIプロバイダーを自動選択",
                value=True,
                key="auto_select_provider",
                help="モデルに応じて最適なAPIプロバイダーを自動選択します（2.5 Pro: Vertex AI、その他: Google AI）"
            )
            
            if auto_select_provider:
                st.info("🤖 自動選択モード: 2.5 Pro・従量課金版はVertex AI、それ以外はGoogle AIを使用します")
                # モデルオプションは両方のプロバイダーから結合
                model_options = default_model_options
            else:
                # 手動選択モード
                api_provider = st.radio(
                    "API Provider",
                    ["Google AI", "Vertex AI"],
                    index=1 if USE_VERTEX_AI else 0,
                    help="Google AI（APIキー）またはVertex AI（GCPプロジェクト）を選択"
                )
                USE_VERTEX_AI = (api_provider == "Vertex AI")
                
                # APIプロバイダーに応じてモデルオプションを切り替え
                if USE_VERTEX_AI:
                    model_options = vertex_ai_models
                else:
                    model_options = google_ai_models
            
            # 自動選択モードでもVertex AI設定は必要（2.5 Pro用）
            if auto_select_provider or USE_VERTEX_AI:
                with st.expander("Vertex AI設定（2.5 Pro用）", expanded=not auto_select_provider):
                    if not VERTEX_AI_AVAILABLE:
                        st.warning("Vertex AI用のライブラリがインストールされていません。pip install google-auth を実行してください。")
                    
                    vertex_project = st.text_input(
                        "GCP Project ID",
                        value=vertex_project,
                        help="Vertex AIを使用するGCPプロジェクトのID"
                    )
                    
                    vertex_location = st.selectbox(
                        "リージョン",
                        ["us-central1", "us-west1", "us-east1", "europe-west1", "asia-northeast1"],
                        index=0 if vertex_location == "us-central1" else ["us-central1", "us-west1", "us-east1", "europe-west1", "asia-northeast1"].index(vertex_location) if vertex_location in ["us-west1", "us-east1", "europe-west1", "asia-northeast1"] else 0,
                        help="Vertex AIのリージョン"
                    )
            
            # 自動選択モードでもGoogle AI設定は必要（その他のモデル用）
            if auto_select_provider or not USE_VERTEX_AI:
                with st.expander("Google AI設定（2.5 Pro以外用）", expanded=not auto_select_provider):
                    api_key = st.text_input(
                        "Gemini API Key",
                        value=api_key,
                        type="password",
                        help="Google AI StudioからAPIキーを取得してください（config.tomlで事前設定可能）"
                    )
        
        # システムプロンプト設定（管理者ツール内）
        default_system_prompt = ""
        if config and "prompts" in config and "default_system_prompt" in config["prompts"]:
            default_system_prompt = config["prompts"]["default_system_prompt"]
        
        # Streamlit Secretsからシステムプロンプトを取得
        if not default_system_prompt and hasattr(st, 'secrets'):
            try:
                if "prompts" in st.secrets and "default_system_prompt" in st.secrets["prompts"]:
                    default_system_prompt = st.secrets["prompts"]["default_system_prompt"]
            except:
                pass
        
        system_prompt = st.text_area(
            "システムプロンプト",
            value=default_system_prompt,
            height=150,
            placeholder="占い用のシステムプロンプトを入力してください...",
            help="占いの回答スタイルや役割を定義するプロンプトです（config.tomlで事前設定可能）"
        )
    else:
        # 管理者ツールが無効の場合はデフォルトのシステムプロンプトを使用
        default_system_prompt = ""
        if config and "prompts" in config and "default_system_prompt" in config["prompts"]:
            default_system_prompt = config["prompts"]["default_system_prompt"]
        
        # Streamlit Secretsからシステムプロンプトを取得
        if not default_system_prompt and hasattr(st, 'secrets'):
            try:
                if "prompts" in st.secrets and "default_system_prompt" in st.secrets["prompts"]:
                    default_system_prompt = st.secrets["prompts"]["default_system_prompt"]
            except:
                pass
        
        system_prompt = default_system_prompt
        
        # 管理者以外も自動選択モードで無料版と従量課金版を選べるようにする
        model_options = default_model_options

if (api_key and vertex_project) or (api_key or (USE_VERTEX_AI and vertex_project)):
    if NEW_SDK:
        # 新しいSDKの場合 - 両方のクライアントを初期化
        google_ai_client = None
        vertex_ai_client = None
        
        # Google AIクライアントの初期化
        if api_key:
            google_ai_client = genai.Client(api_key=api_key)
        
        # Vertex AIクライアントの初期化
        if vertex_project:
            # Streamlit Secretsからサービスアカウント認証情報を取得
            credentials = None
            if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
                try:
                    # Vertex AI用のスコープを設定
                    scopes = [
                        'https://www.googleapis.com/auth/cloud-platform',
                        'https://www.googleapis.com/auth/generative-language'
                    ]
                    credentials = service_account.Credentials.from_service_account_info(
                        dict(st.secrets["gcp_service_account"]),
                        scopes=scopes
                    )
                except Exception as e:
                    st.error(f"Streamlit Secretsからの認証情報の読み込みに失敗しました: {e}")
            
            # Vertex AI用のクライアント設定
            if credentials:
                # Secretsからの認証情報を使用
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = ''  # 環境変数をクリア
                vertex_ai_client = genai.Client(
                    vertexai=True,
                    project=vertex_project,
                    location=vertex_location,
                    credentials=credentials
                )
            else:
                # デフォルトの認証情報を使用（環境変数またはgcloud）
                vertex_ai_client = genai.Client(
                    vertexai=True,
                    project=vertex_project,
                    location=vertex_location
                )
        
        # デフォルトクライアントの設定
        if USE_VERTEX_AI and vertex_ai_client:
            client = vertex_ai_client
        elif google_ai_client:
            client = google_ai_client
        else:
            client = None
    else:
        # 古いSDKの場合（Google AIのみ）
        if USE_VERTEX_AI:
            st.error("Vertex AIは新しいSDKでのみサポートされています。pip install google-genai を実行してください。")
        else:
            genai.configure(api_key=api_key)


# Basic認証チェック
if not check_password():
    st.stop()

# 認証成功後のメイン画面
st.title("🔮 汎用占い生成")

# ユーザー情報表示
if "user_role" in st.session_state:
    with st.sidebar:
        st.success(f"ログイン中: {st.session_state['user_role']}")
        if st.button("ログアウト"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        

if api_key or (USE_VERTEX_AI and vertex_project):
    st.header("🔮 占い設定")
    
    # ===============================
    # 1. プリセット管理セクション
    # ===============================
    with st.expander("🎯 プリセット管理", expanded=False):
        # プリセットデータをセッション状態で管理
        if 'presets' not in st.session_state:
            st.session_state.presets = {}
        
        if 'selected_preset' not in st.session_state:
            st.session_state.selected_preset = None
        
        # ファイル操作セクション
        st.divider()
        st.subheader("📁 ファイル操作")
        
        col_import, col_export = st.columns(2)
        
        with col_import:
            st.write("📤 **インポート**")
            uploaded_preset = st.file_uploader(
                "JSONファイルを選択",
                type=['json'],
                key="preset_upload"
            )
            
            if uploaded_preset is not None:
                # ファイルが既に処理されたかチェック
                file_hash = hashlib.md5(uploaded_preset.read()).hexdigest()
                uploaded_preset.seek(0)  # ファイルポインタをリセット
                
                if 'last_uploaded_preset_hash' not in st.session_state or st.session_state.last_uploaded_preset_hash != file_hash:
                    try:
                        preset_content = json.loads(uploaded_preset.read().decode('utf-8'))
                        # クリーンなプリセットデータのみを抽出
                        cleaned_presets = {}
                        for name, data in preset_content.items():
                            cleaned_presets[name] = {
                                'rules': data.get('rules', ''),
                                'tone': data.get('tone', ''),
                                'created': data.get('created', data.get('last_updated', get_japan_time()))
                            }
                        # 既存のプリセットにマージ（上書き）
                        for name, data in cleaned_presets.items():
                            st.session_state.presets[name] = data
                        
                        st.session_state.last_uploaded_preset_hash = file_hash
                        st.success(f"{len(cleaned_presets)}個のプリセットをインポートしました")
                    except Exception as e:
                        st.error(f"インポートエラー: {str(e)}")
        
        with col_export:
            st.write("📥 **エクスポート**")
            if st.session_state.presets:
                # エクスポート用のデータを作成（不要なキーを除外）
                export_data = {}
                for name, data in st.session_state.presets.items():
                    export_data[name] = {
                        'rules': data.get('rules', ''),
                        'tone': data.get('tone', ''),
                        'last_updated': data.get('last_updated', data.get('created', get_japan_time()))
                    }
                
                # デバッグ情報を表示
                with st.expander("エクスポートデータの確認", expanded=False):
                    st.json(export_data)
                
                json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 JSONファイルをダウンロード",
                    data=json_str,
                    file_name=f"presets_{get_japan_time().replace(':', '').replace('-', '').replace(' ', '_')}.json",
                    mime="application/json",
                    use_container_width=True
                )
            else:
                st.info("プリセットがありません")
        
        # プリセット選択セクション
        if st.session_state.presets:
            st.divider()
            st.subheader("🎯 プリセット選択")
            
            col_select, col_clear = st.columns([3, 1])
            
            with col_select:
                # ドロップダウンでプリセットを選択
                preset_names = list(st.session_state.presets.keys())
                
                # 現在選択中のプリセットをデフォルトに
                if st.session_state.selected_preset and st.session_state.selected_preset in preset_names:
                    default_index = preset_names.index(st.session_state.selected_preset)
                else:
                    default_index = 0
                
                selected_preset_name = st.selectbox(
                    "プリセットを選択",
                    preset_names,
                    index=default_index,
                    format_func=lambda x: f"{x}（選択中）" if x == st.session_state.selected_preset else x
                )
                
                # 選択したプリセットの情報を表示
                preset_info = st.session_state.presets[selected_preset_name]
                
            
            with col_clear:
                # 適用ボタンを右側に配置（高さ調整のため空白を削除）
                if st.button("✅ このプリセットを適用", type="primary", use_container_width=True):
                    # プリセットを適用
                    st.session_state['preset_user_rules_input'] = preset_info.get('rules', '')
                    st.session_state['preset_user_tone_input'] = preset_info.get('tone', '')
                    st.session_state['user_rules'] = preset_info.get('rules', '')
                    st.session_state['user_tone'] = preset_info.get('tone', '')
                    st.session_state.selected_preset = selected_preset_name
                    st.success(f"✅ プリセット「{selected_preset_name}」を適用しました")
                    st.rerun()
                
                # 選択解除ボタンを常時表示（選択中でない場合はグレーアウト）
                if st.button("❌ 選択解除", 
                           use_container_width=True,
                           disabled=st.session_state.selected_preset is None):
                    st.session_state.selected_preset = None
                    # ルール設定とトンマナ設定も空欄に戻す
                    st.session_state.preset_user_rules_input = ""
                    st.session_state.preset_user_tone_input = ""
                    st.session_state.user_rules = ""
                    st.session_state.user_tone = ""
                    st.rerun()
        
        # プリセット編集セクション
        st.divider()
        st.subheader("✏️ ルール＆トンマナ編集", help="占い生成の追加ルールやトーン&マナーを設定できます。")
        
        # プロンプト設定をここに統合
        
        col_rules, col_tone = st.columns(2)
        
        with col_rules:
            # セッション状態の初期化
            if 'preset_user_rules_input' not in st.session_state:
                st.session_state.preset_user_rules_input = st.session_state.get('user_rules', "")
            
            st.text_area(
                "ルール設定",
                height=150,
                placeholder="例：必ず前向きな内容にする、専門用語は使わない、等",
                help="占い生成時の追加ルールを記入してください",
                key="preset_user_rules_input"
            )
        
        with col_tone:
            # セッション状態の初期化
            if 'preset_user_tone_input' not in st.session_state:
                st.session_state.preset_user_tone_input = st.session_state.get('user_tone', "")
            
            st.text_area(
                "トーン&マナー設定",
                height=150,
                placeholder="例：親しみやすい口調で、絵文字を使用しない、等",
                help="占いの文体やトーンの指定を記入してください",
                key="preset_user_tone_input"
            )
        
        col_save1, col_divider, col_save2 = st.columns([5, 0.2, 5])
        
        with col_save1:
            # 上書き保存
            if st.session_state.selected_preset:
                if st.button(
                    f"🔄 「{st.session_state.selected_preset}」を上書き更新",
                    type="secondary",
                    use_container_width=True
                ):
                    # 現在の設定で上書き
                    rules = st.session_state.get('preset_user_rules_input', '')
                    tone = st.session_state.get('preset_user_tone_input', '')
                    
                    # プリセットを直接更新
                    if 'presets' not in st.session_state:
                        st.session_state.presets = {}
                    
                    st.session_state.presets[st.session_state.selected_preset] = {
                        'rules': rules,
                        'tone': tone,
                        'last_updated': get_japan_time()
                    }
                    
                    st.success(f"✅ プリセット「{st.session_state.selected_preset}」を更新しました")
                    st.rerun()
                
                # 削除ボタンを上書き更新の下に配置
                if st.button(
                    f"🗑️ 「{st.session_state.selected_preset}」を削除",
                    type="secondary",
                    use_container_width=True
                ):
                    del st.session_state.presets[st.session_state.selected_preset]
                    st.session_state.selected_preset = None
                    st.success("✅ プリセットを削除しました")
                    st.rerun()
            else:
                st.info("🔄 上書き保存にはプリセットを選択してください")
        
        with col_divider:
            # 縦の仕切り線
            st.markdown("<div style='border-left: 2px solid #ddd; height: 80px; margin: 0 auto;'></div>", unsafe_allow_html=True)
        
        with col_save2:
            # 新規保存
            preset_name = st.text_input(
                "",
                placeholder="新規プリセット名",
                key="new_preset_name",
                label_visibility="collapsed"
            )
            
            if st.button("➕ 新規保存", type="primary", use_container_width=True, disabled=not preset_name):
                if preset_name in st.session_state.presets:
                    st.error(f"プリセット名「{preset_name}」は既に存在します")
                else:
                    # 新規保存
                    st.session_state.presets[preset_name] = {
                        'rules': st.session_state.get('preset_user_rules_input', ''),
                        'tone': st.session_state.get('preset_user_tone_input', ''),
                        'created': get_japan_time()
                    }
                    st.session_state.selected_preset = preset_name
                    st.success(f"✅ プリセット「{preset_name}」を保存しました")
                    st.rerun()
    
    # ===============================
    # 2. キーワード設定セクション
    # ===============================
    with st.expander("📂 キーワードCSV設定", expanded=False):
        st.write("カスタムキーワードCSVをアップロードして、独自のキーワードを使用できます。")
        st.info("CSVファイルの形式：1列目にキーワード名、2列目以降に属性情報を記載してください。")
        
        # セッション状態でカスタムキーワードを管理
        if 'custom_keywords' not in st.session_state:
            st.session_state.custom_keywords = {}
        
        # カスタムキーワードのアップロード
        col1, col2 = st.columns(2)
        
        with col1:
            uploaded_keyword_files = st.file_uploader(
                "キーワードCSVファイルをアップロード",
                type=['csv'],
                accept_multiple_files=True,
                key="keyword_csv_uploader",
                help="複数のCSVファイルをアップロードできます。ファイル名がカテゴリ名として使用されます。"
            )
        
        with col2:
            if uploaded_keyword_files:
                st.write("アップロードされたファイル：")
                for file in uploaded_keyword_files:
                    # ファイル名からカテゴリ名を抽出（拡張子を除く）
                    category_name = file.name.replace('.csv', '').replace('キーワード', '')
                    st.write(f"- {category_name} ({file.name})")
        
        # カスタムキーワードの読み込み
        if uploaded_keyword_files:
            for file in uploaded_keyword_files:
                try:
                    df = pd.read_csv(file, encoding='utf-8')
                    category_name = file.name.replace('.csv', '').replace('キーワード', '')
                    
                    # データ構造を既存の形式に合わせる
                    st.session_state.custom_keywords[category_name] = {
                        "df": df,
                        "columns": list(df.columns),
                        "data": df.to_dict('records')
                    }
                    
                except Exception as e:
                    st.error(f"{file.name}の読み込みに失敗しました: {str(e)}")
            
            if st.session_state.custom_keywords:
                st.success(f"✅ {len(st.session_state.custom_keywords)}個のカスタムキーワードを読み込みました")
        
        # カスタムキーワードのアップロードを必須にする
        if not st.session_state.custom_keywords:
            st.warning("⚠️ キーワードCSVファイルをアップロードしてください。")
    
    # ===============================
    # 3. 基本設定セクション
    # ===============================
    with st.expander("⚙️ AI・モデル設定", expanded=False):
        # モデル選択
        # デフォルトインデックスを探す（無料版を優先）
        default_index = 0
        model_names = list(model_options.keys())
        for i, name in enumerate(model_names):
            if "2.5 Flash Preview 05-20 (無料版)" in name:
                default_index = i
                break
        
        selected_model_name = st.selectbox(
            "使用するモデル",
            options=model_names,
            index=default_index,
            help="使用するGeminiモデルを選択してください（無料版: Google AI、従量課金: Vertex AI）"
        )
        # 自動選択モードの場合は、モデルに応じてAPIプロバイダーを決定
        if "admin_mode" in st.session_state and st.session_state.get("admin_mode"):
            # 管理者ツールが有効な場合は、セッションステートから自動選択モードを取得
            auto_mode = st.session_state.get("auto_select_provider", True)
        else:
            # 管理者ツールが無効な場合は、常に自動選択モード
            auto_mode = True
        
        if auto_mode:
            # 自動選択モード: 2.5 Pro・従量課金版はVertex AI、それ以外はGoogle AI
            if "2.5 Pro" in selected_model_name or "(従量課金)" in selected_model_name:
                USE_VERTEX_AI = True
                selected_model = vertex_ai_models.get(selected_model_name, selected_model_name)
            else:
                USE_VERTEX_AI = False
                selected_model = google_ai_models.get(selected_model_name, selected_model_name)
        else:
            # 手動選択モード: 現在のAPIプロバイダーに応じて正しいモデル名を取得
            if USE_VERTEX_AI:
                selected_model = vertex_ai_models.get(selected_model_name, selected_model_name)
            else:
                selected_model = google_ai_models.get(selected_model_name, selected_model_name)
        
        # 思考機能の設定（Gemini 2.5のみ対応）
        thinking_budget = 0
        if "2.5" in selected_model_name:
            # Gemini 2.5 Proの場合は思考機能の設定を表示しない
            if "Pro" in selected_model_name and USE_VERTEX_AI:
                st.info(f"💡 Gemini 2.5 Pro: 思考機能は自動的に有効になります")
            else:
                # Gemini 2.5 Flash の場合はチェックボックスで制御
                col_thinking1, col_thinking2 = st.columns([1, 3])
                with col_thinking1:
                    enable_thinking = st.checkbox(
                        "思考機能を有効にする",
                        value=False,
                        help="Gemini 2.5の思考機能を有効にします。より詳細な推論が必要な場合に使用してください。"
                    )
                with col_thinking2:
                    if enable_thinking:
                        thinking_budget = st.slider(
                            "思考予算（トークン数）",
                            min_value=1,
                            max_value=4096,
                            value=1024,
                            step=256,
                            help="思考に使用するトークン数を設定します。値が大きいほど深い推論が可能です。"
                        )
                    else:
                        thinking_budget = 0  # チェックボックスがOFFの場合は明示的に0を設定
                
                # デバッグ用：現在の思考機能設定を表示
                thinking_status = "ON" if thinking_budget > 0 else "OFF"
                st.info(f"💡 思考機能: {thinking_status} (トークン予算: {thinking_budget})")
    
    # ===============================
    # 3. 質問入力セクション
    # ===============================
    st.subheader("📝 質問内容")
    
    # 入力モード選択
    input_mode = st.radio(
        "入力モード",
        ["テキスト入力", "CSVファイル入力", "CSV連続モード"],
        horizontal=True,
        help="テキスト入力: 単一の質問を入力 / CSVファイル入力: 複数の質問を個別に処理 / CSV連続モード: 複数の質問を関連した一連の質問として処理"
    )
    
    questions_list = []
    id_list = []  # ID管理用のリスト
    csv_keywords_list = []  # CSV入力モードでのキーワード情報
    
    if input_mode == "テキスト入力":
        # ID入力欄と質問入力欄を横並びに配置
        col_id, col_question = st.columns([1, 3])
        
        with col_id:
            question_id = st.text_input(
                "ID",
                value="",
                placeholder="例: Q001",
                help="質問のIDを入力（省略可）"
            )
        
        with col_question:
            st.write("質問")  # ラベルを表示
        
        question = st.text_area(
            "占いの質問を入力してください",
            height=100,
            placeholder="占いの質問を入力してください...",
            help="占いで答えてもらいたい質問を入力してください",
            label_visibility="collapsed"
        )
        if question:
            questions_list = [question]
            # IDが入力されていない場合はデフォルトIDを使用
            id_list = [question_id if question_id.strip() else "manual_1"]
    elif input_mode == "CSVファイル入力":
        # CSVファイル入力モード
        uploaded_file = st.file_uploader(
            "質問CSVファイルをアップロード",
            type=['csv'],
            help="A列: ID、B列: 質問、C列以降: カテゴリ・キーワード・対象の3列セット（C列: カテゴリ1、D列: キーワード1、E列: 対象1、F列: カテゴリ2、G列: キーワード2、H列: 対象2...）"
        )
        
        if uploaded_file is not None:
            try:
                # CSVファイルを読み込み
                df_questions = pd.read_csv(uploaded_file, encoding='utf-8')
                
                # A列（ID）とB列（質問）を取得
                if len(df_questions.columns) >= 2:
                    id_column = df_questions.iloc[:, 0]  # A列（ID）
                    questions_column = df_questions.iloc[:, 1]  # B列（質問）
                    
                    # IDと質問のペアを作成
                    questions_list = []
                    id_list = []
                    csv_keywords_list = []  # CSVから読み込んだキーワード情報
                    
                    for idx in range(len(df_questions)):
                        if pd.notna(questions_column.iloc[idx]) and str(questions_column.iloc[idx]).strip():
                            questions_list.append(str(questions_column.iloc[idx]))
                            # IDがない場合は行番号を使用
                            id_value = str(id_column.iloc[idx]) if pd.notna(id_column.iloc[idx]) else f"row_{idx+1}"
                            id_list.append(id_value)
                            
                            # C列以降のキーワード情報を読み取り（最大4カテゴリ）
                            row_keywords = []
                            for i in range(4):  # 最大4カテゴリ
                                cat_col = 2 + i * 3  # C列, F列, I列, L列（カテゴリ）
                                key_col = 3 + i * 3  # D列, G列, J列, M列（キーワード）
                                who_col = 4 + i * 3  # E列, H列, K列, N列（対象）
                                
                                if cat_col < len(df_questions.columns) and key_col < len(df_questions.columns):
                                    category = df_questions.iloc[idx, cat_col]
                                    keyword = df_questions.iloc[idx, key_col]
                                    # 対象列がある場合は読み取り、なければデフォルトで「あなた」
                                    who = df_questions.iloc[idx, who_col] if who_col < len(df_questions.columns) else "あなた"
                                    
                                    if pd.notna(category) and pd.notna(keyword):
                                        who_str = str(who).strip() if pd.notna(who) else "あなた"
                                        # 対象の検証
                                        if who_str not in ["あなた", "あの人", "相性"]:
                                            who_str = "あなた"  # 無効な値の場合はデフォルト
                                        row_keywords.append((str(category).strip(), str(keyword).strip(), who_str))
                            
                            csv_keywords_list.append(row_keywords)
                    
                    if questions_list:
                        st.success(f"✅ {len(questions_list)}個の質問を読み込みました")
                        
                        # キーワード指定の有無を確認
                        has_keywords = any(len(kw) > 0 for kw in csv_keywords_list)
                        if has_keywords:
                            st.info("📋 CSVファイルにキーワード指定が含まれています（CSV優先モード）")
                        
                        # プレビュー表示
                        with st.expander("質問プレビュー", expanded=False):
                            for i, (q_id, q, kws) in enumerate(zip(id_list[:5], questions_list[:5], csv_keywords_list[:5]), 1):  # 最初の5個のみ表示
                                preview_text = f"{i}. ID: {q_id} - {q}"
                                if kws:
                                    kw_text = ", ".join([f"{who}の{cat}:{kw}" for cat, kw, who in kws])
                                    preview_text += f" [キーワード: {kw_text}]"
                                st.text(preview_text)
                            if len(questions_list) > 5:
                                st.text(f"... 他 {len(questions_list) - 5} 個")
                    else:
                        st.warning("有効な質問が見つかりませんでした")
                else:
                    st.error("CSVファイルに2列以上必要です（A列: ID, B列: 質問）")
                    
            except Exception as e:
                st.error(f"CSVファイルの読み込みに失敗しました: {str(e)}")
        else:
            st.info("CSVファイルをアップロードしてください")
    else:  # CSV連続モード
        # CSV連続モード
        st.info("CSV連続モード：複数の質問を関連した一連の質問として処理します。キーワードは画面で選択してください。")
        
        uploaded_file = st.file_uploader(
            "質問CSVファイルをアップロード（連続モード）",
            type=['csv'],
            help="A列: ID、B列: 質問のみ。キーワードは画面で選択します。"
        )
        
        if uploaded_file is not None:
            try:
                # CSVファイルを読み込み
                df_questions = pd.read_csv(uploaded_file, encoding='utf-8')
                
                # A列（ID）とB列（質問）を取得
                if len(df_questions.columns) >= 2:
                    id_column = df_questions.iloc[:, 0]  # A列（ID）
                    questions_column = df_questions.iloc[:, 1]  # B列（質問）
                    
                    # IDと質問のペアを作成
                    questions_list = []
                    id_list = []
                    
                    for idx in range(len(df_questions)):
                        if pd.notna(questions_column.iloc[idx]) and str(questions_column.iloc[idx]).strip():
                            questions_list.append(str(questions_column.iloc[idx]))
                            # IDがない場合は行番号を使用
                            id_value = str(id_column.iloc[idx]) if pd.notna(id_column.iloc[idx]) else f"row_{idx+1}"
                            id_list.append(id_value)
                    
                    if questions_list:
                        st.success(f"✅ {len(questions_list)}個の質問を読み込みました（連続処理モード）")
                        
                        # プレビュー表示
                        with st.expander("質問プレビュー", expanded=False):
                            for i, (q_id, q) in enumerate(zip(id_list[:5], questions_list[:5]), 1):  # 最初の5個のみ表示
                                st.text(f"{i}. ID: {q_id} - {q}")
                            if len(questions_list) > 5:
                                st.text(f"... 他 {len(questions_list) - 5} 個")
                    else:
                        st.warning("有効な質問が見つかりませんでした")
                else:
                    st.error("CSVファイルに2列以上必要です（A列: ID, B列: 質問）")
                    
            except Exception as e:
                st.error(f"CSVファイルの読み込みに失敗しました: {str(e)}")
        else:
            st.info("CSVファイルをアップロードしてください")
    
    # ===============================
    # 4. キーワード設定セクション
    # ===============================
    st.subheader("🔍 キーワード設定")
    
    # セッション状態でカテゴリリストを管理
    if 'keyword_categories' not in st.session_state:
        # カスタムキーワードがある場合は最初のカテゴリを設定
        if st.session_state.custom_keywords:
            st.session_state.keyword_categories = [list(st.session_state.custom_keywords.keys())[0]]
        else:
            st.session_state.keyword_categories = []
    
    # カテゴリ管理ボタン
    col_info, col_add, col_remove = st.columns([2, 1, 1])
    with col_info:
        st.info(f"現在のカテゴリ数: {len(st.session_state.keyword_categories)}/4")
    with col_add:
        if st.button("➕ 追加", disabled=len(st.session_state.keyword_categories) >= 4 or not st.session_state.custom_keywords):
            if len(st.session_state.keyword_categories) < 4 and st.session_state.custom_keywords:
                default_category = list(st.session_state.custom_keywords.keys())[0]
                st.session_state.keyword_categories.append(default_category)
                st.rerun()
    with col_remove:
        if st.button("➖ 削除", disabled=len(st.session_state.keyword_categories) <= 1):
            if len(st.session_state.keyword_categories) > 1:
                st.session_state.keyword_categories.pop()
                st.rerun()
    
    # カスタムキーワードが必須
    if st.session_state.custom_keywords:
        category_types = list(st.session_state.custom_keywords.keys())
        keywords = st.session_state.custom_keywords
    else:
        st.error("キーワードCSVファイルをアップロードしてください。")
        st.stop()
    
    who_types = ["あなた", "あの人", "相性"]  # 対象の選択肢
    selected_categories = []
    selected_values = []
    selected_who = []  # 誰の情報を保存
    
    # グリッド表示（2×2）
    num_categories = len(st.session_state.keyword_categories)
    
    # 2列のグリッドで表示
    for row in range(0, num_categories, 2):
        cols = st.columns(2)
        
        for col_idx in range(2):
            idx = row + col_idx
            if idx < num_categories:
                with cols[col_idx]:
                    # カード風にするためにexpanderを使用（常に展開）
                    with st.expander(f"カテゴリ {idx + 1}", expanded=True):
                        # カテゴリアイコンを種類に応じて変更
                        icon_map = {"ハウス": "🏠", "サイン": "♈", "天体": "🌟", "エレメント": "🔥", "MP軸": "🔗", "タロット": "🃏"}
                        current_type = st.session_state.keyword_categories[idx]
                        icon = icon_map.get(current_type, "🔮")
                        
                        # アイコン付きのタイトル
                        st.markdown(f"### {icon} カテゴリ {idx + 1}")
                        
                        # 種類選択
                        # 現在の選択がリストに存在しない場合はデフォルトを使用
                        current_category = st.session_state.keyword_categories[idx]
                        if current_category not in category_types:
                            current_category = category_types[0]
                            st.session_state.keyword_categories[idx] = current_category
                        
                        category_type = st.selectbox(
                            "種類",
                            category_types,
                            index=category_types.index(current_category),
                            key=f"category_type_{idx}",
                            label_visibility="visible"
                        )
                        st.session_state.keyword_categories[idx] = category_type
                        
                        # 誰の情報とキーワード選択を横並びに配置
                        col_who, col_keyword = st.columns([1, 2])
                        
                        with col_who:
                            who_for = st.selectbox(
                                "対象",
                                who_types,
                                key=f"who_{idx}",
                                help="このキーワードが誰に関するものかを選択"
                            )
                        
                            # キーワード選択
                            if category_type in keywords:
                                # キーワードリストを作成（1列目の値 + "すべて"）
                                keyword_data = keywords[category_type]["data"]
                                first_column = keywords[category_type]["columns"][0] if keywords[category_type]["columns"] else "name"
                                keyword_list = ["すべて"] + [item[first_column] for item in keyword_data if first_column in item]
                                
                                selected_value = st.selectbox(
                                    "キーワード",
                                    keyword_list,
                                    key=f"keyword_{idx}",
                                    label_visibility="visible"
                                )
                            else:
                                selected_value = st.selectbox(
                                    "キーワード",
                                    ["データなし"],
                                    key=f"keyword_{idx}",
                                    label_visibility="visible"
                                )
                        
                        selected_categories.append(category_type)
                        selected_values.append(selected_value)
                        selected_who.append(who_for)
    
    # ===============================
    # 5. 出力設定セクション
    # ===============================
    with st.expander("📄 出力設定", expanded=True):
        col_length, col_summary = st.columns(2)
        
        with col_length:
            answer_length = st.number_input(
                "回答文字数",
                min_value=50,
                max_value=2000,
                value=300,
                step=50,
                help="回答の文字数を指定してください"
            )
        
        with col_summary:
            summary_length = st.number_input(
                "サマリ文字数",
                min_value=20,
                max_value=500,
                value=20,
                step=1,
                help="サマリの文字数を指定してください"
            )
        
        # CSVファイル名設定
        custom_filename = st.text_input(
            "CSVファイル名（拡張子なし）",
            value="占い結果",
            help="保存するCSVファイルの名前を入力してください（拡張子は自動で付きます）"
        )
    
    # キーワード読み込みは既にキーワード設定セクションで行っているため不要
    
    # ===============================
    # 5. 実行ボタン
    # ===============================
    st.markdown("---")
    if st.button("🚀 占い回答を生成", type="primary", use_container_width=True):
        if not system_prompt:
            st.error("システムプロンプトを入力してください")
        elif not questions_list:
            if input_mode == "テキスト入力":
                st.error("質問を入力してください")
            else:
                st.error("CSVファイルをアップロードして質問を読み込んでください")
        else:
            # 組み合わせ生成
            keyword_combinations = []
            who_combinations = []  # 誰の情報の組み合わせ
            
            # 各カテゴリの値リストを作成
            value_lists = []
            who_lists = []  # 誰の情報のリスト
            for idx, (category_type, selected_value, selected_who_value) in enumerate(zip(selected_categories, selected_values, selected_who)):
                if selected_value == "すべて":
                    # カスタムキーワードモード
                    if category_type in keywords:
                        keyword_data = keywords[category_type]["data"]
                        first_column = keywords[category_type]["columns"][0] if keywords[category_type]["columns"] else "name"
                        all_values = [item[first_column] for item in keyword_data if first_column in item]
                        value_lists.append(all_values)
                    else:
                        value_lists.append([selected_value])
                    # 「すべて」の場合でも誰の情報は固定
                    who_lists.append([selected_who_value] * len(value_lists[-1]))
                else:
                    value_lists.append([selected_value])
                    who_lists.append([selected_who_value])
            
            # キーワードの組み合わせ生成（動的に対応）
            if value_lists:
                for combination in itertools.product(*value_lists):
                    keyword_combinations.append(combination)
                # 誰の情報も同じ形で組み合わせを作成
                # ただし、「すべて」の場合は特別処理が必要
                who_combinations = [[selected_who[i] for i in range(len(selected_who))] for _ in keyword_combinations]
            
            # 質問×キーワードの全組み合わせを生成（IDも含める）
            total_combinations = []
            
            # CSV入力でキーワード指定がある場合の処理
            if input_mode == "CSVファイル入力" and csv_keywords_list and any(len(kw) > 0 for kw in csv_keywords_list):
                # CSVのキーワード指定を優先
                has_validation_error = False
                validation_errors = []
                
                for i, question in enumerate(questions_list):
                    question_id = id_list[i] if i < len(id_list) else f"auto_{i+1}"
                    csv_keywords = csv_keywords_list[i] if i < len(csv_keywords_list) else []
                    
                    if csv_keywords:  # CSVにキーワード指定がある場合
                        # CSVのキーワードを検証して組み合わせを作成
                        validated_keywords = []
                        error_keywords = []
                        
                        for cat_name, kw_name, who_name in csv_keywords:
                            # カテゴリ名の検証と正規化
                            valid_category = None
                            valid_keyword = None
                            
                            # カテゴリ名のマッチング
                            if cat_name in category_types:
                                valid_category = cat_name
                            else:
                                # 部分一致や大文字小文字を無視してマッチング
                                for ct in category_types:
                                    if cat_name.lower() in ct.lower() or ct.lower() in cat_name.lower():
                                        valid_category = ct
                                        break
                            
                            if valid_category:
                                # キーワードの検証
                                if valid_category in keywords:
                                    keyword_data = keywords[valid_category]["data"]
                                    first_column = keywords[valid_category]["columns"][0] if keywords[valid_category]["columns"] else "name"
                                    valid_keywords_list = [item[first_column] for item in keyword_data if first_column in item]
                                    
                                    # 全角数字を半角数字に変換する関数
                                    def normalize_numbers(text):
                                        # 全角数字を半角に変換
                                        trans_table = str.maketrans('０１２３４５６７８９', '0123456789')
                                        return text.translate(trans_table)
                                    
                                    # キーワード名を正規化
                                    normalized_kw_name = normalize_numbers(kw_name)
                                    
                                    # キーワードリストも正規化して比較
                                    normalized_keywords_list = [normalize_numbers(kw) for kw in valid_keywords_list]
                                    
                                    # 正規化した値で検索
                                    if normalized_kw_name in normalized_keywords_list:
                                        # 元のリストから一致するものを探す
                                        idx = normalized_keywords_list.index(normalized_kw_name)
                                        valid_keyword = valid_keywords_list[idx]
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                                else:
                                    # カテゴリが存在しない場合
                                    valid_keyword = None
                            
                            # 対象（誰の）の検証
                            valid_who = who_name if who_name in ["あなた", "あの人", "相性"] else "あなた"
                            
                            if valid_category and valid_keyword:
                                validated_keywords.append((valid_category, valid_keyword, valid_who))
                            else:
                                error_keywords.append(f"{cat_name}:{kw_name}")
                        
                        if error_keywords:
                            error_msg = f"ID: {question_id} - 無効なキーワード指定: {', '.join(error_keywords)}"
                            validation_errors.append(error_msg)
                            has_validation_error = True
                        
                        if validated_keywords:
                            # 「すべて」を展開する必要があるかチェック
                            expanded_keywords_list = []
                            has_all_keyword = False
                            
                            for cat, kw, who in validated_keywords:
                                if kw == "すべて":
                                    has_all_keyword = True
                                    # カテゴリに応じて展開
                                    if cat in keywords:
                                        keyword_data = keywords[cat]["data"]
                                        first_column = keywords[cat]["columns"][0] if keywords[cat]["columns"] else "name"
                                        all_keywords = [(cat, item[first_column], who) for item in keyword_data if first_column in item]
                                        expanded_keywords_list.append(all_keywords)
                                    else:
                                        expanded_keywords_list.append([(cat, kw, who)])
                                else:
                                    expanded_keywords_list.append([(cat, kw, who)])
                            
                            if has_all_keyword:
                                # 「すべて」が含まれる場合は総当たりで展開
                                import itertools
                                for combo in itertools.product(*expanded_keywords_list):
                                    # comboは各カテゴリから1つずつ選ばれたタプルのリスト
                                    flattened_combo = list(combo)
                                    keyword_values = [kw for _, kw, _ in flattened_combo]
                                    who_values = [who for _, _, who in flattened_combo]
                                    total_combinations.append((question_id, question, tuple(keyword_values), tuple(who_values), flattened_combo))
                            else:
                                # 「すべて」が含まれない場合はそのまま
                                keyword_values = [kw for _, kw, _ in validated_keywords]
                                who_values = [who for _, _, who in validated_keywords]
                                total_combinations.append((question_id, question, tuple(keyword_values), tuple(who_values), validated_keywords))
                        else:
                            # 有効なキーワードがない場合もエラーとする
                            error_msg = f"ID: {question_id} - キーワードが検証できませんでした"
                            validation_errors.append(error_msg)
                            has_validation_error = True
                    else:
                        # CSVにキーワード指定がない場合は画面設定を使用
                        for j, keyword_combo in enumerate(keyword_combinations):
                            who_combo = who_combinations[j] if j < len(who_combinations) else selected_who
                            total_combinations.append((question_id, question, keyword_combo, tuple(who_combo), None))
                
                # エラーがある場合は処理を停止
                if has_validation_error:
                    st.error("CSVファイルに無効なキーワードが含まれています。")
                    for error in validation_errors:
                        st.error(error)
                    st.info("アップロードされているキーワードCSVと一致するキーワードのみ使用できます。")
                    st.stop()
            else:
                # テキスト入力、CSV連続モード、またはCSVにキーワード指定がない場合
                if input_mode == "CSV連続モード" and len(questions_list) > 0:
                    # CSV連続モード：各キーワードの組み合わせごとに、全質問をまとめて処理
                    for j, keyword_combo in enumerate(keyword_combinations):
                        who_combo = who_combinations[j] if j < len(who_combinations) else selected_who
                        # 質問リスト全体を1つの組み合わせとして追加
                        total_combinations.append(("batch", questions_list, keyword_combo, tuple(who_combo), None))
                else:
                    # 通常モード：各質問×各キーワード組み合わせ
                    for i, question in enumerate(questions_list):
                        question_id = id_list[i] if i < len(id_list) else f"auto_{i+1}"
                        for j, keyword_combo in enumerate(keyword_combinations):
                            who_combo = who_combinations[j] if j < len(who_combinations) else selected_who
                            total_combinations.append((question_id, question, keyword_combo, tuple(who_combo), None))
            
            st.info(f"質問数: {len(questions_list)} × キーワード組み合わせ数: {len(keyword_combinations)} = 合計生成数: {len(total_combinations)}")
            
            # 結果保存用リスト
            results = []
            
            # トークン数カウント用
            total_prompt_tokens = 0
            total_candidates_tokens = 0
            total_thoughts_tokens = 0
            total_cached_tokens = 0
            
            # プログレスバー
            progress_bar = st.progress(0)
            status_text = st.empty()
            token_info = st.empty()
            
            for i, combo in enumerate(total_combinations):
                # 新しいデータ構造: (ID, 質問, キーワード, 誰の情報, CSV検証済みキーワード)
                question_id, current_question, keyword_combination, who_combination, csv_validated_keywords = combo
                is_csv_mode = csv_validated_keywords is not None
                is_batch_mode = question_id == "batch"  # CSV連続モードかどうか
                
                try:
                    # キーワード取得（動的カテゴリに対応）
                    all_keywords = []  # 各カテゴリのキーワードを格納
                    
                    if is_csv_mode and csv_validated_keywords:
                        # CSV優先モード: 検証済みキーワードを使用
                        for category_type, value, who in csv_validated_keywords:
                            keyword_dict = {}
                            
                            # カテゴリタイプに応じてキーワードを取得
                            if category_type in keywords:
                                name_column = keywords[category_type]["columns"][0] if keywords[category_type]["columns"] else "name"
                                data = next((item for item in keywords[category_type]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords[category_type]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            all_keywords.append((category_type, value, who, keyword_dict))
                    else:
                        # 通常モード: 画面で選択されたキーワードを使用
                        for idx, (category_type, value, who) in enumerate(zip(selected_categories, keyword_combination, who_combination)):
                            keyword_dict = {}
                            
                            # カテゴリタイプに応じてキーワードを取得
                            if category_type in keywords:
                                name_column = keywords[category_type]["columns"][0] if keywords[category_type]["columns"] else "name"
                                data = next((item for item in keywords[category_type]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords[category_type]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            all_keywords.append((category_type, value, who, keyword_dict))
                    
                    # プロンプト構築
                    full_prompt = system_prompt + "\n\n"
                    
                    # ユーザー定義のルールとトンマナを追加
                    if user_rules:
                        full_prompt += f"<rules>\n{user_rules}\n</rules>\n\n"
                    
                    if user_tone:
                        full_prompt += f"<tone_and_style>\n{user_tone}\n</tone_and_style>\n\n"
                    
                    # CSV連続モードの場合は複数質問を処理
                    if is_batch_mode:
                        # 複数の質問を一連の質問として処理
                        full_prompt += "以下の質問は関連した一連の質問です。それぞれの回答に関連性を持たせて答えてください。\n\n"
                        
                        # 各質問にキーワード情報を追加
                        for q_idx, (q_id, question) in enumerate(zip(id_list, current_question)):
                            enhanced_question = f"質問{q_idx + 1} (ID: {q_id}): {question}"
                            for category_type, value, who, _ in all_keywords:
                                enhanced_question += f"\n【{who}の{category_type}】{value}"
                            full_prompt += f"{enhanced_question}\n\n"
                    else:
                        # 通常モード：単一質問の処理
                        enhanced_question = current_question
                        for category_type, value, who, _ in all_keywords:
                            enhanced_question += f"\n【{who}の{category_type}】{value}"
                        
                        full_prompt += f"質問: {enhanced_question}\n\n"
                    
                    # 各カテゴリのキーワードを追加
                    for category_type, value, who, keyword_dict in all_keywords:
                        if keyword_dict:
                            full_prompt += f"【{who}の{category_type}キーワード】{value}\n"
                            for col, keyword_value in keyword_dict.items():
                                full_prompt += f"・{col}: {keyword_value}\n"
                            full_prompt += "\n"
                    
                    # 文字数指定を追加（JSON形式で出力）
                    if is_batch_mode:
                        # CSV連続モード：複数質問用のJSON形式
                        full_prompt += f"\n【出力形式】\n"
                        full_prompt += f"必ず以下の正確なJSON形式のみを出力してください。前後に説明文を入れないでください：\n"
                        full_prompt += f'{{\n'
                        full_prompt += f'  "関連性の説明": "すべての質問の関連性についての説明",\n'
                        full_prompt += f'  "回答": [\n'
                        for q_idx, (q_id, _) in enumerate(zip(id_list, current_question)):
                            full_prompt += f'    {{\n'
                            full_prompt += f'      "id": "{q_id}",\n'
                            full_prompt += f'      "回答": "{answer_length}文字程度で詳細な占い結果",\n'
                            full_prompt += f'      "サマリ": "{summary_length}文字程度で要点をまとめた内容"\n'
                            full_prompt += f'    }}'
                            if q_idx < len(id_list) - 1:
                                full_prompt += ','
                            full_prompt += '\n'
                        full_prompt += f'  ],\n'
                        full_prompt += f'  "元キーワード": "使用したキーワードを記載",\n'
                        full_prompt += f'  "アレンジキーワード": "アレンジしたキーワードを記載"\n'
                        full_prompt += f'}}\n'
                    else:
                        # 通常モード：単一質問用のJSON形式
                        full_prompt += f"\n【出力形式】\n"
                        full_prompt += f"必ず以下の正確なJSON形式のみを出力してください。前後に説明文を入れないでください：\n"
                        full_prompt += f'{{\n'
                        full_prompt += f'  "回答": "{answer_length}文字程度で詳細な占い結果(ここには使用キーワードは記載しない)",\n'
                        full_prompt += f'  "サマリ": "{summary_length}文字程度で要点をまとめた内容",\n'
                        full_prompt += f'  "元キーワード": "使用したキーワードを記載（なければ空文字）",\n'
                        full_prompt += f'  "アレンジキーワード": "アレンジしたキーワードを記載（なければ空文字）"\n'
                        full_prompt += f'}}\n'
                    
                    full_prompt += f"注意事項：\n"
                    full_prompt += f"- JSONのみを出力（マークダウンのコードブロック```は使用しない）\n"
                    full_prompt += f"- 前後に説明文を含めない"
                    
                    # API呼び出し
                    if NEW_SDK:
                        # 新しいSDKを使用
                        # 適切なクライアントを選択
                        if USE_VERTEX_AI and vertex_ai_client:
                            current_client = vertex_ai_client
                        elif not USE_VERTEX_AI and google_ai_client:
                            current_client = google_ai_client
                        else:
                            current_client = client  # フォールバック
                        
                        if "2.5" in selected_model_name:
                            # Gemini 2.5の処理
                            # Gemini 2.5 Proの場合はthinking_configを一切指定しない
                            if "Pro" in selected_model_name and USE_VERTEX_AI:
                                if i == 0:  # 最初のリクエストでのみ表示
                                    st.info(f"🧠 Gemini 2.5 Proで生成中 (Vertex AI)")
                                response = current_client.models.generate_content(
                                    model=selected_model,
                                    contents=full_prompt
                                )
                            elif thinking_budget > 0:
                                # Gemini 2.5 Flash で思考機能ON
                                if i == 0:  # 最初のリクエストでのみ表示
                                    provider_info = "Vertex AI" if USE_VERTEX_AI else "Google AI"
                                    st.info(f"🧠 思考機能を使用中 ({provider_info}, 予算: {thinking_budget}トークン)")
                                
                                config = types.GenerateContentConfig(
                                    thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget)
                                )
                                response = current_client.models.generate_content(
                                    model=selected_model,
                                    contents=full_prompt,
                                    config=config
                                )
                            else:
                                # Gemini 2.5 Flash で思考機能OFF
                                if i == 0:  # 最初のリクエストでのみ表示
                                    provider_info = "Vertex AI" if USE_VERTEX_AI else "Google AI"
                                    st.info(f"⚡ 思考機能OFF ({provider_info}, 予算: {thinking_budget})")
                                
                                # Gemini 2.5 Flash は thinking_budget=0 を受け付ける
                                config = types.GenerateContentConfig(
                                    thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget)
                                )
                                response = current_client.models.generate_content(
                                    model=selected_model,
                                    contents=full_prompt,
                                    config=config
                                )
                        else:
                            # Gemini 2.5以外では通常の生成
                            if i == 0:
                                provider_info = "Vertex AI" if USE_VERTEX_AI else "Google AI"
                                st.info(f"⚡ 通常モードで生成中（{provider_info}）")
                            response = current_client.models.generate_content(
                                model=selected_model,
                                contents=full_prompt
                            )
                    else:
                        # 古いSDKを使用
                        model = genai.GenerativeModel(selected_model)
                        generation_config = {
                            'temperature': 0.9,
                            'top_p': 1,
                            'top_k': 1,
                            'max_output_tokens': 2048,
                        }
                        response = model.generate_content(
                            full_prompt,
                            generation_config=generation_config
                        )
                    
                    # JSON形式の回答を解析
                    if is_batch_mode:
                        # CSV連続モード：複数回答の処理
                        batch_results = []
                        
                        if response.text:
                            try:
                                # レスポンステキストのクリーンアップ
                                cleaned_text = response.text.strip()
                                
                                # マークダウンのコードブロックを除去
                                if cleaned_text.startswith("```json"):
                                    cleaned_text = cleaned_text[7:]
                                elif cleaned_text.startswith("```"):
                                    cleaned_text = cleaned_text[3:]
                                
                                if cleaned_text.endswith("```"):
                                    cleaned_text = cleaned_text[:-3]
                                
                                cleaned_text = cleaned_text.strip()
                                
                                # JSONの開始位置と終了位置を検出
                                start_idx = cleaned_text.find("{")
                                end_idx = cleaned_text.rfind("}")
                                
                                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                    json_text = cleaned_text[start_idx:end_idx + 1]
                                    json_response = json.loads(json_text)
                                    
                                    # 関連性の説明を取得
                                    relation_text = json_response.get("関連性の説明", "")
                                    original_keyword = json_response.get("元キーワード", "")
                                    arranged_keyword = json_response.get("アレンジキーワード", "")
                                    
                                    # 各質問の回答を取得
                                    answers = json_response.get("回答", [])
                                    for answer in answers:
                                        batch_results.append({
                                            "id": answer.get("id", ""),
                                            "回答": answer.get("回答", ""),
                                            "サマリ": answer.get("サマリ", ""),
                                            "関連性の説明": relation_text
                                        })
                                else:
                                    # JSON形式が見つからない場合
                                    for q_id in id_list:
                                        batch_results.append({
                                            "id": q_id,
                                            "回答": "JSON解析エラー",
                                            "サマリ": "",
                                            "関連性の説明": ""
                                        })
                                        
                            except json.JSONDecodeError as e:
                                # JSON解析に失敗した場合
                                for q_id in id_list:
                                    batch_results.append({
                                        "id": q_id,
                                        "回答": f"JSON解析エラー: {str(e)}",
                                        "サマリ": "",
                                        "関連性の説明": ""
                                    })
                        else:
                            # レスポンスがない場合
                            for q_id in id_list:
                                batch_results.append({
                                    "id": q_id,
                                    "回答": "回答を生成できませんでした",
                                    "サマリ": "",
                                    "関連性の説明": ""
                                })
                    else:
                        # 通常モード：単一回答の処理
                        answer_text = ""
                        summary_text = ""
                        original_keyword = ""
                        arranged_keyword = ""
                        
                        if response.text:
                            try:
                                # レスポンステキストのクリーンアップ
                                cleaned_text = response.text.strip()
                                
                                # マークダウンのコードブロックを除去
                                if cleaned_text.startswith("```json"):
                                    cleaned_text = cleaned_text[7:]  # ```json を除去
                                elif cleaned_text.startswith("```"):
                                    cleaned_text = cleaned_text[3:]  # ``` を除去
                                
                                if cleaned_text.endswith("```"):
                                    cleaned_text = cleaned_text[:-3]  # 末尾の ``` を除去
                                
                                # 再度前後の空白を除去
                                cleaned_text = cleaned_text.strip()
                                
                                # JSONの開始位置と終了位置を検出
                                start_idx = cleaned_text.find("{")
                                end_idx = cleaned_text.rfind("}")
                                
                                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                    json_text = cleaned_text[start_idx:end_idx + 1]
                                    
                                    # JSONとして解析を試行
                                    json_response = json.loads(json_text)
                                    answer_text = json_response.get("回答", "")
                                    summary_text = json_response.get("サマリ", "")
                                    original_keyword = json_response.get("元キーワード", "")
                                    arranged_keyword = json_response.get("アレンジキーワード", "")
                                else:
                                    # JSON形式が見つからない場合
                                    answer_text = response.text
                                    summary_text = ""
                                    
                            except json.JSONDecodeError as e:
                                # JSON解析に失敗した場合は元のテキストを回答に入れる
                                answer_text = response.text
                                summary_text = ""
                                # サマリが空の場合、エラー情報を記録
                                if not summary_text:
                                    summary_text = f"JSON解析エラー"
                        else:
                            answer_text = "回答を生成できませんでした"
                            summary_text = ""
                    
                    # トークン数の取得（Noneチェック付き）
                    if hasattr(response, 'usage_metadata') and response.usage_metadata:
                        if hasattr(response.usage_metadata, 'prompt_token_count') and response.usage_metadata.prompt_token_count is not None:
                            total_prompt_tokens += response.usage_metadata.prompt_token_count
                        if hasattr(response.usage_metadata, 'candidates_token_count') and response.usage_metadata.candidates_token_count is not None:
                            total_candidates_tokens += response.usage_metadata.candidates_token_count
                        if hasattr(response.usage_metadata, 'thoughts_token_count') and response.usage_metadata.thoughts_token_count is not None:
                            total_thoughts_tokens += response.usage_metadata.thoughts_token_count
                        if hasattr(response.usage_metadata, 'cached_content_token_count') and response.usage_metadata.cached_content_token_count is not None:
                            total_cached_tokens += response.usage_metadata.cached_content_token_count
                    
                    # 結果保存
                    if is_batch_mode:
                        # CSV連続モード：複数の結果を保存
                        for idx, (q_id, question, batch_result) in enumerate(zip(id_list, current_question, batch_results)):
                            result_dict = {"id": q_id, "質問": question}
                            
                            # 各カテゴリの値を追加
                            for cat_idx, (category_type, value, who) in enumerate(zip(selected_categories, keyword_combination, who_combination)):
                                result_dict[f"{who}の{category_type}{cat_idx+1}"] = value
                            
                            # 回答データを追加
                            result_dict["回答"] = batch_result.get("回答", "")
                            result_dict["サマリ"] = batch_result.get("サマリ", "")
                            result_dict["関連性の説明"] = batch_result.get("関連性の説明", "")
                            result_dict["元キーワード"] = original_keyword
                            result_dict["アレンジキーワード"] = arranged_keyword
                            
                            results.append(result_dict)
                    else:
                        # 通常モード：単一の結果を保存
                        result_dict = {"id": question_id, "質問": current_question}
                        
                        # 各カテゴリの値を追加（最大4つ）
                        if is_csv_mode and csv_validated_keywords:
                            # CSV優先モード: CSV由来のキーワードを保存
                            for idx, (category_type, value, who) in enumerate(csv_validated_keywords):
                                result_dict[f"{who}の{category_type}{idx+1}"] = value
                            # 空欄は作らない（CSVモードでは実際のキーワード数だけ出力）
                        else:
                            # 通常モード: 画面で選択されたキーワードを保存
                            for idx, (category_type, value, who) in enumerate(zip(selected_categories, keyword_combination, who_combination)):
                                result_dict[f"{who}の{category_type}{idx+1}"] = value
                        
                        # 残りの固定項目を追加
                        result_dict["回答"] = answer_text
                        result_dict["サマリ"] = summary_text
                        result_dict["元キーワード"] = original_keyword
                        result_dict["アレンジキーワード"] = arranged_keyword
                        
                        results.append(result_dict)
                    
                    # プログレス更新
                    progress = (i + 1) / len(total_combinations)
                    progress_bar.progress(progress)
                    thinking_status = f" (思考機能: {thinking_budget}トークン)" if thinking_budget > 0 else ""
                    # 組み合わせの表示テキストを動的に生成
                    combo_parts = []
                    for val, who in zip(keyword_combination, who_combination):
                        combo_parts.append(f"{who}の{val}")
                    combo_text = " × ".join(combo_parts)
                    
                    if is_batch_mode:
                        status_text.text(f"進行状況: {i + 1}/{len(total_combinations)} - 連続処理: {len(current_question)}個の質問 | {combo_text}{thinking_status}")
                    else:
                        question_preview = current_question[:30] + "..." if len(current_question) > 30 else current_question
                        status_text.text(f"進行状況: {i + 1}/{len(total_combinations)} - 質問: {question_preview} | {combo_text}{thinking_status}")
                    
                    # トークン情報の更新
                    token_text = f"入力: {total_prompt_tokens:,} | 出力: {total_candidates_tokens:,}"
                    if total_thoughts_tokens > 0:
                        token_text += f" | 思考: {total_thoughts_tokens:,}"
                    if total_cached_tokens > 0:
                        token_text += f" | キャッシュ: {total_cached_tokens:,}"
                    token_info.info(f"📊 トークン使用量: {token_text}")
                    
                except Exception as e:
                    # エラー時の結果保存（動的カテゴリに対応）
                    result_dict = {"id": question_id, "質問": current_question}
                    
                    # 各カテゴリの値を追加
                    if is_csv_mode and csv_validated_keywords:
                        # CSV優先モード
                        for idx, (category_type, value, who) in enumerate(csv_validated_keywords):
                            result_dict[f"{who}の{category_type}{idx+1}"] = value
                        # 空欄は作らない（CSVモードでは実際のキーワード数だけ出力）
                    else:
                        # 通常モード
                        for idx, (category_type, value, who) in enumerate(zip(selected_categories, keyword_combination, who_combination)):
                            result_dict[f"{who}の{category_type}{idx+1}"] = value
                    
                    result_dict["回答"] = f"エラー: {str(e)}"
                    result_dict["サマリ"] = ""
                    result_dict["元キーワード"] = ""
                    result_dict["アレンジキーワード"] = ""
                    
                    results.append(result_dict)
            
            # 結果表示
            st.success("生成完了！")
            
            # 最終的なトークン使用量サマリー
            st.subheader("トークン使用量サマリー")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("入力トークン", f"{total_prompt_tokens:,}")
            
            with col2:
                st.metric("出力トークン", f"{total_candidates_tokens:,}")
            
            with col3:
                if total_thoughts_tokens > 0:
                    st.metric("思考トークン", f"{total_thoughts_tokens:,}")
                else:
                    st.metric("思考トークン", "0")
            
            with col4:
                total_tokens = total_prompt_tokens + total_candidates_tokens + total_thoughts_tokens
                st.metric("合計トークン", f"{total_tokens:,}")
            
            # CSV出力
            df = pd.DataFrame(results)
            timestamp = get_japan_time().replace(':', '').replace('-', '').replace(' ', '_')
            # カスタムファイル名を使用（デフォルトは"占い結果"）
            csv_filename = f"{custom_filename}_{timestamp}.csv"
            
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="結果をCSVでダウンロード",
                data=csv,
                file_name=csv_filename,
                mime="text/csv"
            )
            
            # 結果プレビュー
            st.subheader("結果プレビュー")
            st.dataframe(df)
    
    # ===============================
    # 6. キーワード参照セクション
    # ===============================
    with st.expander("📚 キーワード参照", expanded=False):
        if st.session_state.custom_keywords:
            # カスタムキーワードの表示
            for category_name, keyword_info in keywords.items():
                if keyword_info and "df" in keyword_info:
                    st.subheader(f"{category_name}キーワード")
                    st.dataframe(keyword_info["df"], use_container_width=True)
        else:
            st.info("キーワードCSVファイルをアップロードしてください。")

else:
    if USE_VERTEX_AI:
        st.info("👈 サイドバーでGCPプロジェクトIDを設定してください")
    else:
        st.info("👈 サイドバーでGemini APIキーを入力してください")
    
    st.subheader("使用方法")
    st.markdown("""
    1. **質問入力**: 占いで答えてもらいたい質問を入力
    2. **キーワード選択**: ハウス、サイン、天体を選択（「すべて」で一括生成）
    3. **生成実行**: ボタンを押して占い回答を生成
    4. **結果ダウンロード**: CSVファイルで結果をダウンロード
    """)
