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

# --- 2. カスタムCSS (枠線復活・行間凝縮) ---
st.markdown("""
    <style>
    /* タイトルエリア */
    .main-title { font-weight: 400; font-size: 46px; margin: 0; padding: 0; }
    .sub-title { font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa; }

    /* 指標カード（中央揃え・行間凝縮・枠線あり） */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        width: 100%;
        margin-top: 5px;
    }
    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
        .card-value { font-size: 22px !important; }
    }

    .metric-card {
        background-color: #1e2129;
        border: 1px solid #3d414b; /* 枠線を復活 */
        border-radius: 6px;
        padding: 8px 5px; /* 上下余白を絞る */
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 0px; /* 行間を極小化 */
    }
    .card-label { font-size: 12px; color: #aaaaaa; margin: 0; padding: 0; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; padding: 0; }
    
    /* 騰落率バッジ (日本式：上昇レッド / 下落グリーン) */
    .delta-badge {
        font-size: 12px;
        font-weight: 600;
        padding: 1px 8px;
        border-radius: 4px;
        width: fit-content;
        margin-top: 2px;
    }
    .plus { background-color: #3a1e1e; color: #ff4b4b; } /* 上昇：レッド */
    .minus { background-color: #1e3a2a; color: #00f0a8; } /* 下落：グリーン */

    /* 更新ボタン (左揃え) */
    div.stButton > button {
        padding: 2px 12px !important;
        font-size: 13px !important;
        border-radius: 4px !important;
    }

    /* AI予測ボックス */
    .ai-box {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 12px;
        margin-top: 15px;
    }
    .ai-label { color: #60a5fa; font-weight: bold; font-size: 14px; margin-bottom: 3px; }
    .ai-text { color: #d1d5db; font-size: 13px; line-height: 1.5; }
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
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>FORE CASTER</h1>
        <h3 style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>SCREENING & BACKTEST | ver 1.2</h3>
    </div>
    """, unsafe_allow_html=True)

# 監視銘柄入力
if 'target_tickers' not in st.session_state: 
    st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    # 更新ボタンを左揃え
    if st.button("🔄 更新"):
        st.cache_data.clear()
        st.rerun()

    # 今日の日付を取得してタイトルに反映
    today_str = datetime.now().strftime('%Y/%m/%d')
    with st.expander(f"リアルタイム指標 ({today_str})", expanded=True):
        market_data = fetch_market_info()
        
        # 指標カードグリッド
        cards_html = '<div class="metric-grid">'
        for name, info in market_data.items():
            if info["val"] is not None:
                val = f"{info['val']:,.1f}" if info['val'] > 100 else f"{info['val']:,.2f}"
                pct = info['pct']
                # 日本式：＋ならレッド(plus)、－ならグリーン(minus)
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

        # AI予測
        vix_val = market_data.get("VIX指数", {}).get("val", 0)
        ai_msg = "地合いは中立的です。個別のテクニカルサインを重視しましょう。"
        if vix_val and vix_val > 20:
            ai_msg = f"VIX指数が {vix_val:.1f} と警戒水準です。突発的な変動に備えリスク管理を徹底してください。"
        elif vix_val and vix_val < 15:
            ai_msg = f"VIX指数は {vix_val:.1f} で安定しています。順張りロジックが機能しやすい良好な地合いです。"

        st.markdown(f"""
            <div class="ai-box">
                <div class="ai-label">🤖 AI予測</div>
                <div class="ai-text">{ai_msg}</div>
            </div>
        """, unsafe_allow_html=True)

    st.divider()
    if st.button("Top5を自動抽出", type="primary", use_container_width=True):
        st.info("銘柄スキャンを開始します...")
