import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS (バグ防止とカードデザイン) ---
st.markdown("""
    <style>
    /* リアルタイム指標ヘッダーの横並び */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .header-title {
        font-size: 20px;
        font-weight: 600;
        color: #eeeeee;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* グリッドシステム (PC:4列 / スマホ:2列) */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        width: 100%;
    }

    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
    }

    /* カード単体のデザイン (sample01.jpgの再現) */
    .metric-card {
        background-color: #1e2129;
        border: 1px solid #3d414b;
        border-radius: 8px;
        padding: 12px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 100px;
    }
    .card-label { font-size: 11px; color: #aaaaaa; margin-bottom: 5px; }
    .card-value { font-size: 22px; font-weight: 600; color: #ffffff; }
    
    /* 騰落率バッジ */
    .delta-badge {
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        width: fit-content;
        margin-top: 8px;
    }
    .plus { background-color: #1e3a2a; color: #00f0a8; border: 1px solid #2e5a3a; }
    .minus { background-color: #3a1e1e; color: #ff4b4b; border: 1px solid #5a2e2e; }

    /* 更新ボタンを小さく右寄せ */
    div.stButton > button {
        padding: 2px 10px !important;
        font-size: 12px !important;
        height: auto !important;
        border-radius: 4px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. データ取得 ---
MARKET_INDICES = {
    "日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油先物(WTI)": "CL=F", "Gold(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

@st.cache_data(ttl=300)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
            else: data[name] = {"val": None, "pct": None}
        except: data[name] = {"val": None, "pct": None}
    return data

# --- 4. メインレイアウト ---

# タイトルエリア (ユーザーによる微調整済み)
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>FORE CASTER</h1>
        <h3 style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>SCREENING & BACKTEST | ver 1.0</h3>
    </div>
    """, unsafe_allow_html=True)

# 監視銘柄入力
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    # 指標タイトルとボタンの横並び
    h_col1, h_col2 = st.columns([0.8, 0.2])
    with h_col1:
        st.markdown('<div class="header-title">🌍 リアルタイム指標</div>', unsafe_allow_html=True)
    with h_col2:
        if st.button("🔄 更新"):
            st.cache_data.clear()
            st.rerun()

    # 指標カードグリッドの描画
    with st.expander("詳細を表示 (タップで開閉)", expanded=True):
        market_data = fetch_market_info()
        
        cards_html = '<div class="metric-grid">'
        for name, info in market_data.items():
            if info["val"] is not None:
                val = f"{info['val']:,.1f}" if info['val'] > 100 else f"{info['val']:,.2f}"
                pct = info['pct']
                cls = "plus" if pct >= 0 else "minus"
                cards_html += f"""
                    <div class="metric-card">
                        <div class="card-label">{name}</div>
                        <div class="card-value">{val}</div>
                        <div class="delta-badge {cls}">{"＋" if pct >= 0 else ""}{pct:.2f}%</div>
                    </div>"""
            else:
                cards_html += f'<div class="metric-card"><div class="card-label">{name}</div><div class="card-value">N/A</div></div>'
        cards_html += '</div>'
        
        st.markdown(cards_html, unsafe_allow_html=True)

    st.divider()
    if st.button("Top5を自動抽出", type="primary", use_container_width=True):
        st.info("期待値スキャンエンジンを実行します...")
        # (スキャンロジックは以前のものをここに統合可能)
