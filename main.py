import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone, time

# 外部モジュールのインポート
from const import TICKER_NAME_MAP, MARKET_INDICES
import logic_core as core

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. デザインCSS (デザイン調整版) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 40px !important; margin: 0 !important; padding: 0 !important; }
    .sub-title { font-weight: 300 !important; font-size: 18px !important; margin: 0 !important; color: #aaaaaa !important; }
    
    /* 指標カードの余白調整 */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; width: 100%; margin-top: 10px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; text-align: center; }
    .card-label { font-size: 11px; color: #aaaaaa; }
    .card-value { font-size: 22px; font-weight: 600; color: #ffffff; }
    
    /* サブタブのフォントサイズ調整 */
    button[data-baseweb="tab"] p { font-size: 14px !important; }
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
                latest = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

# --- 4. サイドバー設定 (共通) ---
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

# --- 5. メインヘッダー ---
st.markdown(f"<div><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>ver 3.0 | Screening & Backtest</h3></div>", unsafe_allow_html=True)

# --- 6. メインタブ構成 ---
tab_top, tab_screen, tab_bt, tab_rank = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト", "🏆 ランキング"])

# --- タブ1: ワンタッチ (指標ウォッチを内包) ---
with tab_top:
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    
    # ここに指標ウォッチを配置（スマホでボタンのすぐ上に表示される）
    with st.expander(f"🕒 市場指標ウォッチ ▶︎ {now_jst}", expanded=True):
        cards_html = '<div class="metric-grid">'
        for n in MARKET_INDICES.keys():
            i = m_data.get(n, {})
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
        
    if st.button("🚀 ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        st.info("ここにワンタッチロジックを実装します。")

# --- タブ3: バックテスト (BACK TESTER 6.3 の 6 つのタブを移植) ---
with tab_bt:
    ticker_in = st.text_input("🎯 監視銘柄コード (カンマ区切り)", "8267.T", key="bt_ticker_input")
    tickers = [t.strip() for t in ticker_in.split(",") if t.strip()]
    
    if st.button("📊 バックテスト実行", type="primary", use_container_width=True):
        end_date = datetime.now(); start_date = end_date - timedelta(days=days_back)
        all_trades = []; t_names = {}
        pb = st.progress(0); st_text = st.empty()
        for i, t in enumerate(tickers):
            st_text.text(f"Testing {t}..."); pb.progress((i+1)/len(tickers))
            df = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
            p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
            all_trades.extend(core.run_ticker_simulation(t, df, p_map, o_map, a_map, params))
            t_names[t] = TICKER_NAME_MAP.get(t, t)
        st.session_state['res_df'] = pd.DataFrame(all_trades)
        st.session_state['t_names'] = t_names
        st.rerun()

    # --- 分析結果のサブタブ (6.3統合) ---
    if 'res_df' in st.session_state and not st.session_state['res_df'].empty:
        res_df = st.session_state['res_df']; t_names = st.session_state['t_names']
        sub_tabs = st.tabs(["📊 サマリー", "🏅 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ"])
        
        with sub_tabs[0]: # 📊 サマリー
            wins = res_df[res_df['PnL'] > 0]; losses = res_df[res_df['PnL'] <= 0]
            pf = wins['PnL'].sum() / abs(losses['PnL'].sum()) if not losses.empty else 0
            st.markdown(f"""
            <div style='display:grid; grid-template-columns:repeat(4,1fr); gap:10px;'>
                <div class='summary-box'><div class='card-label'>回数</div><div class='card-value'>{len(res_df)}</div></div>
                <div class='summary-box'><div class='card-label'>勝率</div><div class='card-value'>{(len(wins)/len(res_df)):.1%}</div></div>
                <div class='summary-box'><div class='card-label'>PF</div><div class='card-value'>{pf:.2f}</div></div>
                <div class='summary-box'><div class='card-label'>期待値</div><div class='card-value'>{res_df['PnL'].mean():.2%}</div></div>
            </div>""", unsafe_allow_html=True)
            # レポートテキスト等の詳細は後ほど関数化してスッキリさせます
        
        # ※ tab2〜tab6 の具体的な表示ロジックは、以前作成したコードをこのブロック内に順次組み込んでいきます
        with sub_tabs[5]: # 📝 詳細ログ
             st.info("詳細ログをここに表示します。")

        if st.button("♻️ バックテスト結果をリセット", key="reset_bt_main"):
            st.session_state['res_df'] = pd.DataFrame(); st.rerun()
