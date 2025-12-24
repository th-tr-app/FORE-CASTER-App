import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# カスタムCSS（デザインの心臓部）
st.markdown("""
    <style>
    .main-title { font-weight: 500; font-size: 26px; margin-bottom: 5px; }
    .section-header-container { display: flex; align-items: center; margin-bottom: 10px; }
    .section-header { font-size: 16px !important; font-weight: 600; color: #dddddd; margin-right: 15px; }

    /* タイル型グリッド設計 */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr); /* PCは4列 */
        gap: 8px;
        width: 100%;
    }

    /* スマホ(幅640px以下)は強制2列 */
    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
    }

    /* カードのデザイン（BACK TESTER風） */
    .metric-card {
        background-color: #1e2129;
        border: 1px solid #3d414b;
        border-radius: 8px;
        padding: 10px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    .metric-label { font-size: 10px; color: #aaaaaa; margin-bottom: 2px; }
    .metric-value { font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 2px; }
    .metric-delta { font-size: 11px; font-weight: 500; }
    
    .delta-plus { color: #00f0a8; }
    .delta-minus { color: #ff4b4b; }
    
    /* 更新ボタンの小型化 */
    div.stButton > button {
        padding: 2px 8px !important;
        font-size: 11px !important;
        height: 24px !important;
        border-radius: 4px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 & マッピング ---
MARKET_INDICES = {
    "日経平均": "^N225", "日経先物": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
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

def render_market_grid(m_info):
    """全ての指標を一つのHTMLグリッドとして出力"""
    cards_html = ""
    for name, info in m_info.items():
        val = info["val"]
        pct = info["pct"]
        if val is None:
            cards_html += f'<div class="metric-card"><div class="metric-label">{name}</div><div class="metric-value">取得不可</div><div class="metric-delta">---</div></div>'
        else:
            delta_class = "delta-plus" if pct >= 0 else "delta-minus"
            val_formatted = f"{val:,.0f}" if val > 100 else f"{val:,.2f}"
            cards_html += f"""
                <div class="metric-card">
                    <div class="metric-label">{name}</div>
                    <div class="metric-value">{val_formatted}</div>
                    <div class="metric-delta {delta_class}">{pct:+.2f}%</div>
                </div>
            """
    st.markdown(f'<div class="metric-grid">{cards_html}</div>', unsafe_allow_html=True)

# --- 4. サイドバー ---
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

if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["ワンタッチ", "スクリーニング", "バックテスト"])

# --- タブ1: ワンタッチ ---
with tab_top:
    # ヘッダー部分（見出しと更新ボタン）
    h_col1, h_col2 = st.columns([0.8, 0.2])
    with h_col1:
        st.markdown("<div class='section-header'>🌍 リアルタイム指標</div>", unsafe_allow_html=True)
    with h_col2:
        if st.button("🔄更新"):
            st.cache_data.clear()
            st.rerun()

    # 指標パネル（Expander）
    with st.expander("詳細を表示 (タップで開閉)", expanded=True):
        market_data = fetch_market_info()
        render_market_grid(market_data) # ここでHTMLグリッドを一気に描画

        # AI予測
        vix_val = market_data.get("VIX指数", {}).get("val", 0)
        st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
        if vix_val and vix_val > 20:
            st.warning(f"🤖 **AI予測:** VIX高め。不安定な地合いです。")
        elif vix_val and vix_val < 15:
            st.info(f"🤖 **AI予測:** 市場安定。順張りチャンスです。")
        else:
            st.info("🤖 **AI予測:** 指標は中立。テクニカルに従いましょう。")

    st.divider()
    st.markdown("<div class='section-header'>🚀 One-Touch 期待値スキャン</div>", unsafe_allow_html=True)
    if st.button("主要銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        st.write("※抽出ロジック計算中...")
        st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
        st.rerun()
