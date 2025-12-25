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

# --- 2. カスタムCSS (視認性向上・フラットデザイン) ---
st.markdown("""
    <style>
    /* タイトルエリア */
    .main-title { font-weight: 400; font-size: 46px; margin: 0; padding: 0; }
    .sub-title { font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa; }

    /* リアルタイム指標ヘッダー */
    .header-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 15px;
        margin-bottom: 5px;
    }
    .section-title {
        font-size: 22px;
        font-weight: 600;
        color: #eeeeee;
    }

    /* 指標カード（背景同化・フォント拡大） */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 15px;
        width: 100%;
        margin-top: 10px;
    }
    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
        .card-value { font-size: 24px !important; } /* スマホでも大きく表示 */
    }

    .metric-card {
        background-color: transparent; /* 背景色と同じに */
        border: none; /* 枠線を消去 */
        padding: 5px;
        display: flex;
        flex-direction: column;
    }
    .card-label { font-size: 14px; color: #aaaaaa; margin-bottom: 2px; }
    .card-value { font-size: 28px; font-weight: 600; color: #ffffff; }
    
    .delta-badge {
        font-size: 13px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        width: fit-content;
        margin-top: 5px;
    }
    .plus { background-color: #1e3a2a; color: #00f0a8; }
    .minus { background-color: #3a1e1e; color: #ff4b4b; }

    /* 更新ボタン */
    div.stButton > button {
        padding: 4px 12px !important;
        font-size: 14px !important;
        height: auto !important;
    }

    /* AI予測ボックス */
    .ai-box {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 15px;
        margin-top: 20px;
    }
    .ai-label { color: #60a5fa; font-weight: bold; font-size: 15px; margin-bottom: 5px; }
    .ai-text { color: #d1d5db; font-size: 14px; line-height: 1.6; }
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

# タイトルエリア
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 class='main-title'>FORE CASTER</h1>
        <h3 class='sub-title'>SCREENING & BACKTEST | ver 1.01</h3>
    </div>
    """, unsafe_allow_html=True)

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    # 指標タイトルとボタン
    st.markdown('<div class="header-row"><span class="section-title">🌍 リアルタイム指標</span></div>', unsafe_allow_html=True)
    if st.button("🔄 更新"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("詳細を表示 (タップで開閉)", expanded=True):
        market_data = fetch_market_info()
        
        # 指標カード
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

        # AI予測の表示（ここで確実に描画）
        vix_val = market_data.get("VIX指数", {}).get("val", 0)
        ai_msg = "市場指標は中立です。個別のテクニカルサインを重視しましょう。"
        if vix_val and vix_val > 20:
            ai_msg = f"VIX指数が {vix_val:.1f} と警戒水域です。ボラティリティの拡大に備え、ポジションサイズを調整してください。"
        elif vix_val and vix_val < 15:
            ai_msg = f"VIX指数は {vix_val:.1f} で非常に安定しています。順張りロジックが機能しやすい良好な地合いです。"

        st.markdown(f"""
            <div class="ai-box">
                <div class="ai-label">🤖 AI予測</div>
                <div class="ai-text">{ai_msg}</div>
            </div>
        """, unsafe_allow_html=True)

    st.divider()
    if st.button("Top5を自動抽出", type="primary", use_container_width=True):
        st.info("期待値スキャン中...")
