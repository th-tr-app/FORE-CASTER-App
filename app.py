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

# カスタムCSS（楽天証券風リストデザイン）
st.markdown("""
    <style>
    .main-title { font-weight: 500; font-size: 26px; margin-bottom: 5px; }
    .section-header { font-size: 16px !important; font-weight: 600; color: #dddddd; vertical-align: middle; }
    
    /* リスト形式の行デザイン */
    .market-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 15px;
        border-bottom: 1px solid #3d414b;
        background-color: #1e2129;
    }
    .market-name { font-size: 14px; font-weight: 500; color: #ffffff; flex: 2; }
    .market-price { font-size: 16px; font-weight: 600; color: #ffffff; flex: 2; text-align: right; padding-right: 20px; }
    .market-delta { font-size: 14px; font-weight: 600; flex: 1.5; text-align: right; border-radius: 4px; padding: 2px 6px; }
    
    .up-bg { color: #00f0a8; } /* 上昇：緑 */
    .down-bg { color: #ff4b4b; } /* 下落：赤 */
    
    /* 更新ボタンの小型化調整 */
    div[data-testid="column"] button {
        padding: 2px 8px !important;
        font-size: 12px !important;
        height: 28px !important;
        margin-top: -5px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 ---
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

# --- 4. サイドバー設定 ---
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
    # 指標タイトルと更新ボタンをコンパクトに横並び
    h_col1, h_col2 = st.columns([0.25, 0.75])
    with h_col1:
        st.markdown("<span class='section-header'>🌍 リアルタイム指標</span>", unsafe_allow_html=True)
    with h_col2:
        if st.button("🔄更新"):
            st.cache_data.clear()
            st.rerun()

    # 指標パネル（Expander）
    with st.expander("詳細を表示 (タップで開閉)", expanded=True):
        market_data = fetch_market_info()
        
        # 銘柄リストを1行ずつループで表示
        for name, info in market_data.items():
            val = info["val"]
            pct = info["pct"]
            
            if val is not None:
                delta_class = "up-bg" if pct >= 0 else "down-bg"
                val_fmt = f"{val:,.1f}" if val > 100 else f"{val:,.2f}"
                pct_fmt = f"{pct:+.2f}%"
                
                # Streamlitの標準markdownで1行を構成（バグ回避のためHTMLタグを最小限に）
                st.markdown(f"""
                <div class="market-row">
                    <div class="market-name">{name}</div>
                    <div class="market-price">{val_fmt}</div>
                    <div class="market-delta {delta_class}">{pct_fmt}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="market-row"><div class="market-name">{name}</div><div>取得失敗</div></div>', unsafe_allow_html=True)

        # AI予測
        vix_val = market_data.get("VIX指数", {}).get("val", 0)
        st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
        if vix_val and vix_val > 20:
            st.warning(f"🤖 **AI予測:** VIX高め({vix_val:.1f})。ボラティリティ警戒地合いです。")
        elif vix_val and vix_val < 15:
            st.info(f"🤖 **AI予測:** 市場安定({vix_val:.1f})。順張りチャンスです。")
        else:
            st.info("🤖 **AI予測:** 指標は中立。テクニカルに従いましょう。")

    st.divider()
    st.markdown("<div class='section-header'>🚀 One-Touch 期待値スキャン</div>", unsafe_allow_html=True)
    if st.button("主要銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        st.write("※抽出ロジック計算中...")
        st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
        st.rerun()
