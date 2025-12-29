import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from datetime import datetime, timedelta, timezone, time

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS (デザイン最終調整) ---
st.markdown("""
    <style>
    /* タイトルエリア (ver 1.62 ユーザー指定デザイン) */
    .main-title { font-weight: 400; font-size: 46px; margin: 0; padding: 0; }
    .sub-title { font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa; }

    /* 指標カード（中央揃え・背景透過・枠線あり） */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { 
        background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; 
        padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; 
    }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; } /* 日本式：上昇レッド */
    .minus { background-color: #1e3a2a; color: #00f0a8; } /* 日本式：下落グリーン */

    /* 更新ボタン (左揃え) */
    div.stButton > button { padding: 2px 12px !important; font-size: 13px !important; border-radius: 4px !important; }

    /* サイドバーボタンの幅調整 */
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; }

    /* AI予測ボックス */
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. セッション管理 & 定数 ---
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8306.T, 7011.T"
if 'scan_results' not in st.session_state: st.session_state['scan_results'] = []

TICKER_NAME_MAP = {
    "1605.T": "INPEX", "3436.T": "SUMCO", "4568.T": "第一三共", "6501.T": "日立",
    "6758.T": "ソニーG", "6920.T": "レーザーテック", "7011.T": "三菱重工", "7013.T": "IHI",
    "7203.T": "トヨタ", "8306.T": "三菱UFJ", "9984.T": "ソフトバンクG", "1570.T": "日経レバ"
}

MARKET_INDICES = {
    "日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

# --- 4. ロジック関数 ---
@st.cache_data(ttl=300)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="2d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

def run_scan_engine(ticker, days_back):
    """銘柄スキャン用計算エンジン"""
    try:
        df = yf.download(ticker, start=datetime.now()-timedelta(days=days_back), interval="5m", progress=False)
        if df.empty: return None
        df.index = df.index.tz_convert('Asia/Tokyo')
        
        pnls = []
        for d in np.unique(df.index.date):
            day = df[df.index.date == d].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            in_pos = False
            for ts, row in day.iterrows():
                if not in_pos and time(9,0) <= ts.time() <= time(9,15):
                    if row['Close'] > row['VWAP']:
                        entry_p = row['Close'] * 1.0003; in_pos = True
                elif in_pos:
                    if row['Low'] <= entry_p * 0.992 or ts.time() >= time(14, 55):
                        exit_p = row['Close'] * 0.9997; pnls.append((exit_p - entry_p) / entry_p); in_pos = False; break
        return np.mean(pnls) if pnls else None
    except: return None

# --- 5. サイドバー (戦略プリセット) ---
st.sidebar.markdown("### 🛡️ 戦略プリセット")
col_s1, col_s2, col_s3 = st.sidebar.columns(3)
if col_s1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_s2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_s3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.markdown("### ⚙️ BACK TESTER 5.8 設定")
# 5.8のコードを統合次第、ここにスライダー等を配置

# --- 6. メインレイアウト ---
# タイトルエリア
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

    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info()
        cards_html = '<div class="metric-grid">'
        for n, i in m_data.items():
            if i.get("val"):
                val = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{val}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
        
        vix = m_data.get("VIX指数", {}).get("val", 0)
        ai_msg = f"VIX指数は {vix:.1f} です。安定した地合いなら順張り、荒れ相場なら逆張りや防御を検討してください。"
        st.markdown(f'<div class="ai-box"><div style="color:#60a5fa; font-weight:bold;">🤖 AI予測</div><div style="color:#d1d5db; font-size:13px;">{ai_msg}</div></div>', unsafe_allow_html=True)

    st.divider()
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        results = []
        progress = st.progress(0)
        tickers = list(TICKER_NAME_MAP.keys())
        for i, t in enumerate(tickers):
            progress.progress((i + 1) / len(tickers))
            ev = run_scan_engine(t, days_back=20)
            if ev and ev > 0: results.append({"コード": t, "銘柄名": TICKER_NAME_MAP[t], "期待値": f"{ev:+.3%}"})
        
        if results:
            top5 = results[:5]
            st.session_state['scan_results'] = top5
            st.session_state['target_tickers'] = ", ".join([d['コード'] for d in top5])
            st.success("スキャン完了！監視銘柄を更新しました。")
            st.rerun()
        else:
            st.error("推奨銘柄が見つかりませんでした。条件を緩和してください。")

    if st.session_state['scan_results']:
        st.markdown("#### 🚀 本日の期待値Top5")
        st.table(st.session_state['scan_results'])

# --- タブ3: バックテスト ---
with tab_bt:
    st.info("ここに BACK TESTER 5.8 をまるごと移植します。コードをいただければ統合を開始します。")
