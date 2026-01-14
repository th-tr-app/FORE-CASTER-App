import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone, time

# 外部モジュールの読み込み
from const import TICKER_NAME_MAP, MARKET_INDICES
import logic_core as core

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. デザインCSS (v2.01完全継承 + タブ調整) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }
    
    /* 指標カード */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 15px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 16px; font-weight: 600; margin-top: 2px; }
    .plus { color: #ff4b4b; }
    .minus { color: #00f0a8; }
    
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    
    /* バックテスト・サマリー用ボックス */
    .summary-box { background-color: #262730; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #3d414b; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 市場データ取得関数 ---
@st.cache_data(ttl=300)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty:
                latest = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

# --- 4. サイドバー設定 (共通パラメーター) ---
st.sidebar.header("⚙️ パラメーター設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
s_t = st.sidebar.time_input("開始時間", time(9, 0), step=300)
e_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)

with st.sidebar.expander("📉 エントリー/決済詳細"):
    u_vwap = st.sidebar.checkbox("VWAPより上でエントリー", value=True)
    u_ema = st.sidebar.checkbox("EMA5より上でエントリー", value=True)
    u_rsi = st.sidebar.checkbox("RSIが45以上or上向き", value=True)
    u_macd = st.sidebar.checkbox("MACDが上向き", value=True)
    st.divider()
    g_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
    g_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100
    ts_s = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
    ts_w = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
    sl_f = st.sidebar.number_input("損切り (%) ※ATR非使用時", -5.0, -0.1, -0.5, 0.05) / 100
    u_atr = st.sidebar.checkbox("ATR損切りを使用", value=True)
    a_mul = st.sidebar.number_input("ATR倍率", 0.5, 5.0, 1.5, 0.1)
    a_min = st.sidebar.number_input("最低損切り (%)", 0.1, 5.0, 0.5, 0.1) / 100

params = {
    'days': days_back, 'start_t': s_t, 'end_t': e_t, 'u_vwap': u_vwap, 'u_ema': u_ema, 'u_rsi': u_rsi, 'u_macd': u_macd,
    'g_min': g_min, 'g_max': g_max, 'ts_start': ts_s, 'ts_width': ts_w, 'sl_fix': sl_f, 'u_atr': u_atr, 'atr_mul': a_mul, 'atr_min': a_min
}

# --- 5. メインヘッダー表示 ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 3.0</h3></div>", unsafe_allow_html=True)

# 指標ウォッチ
jst = timezone(timedelta(hours=9))
now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
m_data = fetch_market_info()

with st.expander(f"🕒 指標ウォッチ ▶︎ ({now_jst})", expanded=True):
    cards_html = '<div class="metric-grid">'
    for n in MARKET_INDICES.keys():
        i = m_data.get(n, {})
        if i.get("val"):
            v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
            cls = "plus" if i['pct'] >= 0 else "minus"
            cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
    st.markdown(cards_html + '</div>', unsafe_allow_html=True)

# --- 6. メインタブ構成 (ランキングを独立) ---
tab_top, tab_screen, tab_bt, tab_rank = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト", "🏆 ランキング"])

with tab_top:
    st.info("💡 ワンタッチ機能をここに移植します。")

with tab_screen:
    st.info("💡 スクリーニング機能をここに移植します。")

with tab_bt:
    st.markdown("### 📈 個別銘柄バックテスト")
    # 6.3の個別バックテスト表示ロジックをここに統合します
    st.info("サイドバーのパラメーターを反映した詳細分析を表示します。")

with tab_rank:
    st.markdown("### 🏆 登録銘柄期待値ランキング")
    st.markdown("""<p style='font-size:0.85rem; color:#808495;'>サイドバーの設定に基づき、全登録銘柄から期待値の高い銘柄を抽出します。<br><span style='color:yellow;'>『バックテスト結果をクリア』してからご利用ください。</span></p>""", unsafe_allow_html=True)
    
    if st.button("🚀 ランキング生成実行", type="primary", use_container_width=True):
        st.session_state['trigger_rank_scan'] = True
        st.rerun()

    # logic_core.py を利用したランキング表示ロジックをここに移植します
