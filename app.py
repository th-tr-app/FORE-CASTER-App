import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")

# サイドバーとメイン画面のロゴ設定
# image_13.png (サイドバー用ロゴ), image_12.png (サイドバー折りたたみ時アイコン)
st.logo("image_13.png", icon_image="image_12.png")

# カスタムCSS（レスポンシブ調整）
st.markdown("""
    <style>
    /* スマホで横並びを維持する設定 */
    @media (max-width: 640px) {
        [data-testid="stMetric"] {
            min-width: 80px !important;
        }
        [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: wrap !important;
        }
        /* 横2列にするための調整（4x4はスマホでは文字が潰れるため、視認性を重視し2x4を推奨しますが、CSSで可能な限り並べます） */
        div[data-testid="column"] {
            flex: 1 1 45% !important;
            min-width: 45% !important;
        }
    }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 & マッピング ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "6920.T": "レーザーテック", "7011.T": "三菱重工",
    "7203.T": "トヨタ", "8306.T": "三菱UFJ", "9984.T": "ソフトバンクG",
    "1570.T": "日経レバ", "7013.T": "IHI", "8031.T": "三井物産", "6758.T": "ソニーG"
}

# 指標の入れ替え & 並び替え
MARKET_INDICES = {
    "日経平均": "^N225",
    "日経先物 (CME)": "NIY=F",
    "ドル/円": "JPY=X",
    "NYダウ30種": "^DJI",
    "原油先物 (WTI)": "CL=F",
    "Gold (COMEX)": "GC=F",
    "VIX指数": "^VIX",
    "SOX指数": "^SOX"
}

# --- 3. 関数定義 ---

@st.cache_data(ttl=600)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change_pct = ((latest - prev) / prev) * 100
                data[name] = {"val": latest, "pct": change_pct}
            else: data[name] = {"val": None, "pct": None}
        except: data[name] = {"val": None, "pct": None}
    return data

# --- 4. サイドバー ---
# タイトルを削除し、パラメータのみ配置
st.sidebar.subheader("🛡️ 戦略プリセット")
col_p1, col_p2, col_p3 = st.sidebar.columns(3)
if col_p1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_p2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_p3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.subheader("⚙️ BACK TESTER 設定")
days_back = st.sidebar.slider("過去日数", 10, 59, 59)
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7) / 100

# --- 5. メインレイアウト ---
st.markdown("<h1 style='font-weight: 400; font-size: 42px; margin-bottom: 20px;'>FORE CASTER</h1>", unsafe_allow_html=True)

# 共通銘柄入力
if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

# タブの名称を短縮
tab_top, tab_screen, tab_bt = st.tabs(["ワンタッチ", "スクリーニング", "バックテスト"])

# --- タブ1: トップ画面 ---
with tab_top:
    # リアルタイム情報の見出し
    col_head_l, col_head_r = st.columns([0.8, 0.2])
    with col_head_l:
        st.subheader("🌍 リアルタイム指標")
    with col_head_r:
        if st.button("🔄 更新"):
            st.cache_data.clear()
            st.rerun()

    with st.expander("詳細を表示 (タップで開閉)", expanded=True):
        m_info = fetch_market_info()
        # 4列レイアウト
        m_cols = st.columns(4)
        for i, (name, info) in enumerate(m_info.items()):
            # PCでは2段(4x2)、スマホでは自動的に折り返し
            with m_cols[i % 4]:
                if info["val"] is not None:
                    st.metric(name, f"{info['val']:,.1f}", f"{info['pct']:+.2f}%")
                else:
                    st.metric(name, "取得不可", "---")
        
        # --- AI予測ロジック ---
        vix_val = m_info.get("VIX指数", {}).get("val", 0)
        st.markdown("---")
        if vix_val and vix_val > 20:
            st.warning(f"🤖 **AI予測:** VIXが{vix_val:.1f}と高く、市場に不安が広がっています。突発的な急落に備え、ポジションを小さく保つか、損切り設定を厳格にしてください。")
        elif vix_val and vix_val < 15:
            st.info("🤖 **AI予測:** 市場は極めて安定しています。トレンド追随（順張り）が機能しやすい環境です。強気のエントリーを検討できます。")
        else:
            st.write("🤖 **AI予測:** 指標に極端な偏りはありません。テクニカル指標のサインに忠実なトレードを推奨します。")

    st.divider()
    st.subheader("🚀 One-Touch 期待値スキャン")
    if st.button("主要銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        st.write("※分析エンジン準備中。サンプル銘柄をロードします...")
        st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
        st.rerun()
