import streamlit as st
import os
import pandas as pd
import csv
from datetime import datetime
import itertools
import toml
import json
import hashlib
import hmac

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

# 占い用の定数定義
HOUSES = ["すべて"] + [f"第{i}ハウス" for i in range(1, 13)]
SIGNS = ["すべて", "牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"]
PLANETS = ["すべて", "太陽", "月", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"]
ELEMENTS = ["すべて", "火", "地", "風", "水"]
MP_AXES = ["すべて", "情報軸", "結婚･やすらぎ軸", "行動軸", "成功軸", "責任軸", "180度転換軸", "迷い軸", "カリスマ軸", 
           "自己人脈軸", "紹介･交際軸", "情報・活動軸", "開業・営業軸", "融通ナシ軸", "アイデア軸", "判断ミス軸", 
           "発明・有名軸", "情報人脈軸", "一目ぼれ軸", "自己投資軸", "投資控え軸", "ときめき軸", "心不安軸", 
           "欲情・臨時収入軸", "スポンサー人脈軸", "ミラクル軸", "清算軸", "建て直し軸", "病気軸", "エネルギーパワー軸", 
           "行動人脈軸", "移転・転職軸", "成功・発展軸", "誤診軸", "カリスマ・成功軸", "成功人脈軸", "圧迫軸", 
           "ストレス軸", "執着軸", "年上人脈軸", "別れ・孤立軸", "大変革軸", "変化人脈軸", "カルマ業病軸", 
           "スピリチュアル人脈軸", "助言人脈軸", "無軸"]
TAROTS = ["すべて", "愚者(正位置)", "愚者(逆位置)", "魔術師(正位置)", "魔術師(逆位置)", "女教皇(正位置)", "女教皇(逆位置)", 
          "女帝(正位置)", "女帝(逆位置)", "皇帝(正位置)", "皇帝(逆位置)", "法王(正位置)", "法王(逆位置)",
          "恋人(正位置)", "恋人(逆位置)", "戦車(正位置)", "戦車(逆位置)", "力(正位置)", "力(逆位置)",
          "隠者(正位置)", "隠者(逆位置)", "運命の輪(正位置)", "運命の輪(逆位置)", "正義(正位置)", "正義(逆位置)",
          "吊られた男(正位置)", "吊られた男(逆位置)", "死神(正位置)", "死神(逆位置)", "節制(正位置)", "節制(逆位置)",
          "悪魔(正位置)", "悪魔(逆位置)", "塔(正位置)", "塔(逆位置)", "星(正位置)", "星(逆位置)",
          "月(正位置)", "月(逆位置)", "太陽(正位置)", "太陽(逆位置)", "審判(正位置)", "審判(逆位置)",
          "世界(正位置)", "世界(逆位置)"]

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

# キーワードCSVファイル読み込み関数
@st.cache_data
def load_keywords():
    keywords = {}
    base_path = os.path.dirname(__file__)
    
    try:
        # ハウスキーワード
        house_path = os.path.join(base_path, "ハウスキーワード.csv")
        if os.path.exists(house_path):
            df = pd.read_csv(house_path, encoding='utf-8')
            # DataFrameを保持（ヘッダー情報も含む）
            keywords["house"] = {
                "df": df,
                "columns": list(df.columns),
                "data": df.to_dict('records')
            }
        
        # サインキーワード
        sign_path = os.path.join(base_path, "サインキーワード.csv")
        if os.path.exists(sign_path):
            df = pd.read_csv(sign_path, encoding='utf-8')
            keywords["sign"] = {
                "df": df,
                "columns": list(df.columns),
                "data": df.to_dict('records')
            }
        
        # 天体キーワード
        planet_path = os.path.join(base_path, "天体キーワード.csv")
        if os.path.exists(planet_path):
            df = pd.read_csv(planet_path, encoding='utf-8')
            keywords["planet"] = {
                "df": df,
                "columns": list(df.columns),
                "data": df.to_dict('records')
            }
        
        # エレメントキーワード
        element_path = os.path.join(base_path, "エレメントキーワード.csv")
        if os.path.exists(element_path):
            df = pd.read_csv(element_path, encoding='utf-8')
            keywords["element"] = {
                "df": df,
                "columns": list(df.columns),
                "data": df.to_dict('records')
            }
        
        # MP軸キーワード
        mp_path = os.path.join(base_path, "MP軸キーワード.csv")
        if os.path.exists(mp_path):
            df = pd.read_csv(mp_path, encoding='utf-8')
            keywords["mp_axis"] = {
                "df": df,
                "columns": list(df.columns),
                "data": df.to_dict('records')
            }
        
        # タロットキーワード
        tarot_path = os.path.join(base_path, "タロットキーワード.csv")
        if os.path.exists(tarot_path):
            df = pd.read_csv(tarot_path, encoding='utf-8')
            keywords["tarot"] = {
                "df": df,
                "columns": list(df.columns),
                "data": df.to_dict('records')
            }
            
    except Exception as e:
        pass
    
    return keywords

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
        
        # テスト用テンプレート
        st.markdown("---")
        st.subheader("📝 テスト用テンプレート")
        
        st.text("設定値:")
        st.text("ハウス：すべて")
        st.text("サイン：なし")
        st.text("天体：太陽")
        
        st.code("""「天体」の中の「太陽」と、「ハウス」の「第1～12ハウス」のキーワードを参照して、あなたはどんな性格の人なのかを答えて。太陽が各ハウスに入っているときの特徴をわかりやすく答えに繋げて""", language="text")
        
        st.info("上記の質問文をコピーして質問欄に貼り付け、設定値を手動で選択してください。")

if api_key or (USE_VERTEX_AI and vertex_project):
    st.header("🔮 占い設定")
    
    # ===============================
    # 1. キーワード設定セクション
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
        
        # カスタムキーワード使用の切り替え
        use_custom_keywords = st.checkbox(
            "カスタムキーワードを使用する",
            value=bool(st.session_state.custom_keywords),
            disabled=not bool(st.session_state.custom_keywords),
            help="アップロードしたカスタムキーワードを使用します"
        )
    
    # ===============================
    # 2. 基本設定セクション
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
        ["テキスト入力", "CSVファイル入力"],
        horizontal=True,
        help="テキスト入力: 単一の質問を入力 / CSVファイル入力: 複数の質問をCSVファイルから読み込み"
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
    else:
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
    
    # ===============================
    # 4. プロンプト設定セクション
    # ===============================
    with st.expander("📝 プロンプト設定", expanded=False):
        st.write("占い生成の追加ルールやトーン&マナーを設定できます。")
        
        col_rules, col_tone = st.columns(2)
        
        with col_rules:
            user_rules = st.text_area(
                "ルール設定",
                value="",
                height=150,
                placeholder="例：必ず前向きな内容にする、専門用語は使わない、等",
                help="占い生成時の追加ルールを記入してください"
            )
        
        with col_tone:
            user_tone = st.text_area(
                "トーン&マナー設定",
                value="",
                height=150,
                placeholder="例：親しみやすい口調で、絵文字を使用する、等",
                help="占いの文体やトーンの指定を記入してください"
            )
    
    # ===============================
    # 5. キーワード設定セクション
    # ===============================
    st.subheader("🔍 キーワード設定")
    
    # セッション状態でカテゴリリストを管理
    if 'keyword_categories' not in st.session_state:
        # カスタムキーワードが有効な場合は最初のカテゴリ、そうでなければハウス
        if 'use_custom_keywords' in locals() and use_custom_keywords and st.session_state.custom_keywords:
            st.session_state.keyword_categories = [list(st.session_state.custom_keywords.keys())[0]]
        else:
            st.session_state.keyword_categories = ["ハウス"]
    
    # カテゴリ管理ボタン
    col_info, col_add, col_remove = st.columns([2, 1, 1])
    with col_info:
        st.info(f"現在のカテゴリ数: {len(st.session_state.keyword_categories)}/4")
    with col_add:
        if st.button("➕ 追加", disabled=len(st.session_state.keyword_categories) >= 4):
            if len(st.session_state.keyword_categories) < 4:
                # カスタムキーワードが有効な場合は最初のカテゴリ、そうでなければハウス
                if 'use_custom_keywords' in locals() and use_custom_keywords and st.session_state.custom_keywords:
                    default_category = list(st.session_state.custom_keywords.keys())[0]
                else:
                    default_category = "ハウス"
                st.session_state.keyword_categories.append(default_category)
                st.rerun()
    with col_remove:
        if st.button("➖ 削除", disabled=len(st.session_state.keyword_categories) <= 1):
            if len(st.session_state.keyword_categories) > 1:
                st.session_state.keyword_categories.pop()
                st.rerun()
    
    # 選択されたカテゴリとキーワードを保存
    # カスタムキーワードが有効な場合はそれを使用、そうでなければデフォルト
    if 'use_custom_keywords' in locals() and use_custom_keywords and st.session_state.custom_keywords:
        category_types = list(st.session_state.custom_keywords.keys())
        keywords = st.session_state.custom_keywords
    else:
        category_types = ["ハウス", "サイン", "天体", "エレメント", "MP軸", "タロット"]
        keywords = load_keywords()
    
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
                        
                            # キーワード選択（動的に対応）
                            if 'use_custom_keywords' in locals() and use_custom_keywords and st.session_state.custom_keywords:
                                # カスタムキーワードモード
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
                            else:
                                # デフォルトキーワードモード
                                if category_type == "ハウス":
                                    selected_value = st.selectbox(
                                        "キーワード", 
                                        HOUSES, 
                                        key=f"keyword_{idx}",
                                        label_visibility="visible"
                                    )
                                elif category_type == "サイン":
                                    selected_value = st.selectbox(
                                        "キーワード", 
                                        SIGNS, 
                                        key=f"keyword_{idx}",
                                        label_visibility="visible"
                                    )
                                elif category_type == "天体":
                                    selected_value = st.selectbox(
                                        "キーワード", 
                                        PLANETS, 
                                        key=f"keyword_{idx}",
                                        label_visibility="visible"
                                    )
                                elif category_type == "エレメント":
                                    selected_value = st.selectbox(
                                        "キーワード", 
                                        ELEMENTS, 
                                        key=f"keyword_{idx}",
                                        label_visibility="visible"
                                    )
                                elif category_type == "MP軸":
                                    selected_value = st.selectbox(
                                        "キーワード", 
                                        MP_AXES, 
                                        key=f"keyword_{idx}",
                                        label_visibility="visible"
                                    )
                                else:  # タロット
                                    selected_value = st.selectbox(
                                        "キーワード", 
                                        TAROTS, 
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
    # 6. 実行ボタン
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
                    if 'use_custom_keywords' in locals() and use_custom_keywords and st.session_state.custom_keywords:
                        # カスタムキーワードモード
                        if category_type in keywords:
                            keyword_data = keywords[category_type]["data"]
                            first_column = keywords[category_type]["columns"][0] if keywords[category_type]["columns"] else "name"
                            all_values = [item[first_column] for item in keyword_data if first_column in item]
                            value_lists.append(all_values)
                        else:
                            value_lists.append([selected_value])
                    else:
                        # デフォルトキーワードモード
                        if category_type == "ハウス":
                            value_lists.append([f"第{i}ハウス" for i in range(1, 13)])
                        elif category_type == "サイン":
                            value_lists.append(["牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"])
                        elif category_type == "天体":
                            value_lists.append(["太陽", "月", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"])
                        elif category_type == "エレメント":
                            value_lists.append(["火", "地", "風", "水"])
                        elif category_type == "MP軸":
                            value_lists.append(MP_AXES[1:])  # "すべて"を除く
                        else:  # タロット
                            value_lists.append(TAROTS[1:])  # "すべて"を除く
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
                                if valid_category == "ハウス":
                                    if kw_name in HOUSES:
                                        valid_keyword = kw_name
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                                    else:
                                        # 数字だけの場合は第Xハウス形式に変換
                                        try:
                                            house_num = int(kw_name)
                                            if 1 <= house_num <= 12:
                                                valid_keyword = f"第{house_num}ハウス"
                                        except:
                                            pass
                                elif valid_category == "サイン":
                                    if kw_name in SIGNS:
                                        valid_keyword = kw_name
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                                elif valid_category == "天体":
                                    if kw_name in PLANETS:
                                        valid_keyword = kw_name
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                                elif valid_category == "エレメント":
                                    if kw_name in ELEMENTS:
                                        valid_keyword = kw_name
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                                elif valid_category == "MP軸":
                                    if kw_name in MP_AXES:
                                        valid_keyword = kw_name
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                                elif valid_category == "タロット":
                                    if kw_name in TAROTS:
                                        valid_keyword = kw_name
                                    elif kw_name.lower() == "すべて" or kw_name.lower() == "all":
                                        valid_keyword = "すべて"
                            
                            # 対象（誰の）の検証
                            valid_who = who_name if who_name in ["あなた", "あの人", "相性"] else "あなた"
                            
                            if valid_category and valid_keyword:
                                validated_keywords.append((valid_category, valid_keyword, valid_who))
                            else:
                                error_keywords.append(f"{cat_name}:{kw_name}")
                        
                        if error_keywords:
                            st.warning(f"ID: {question_id} - 無効なキーワード指定: {', '.join(error_keywords)}")
                        
                        if validated_keywords:
                            # 「すべて」を展開する必要があるかチェック
                            expanded_keywords_list = []
                            has_all_keyword = False
                            
                            for cat, kw, who in validated_keywords:
                                if kw == "すべて":
                                    has_all_keyword = True
                                    # カテゴリに応じて展開
                                    if cat == "ハウス":
                                        expanded_keywords_list.append([(cat, f"第{i}ハウス", who) for i in range(1, 13)])
                                    elif cat == "サイン":
                                        expanded_keywords_list.append([(cat, sign, who) for sign in SIGNS[1:]])  # "すべて"を除く
                                    elif cat == "天体":
                                        expanded_keywords_list.append([(cat, planet, who) for planet in PLANETS[1:]])
                                    elif cat == "エレメント":
                                        expanded_keywords_list.append([(cat, elem, who) for elem in ELEMENTS[1:]])
                                    elif cat == "MP軸":
                                        expanded_keywords_list.append([(cat, axis, who) for axis in MP_AXES[1:]])
                                    elif cat == "タロット":
                                        expanded_keywords_list.append([(cat, tarot, who) for tarot in TAROTS[1:]])
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
                            # 有効なキーワードがない場合は画面設定を使用
                            for j, keyword_combo in enumerate(keyword_combinations):
                                who_combo = who_combinations[j] if j < len(who_combinations) else selected_who
                                total_combinations.append((question_id, question, keyword_combo, tuple(who_combo), None))
                    else:
                        # CSVにキーワード指定がない場合は画面設定を使用
                        for j, keyword_combo in enumerate(keyword_combinations):
                            who_combo = who_combinations[j] if j < len(who_combinations) else selected_who
                            total_combinations.append((question_id, question, keyword_combo, tuple(who_combo), None))
            else:
                # テキスト入力またはCSVにキーワード指定がない場合
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
                
                try:
                    # キーワード取得（動的カテゴリに対応）
                    all_keywords = []  # 各カテゴリのキーワードを格納
                    
                    if is_csv_mode and csv_validated_keywords:
                        # CSV優先モード: 検証済みキーワードを使用
                        for category_type, value, who in csv_validated_keywords:
                            keyword_dict = {}
                            
                            # カテゴリタイプに応じてキーワードを取得
                            if category_type == "ハウス" and "house" in keywords:
                                name_column = keywords["house"]["columns"][0] if keywords["house"]["columns"] else "name"
                                data = next((item for item in keywords["house"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["house"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "サイン" and "sign" in keywords:
                                name_column = keywords["sign"]["columns"][0] if keywords["sign"]["columns"] else "name"
                                data = next((item for item in keywords["sign"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["sign"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "天体" and "planet" in keywords:
                                name_column = keywords["planet"]["columns"][0] if keywords["planet"]["columns"] else "name"
                                data = next((item for item in keywords["planet"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["planet"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "エレメント" and "element" in keywords:
                                name_column = keywords["element"]["columns"][0] if keywords["element"]["columns"] else "name"
                                data = next((item for item in keywords["element"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["element"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "MP軸" and "mp_axis" in keywords:
                                name_column = keywords["mp_axis"]["columns"][0] if keywords["mp_axis"]["columns"] else "name"
                                data = next((item for item in keywords["mp_axis"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["mp_axis"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "タロット" and "tarot" in keywords:
                                name_column = keywords["tarot"]["columns"][0] if keywords["tarot"]["columns"] else "name"
                                data = next((item for item in keywords["tarot"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["tarot"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            all_keywords.append((category_type, value, who, keyword_dict))
                    else:
                        # 通常モード: 画面で選択されたキーワードを使用
                        for idx, (category_type, value, who) in enumerate(zip(selected_categories, keyword_combination, who_combination)):
                            keyword_dict = {}
                            
                            # カテゴリタイプに応じてキーワードを取得
                            if category_type == "ハウス" and "house" in keywords:
                                name_column = keywords["house"]["columns"][0] if keywords["house"]["columns"] else "name"
                                data = next((item for item in keywords["house"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["house"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "サイン" and "sign" in keywords:
                                name_column = keywords["sign"]["columns"][0] if keywords["sign"]["columns"] else "name"
                                data = next((item for item in keywords["sign"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["sign"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "天体" and "planet" in keywords:
                                name_column = keywords["planet"]["columns"][0] if keywords["planet"]["columns"] else "name"
                                data = next((item for item in keywords["planet"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["planet"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "エレメント" and "element" in keywords:
                                name_column = keywords["element"]["columns"][0] if keywords["element"]["columns"] else "name"
                                data = next((item for item in keywords["element"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["element"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "MP軸" and "mp_axis" in keywords:
                                name_column = keywords["mp_axis"]["columns"][0] if keywords["mp_axis"]["columns"] else "name"
                                data = next((item for item in keywords["mp_axis"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["mp_axis"]["columns"][1:]:
                                        if col in data and data[col]:
                                            keyword_dict[col] = data[col]
                            
                            elif category_type == "タロット" and "tarot" in keywords:
                                name_column = keywords["tarot"]["columns"][0] if keywords["tarot"]["columns"] else "name"
                                data = next((item for item in keywords["tarot"]["data"] if item.get(name_column) == value), None)
                                if data:
                                    for col in keywords["tarot"]["columns"][1:]:
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
                    
                    # 質問に選択したカテゴリを追加
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
                    full_prompt += f"- 回答内で改行する場合は<br>タグを使用可能\n"
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
                    
                    # 結果保存（動的カテゴリに対応）
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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    # 7. キーワード参照セクション
    # ===============================
    with st.expander("📚 キーワード参照", expanded=False):
        if 'use_custom_keywords' in locals() and use_custom_keywords and st.session_state.custom_keywords:
            # カスタムキーワードの表示
            for category_name, keyword_info in keywords.items():
                if keyword_info and "df" in keyword_info:
                    st.subheader(f"{category_name}キーワード")
                    st.dataframe(keyword_info["df"], use_container_width=True)
        else:
            # デフォルトキーワードの表示
            if "house" in keywords and keywords["house"]:
                st.subheader("ハウスキーワード")
                st.dataframe(keywords["house"]["df"], use_container_width=True)
            
            if "sign" in keywords and keywords["sign"]:
                st.subheader("サインキーワード")
                st.dataframe(keywords["sign"]["df"], use_container_width=True)
            
            if "planet" in keywords and keywords["planet"]:
                st.subheader("天体キーワード")
                st.dataframe(keywords["planet"]["df"], use_container_width=True)
            
            if "element" in keywords and keywords["element"]:
                st.subheader("エレメントキーワード")
                st.dataframe(keywords["element"]["df"], use_container_width=True)
            
            if "mp_axis" in keywords and keywords["mp_axis"]:
                st.subheader("MP軸キーワード")
                st.dataframe(keywords["mp_axis"]["df"], use_container_width=True)
            
            if "tarot" in keywords and keywords["tarot"]:
                st.subheader("タロットキーワード")
                st.dataframe(keywords["tarot"]["df"], use_container_width=True)

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
