import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")

# サイドバー設定（image_13.png: ロゴ, image_12.png: アイコン）
st.logo("image_13.png", icon_image="image_12.png")

# カスタムCSS（フォントサイズ調整とモバイル4列強制）
st.markdown("""
    <style>
    /* 全体タイトルの調整 */
    .main-title { font-weight: 400; font-size: 32px; margin-bottom: 10px; }
    
    /* 見出し(Subheader)のサイズ調整 */
    .section-header { 
        font-size: 18px !important; 
        font-weight: 600; 
        margin-top: 10px; 
        margin-bottom: 10px; 
        color: #ffffff;
    }

    /* PC・スマホ共通：メトリックのコンテナ設定 */
    [data-testid="stHorizontalBlock"] {
        gap: 0px !important;
    }

    /* スマホ(幅640px以下)専用の強制4列レイアウト */
    @media (max-width: 640px) {
        div[data-testid="column"] {
            flex: 1 1 24% !important; /* 4列に分割 */
            min-width: 24% !important;
            padding: 2px !important;
        }
        /* メトリック内のフォントを極小化して重なりを防ぐ */
        [data-testid="stMetricLabel"] { font-size: 9px !important; }
        [data-testid="stMetricValue"] { font-size: 13px !important; }
        [data-testid="stMetricDelta"] { font-size: 9px !important; }
        
        /* タブのフォントサイズも調整 */
        button[data-baseweb="tab"] { font-size: 12px !important; padding: 10px 5px !important; }
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

MARKET_INDICES = {
    "日経平均": "^N225", "日経先物": "NIY=F", "ドル/円": "JPY=X", "NYダウ30": "^DJI",
    "原油(WTI)": "CL=F", "Gold": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
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

# --- 4. サイドバー (タイトル削除済) ---
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
st.markdown("<div class='main-title'>FORE CASTER</div>", unsafe_allow_html=True)

# 共通銘柄入力
if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["ワンタッチ", "スクリーニング", "バックテスト"])

# --- タブ1: トップ画面 ---
with tab_top:
    col_head_l, col_head_r = st.columns([0.8, 0.2])
    with col_head_l:
        st.markdown("<div class='section-header'>🌍 リアルタイム指標</div>", unsafe_allow_html=True)
    with col_head_r:
        if st.button("🔄 更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.expander("詳細を表示", expanded=True):
        m_info = fetch_market_info()
        # 4列固定レイアウト
        m_cols = st.columns(4)
        for i, (name, info) in enumerate(m_info.items()):
            with m_cols[i % 4]:
                if info["val"] is not None:
                    # delta_color="normal" は +が緑 / -が赤 (欧米基準)
                    st.metric(label=name, value=f"{info['val']:,.0f}", delta=f"{info['pct']:+.2f}%", delta_color="normal")
                else:
                    st.metric(label=name, value="取得失敗", delta="---")
        
        # AI予測 (VIXベース)
        vix_val = m_info.get("VIX指数", {}).get("val", 0)
        st.markdown("---")
        if vix_val and vix_val > 20:
            st.warning(f"🤖 **AI予測:** VIX高。ボラティリティ警戒。")
        elif vix_val and vix_val < 15:
            st.info(f"🤖 **AI予測:** 市場安定。順張り有利。")
        else:
            st.write("🤖 **AI予測:** 指標は中立です。")

    st.divider()
    st.markdown("<div class='section-header'>🚀 One-Touch 期待値スキャン</div>", unsafe_allow_html=True)
    if st.button("主要銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        st.write("※分析エンジン準備中...")
        st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
        st.rerun()
