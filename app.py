import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, timezone, time

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS ---
st.markdown("""
    <style>
    .main-title { font-weight: 400; font-size: 46px; margin: 0; padding: 0; }
    .sub-title { font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa; }

    /* 指標カード */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { 
        background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; 
        padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; 
    }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }

    /* チェックボックスサイズ調整 */
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }

    /* サイドバーの選択中ボタンの強調（枠線や色） */
    .active-btn {
        border: 2px solid #ff4b4b !important;
        background-color: #3a1e1e !important;
        color: white !important;
    }

    /* AI予測ボックス */
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. セッション管理 & 定数 ---
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8267.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"

# --- 4. サイドバー (戦略プリセット: 縦並び & 視覚化) ---
st.sidebar.markdown("### ♙ 戦略プリセット")

# 各プリセットの状態に応じてラベルを変更
label_normal = "通常フィルター" + (" [ 選択中 ]" if st.session_state['preset'] == "NORMAL" else "")
label_defensive = "ディフェンシブ" + (" [ 選択中 ]" if st.session_state['preset'] == "DEFENSIVE" else "")
label_range = "横ばい相場対応" + (" [ 選択中 ]" if st.session_state['preset'] == "RANGE" else "")

# 縦に配置
if st.sidebar.button(label_normal, type="secondary" if st.session_state['preset'] != "NORMAL" else "primary"):
    st.session_state['preset'] = "NORMAL"
    st.rerun()

if st.sidebar.button(label_defensive, type="secondary" if st.session_state['preset'] != "DEFENSIVE" else "primary"):
    st.session_state['preset'] = "DEFENSIVE"
    st.rerun()

if st.sidebar.button(label_range, type="secondary" if st.session_state['preset'] != "RANGE" else "primary"):
    st.session_state['preset'] = "RANGE"
    st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
start_entry_time = st.sidebar.time_input("開始時間", time(9, 0), step=300)
end_entry_time = st.sidebar.time_input("終了時間", time(9, 15), step=300)

st.sidebar.markdown("<br>", unsafe_allow_html=True)

st.sidebar.subheader("📉 エントリー条件")
use_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
use_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
use_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
use_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)

st.sidebar.divider()
gap_min = st.sidebar.slider("寄付ギャップダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
gap_max = st.sidebar.slider("寄付ギャップアップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100

st.sidebar.subheader("💰 決済ルール")
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
trailing_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, 0.05) / 100

# --- 5. メインレイアウト ---
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>FORE CASTER</h1>
        <h3 style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>SCREENING & BACKTEST | ver 1.62</h3>
    </div>
    """, unsafe_allow_html=True)

st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

# 以降のタブやバックテストロジックは以前のバージョンを継承
# (ここではコード量を抑えるため省略しますが、実際のファイルにはバックテストロジックが含まれます)
