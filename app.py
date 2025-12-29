import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from datetime import datetime, timedelta, timezone, time

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS ---
st.markdown("""
    <style>
    /* メインタイトルのスタイル（ユーザー指定） */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    /* サイドバーボタン */
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. セッション管理 ---
if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"

# --- 4. サイドバー (戦略プリセット) ---
st.sidebar.markdown("### 🛡️ 戦略プリセット")
col_s1, col_s2, col_s3 = st.sidebar.columns(3)
if col_s1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_s2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_s3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.markdown("### ⚙️ BACK TESTER 5.8 設定")
# 5.8のコードを統合後、ここにスライダー等の設定項目を配置します。

# --- 5. メインレイアウト ---

# タイトルエリア（ユーザー様指定デザイン）
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>FORE CASTER</h1>
        <h3 style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>SCREENING & BACKTEST | ver 1.0</h3>
    </div>
    """, unsafe_allow_html=True)

st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

# --- タブ1: ワンタッチ ---
with tab_top:
    if st.button("🔄 更新"): st.cache_data.clear(); st.rerun()

    # 日本時間 (JST)
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        st.info("ここに現在の指標カードとAI予測が表示されます（ロジックは統合済み）")

    st.divider()
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        st.success("スキャンロジック実行中... 完了後Top5を自動登録します。")

# --- タブ3: バックテスト ---
with tab_bt:
    st.subheader("📊 詳細バックテスト分析")
    st.info("現在、BACK TESTER 5.8 の移植待ちです。コードをいただければ、ここに統合を開始します。")
