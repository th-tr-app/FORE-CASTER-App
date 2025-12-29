import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
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
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } .card-value { font-size: 22px !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 定数 ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "1802.T": "大林組", "1812.T": "鹿島建設", "3436.T": "SUMCO",
    "4507.T": "塩野義製薬", "4568.T": "第一三共", "5020.T": "ENEOS", "6501.T": "日立",
    "6758.T": "ソニーG", "6920.T": "レーザーテック", "7011.T": "三菱重工", "7013.T": "IHI",
    "7203.T": "トヨタ", "8031.T": "三井物産", "8306.T": "三菱UFJ", "9984.T": "ソフトバンクG",
    "1570.T": "日経レバ" # 走査速度のため主要銘柄に絞り込み
}

MARKET_INDICES = {
    "日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

# --- 4. 関数定義 ---
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

def run_scan_engine(ticker, days_back, entry_start, entry_end, use_vwap):
    """時間と条件を考慮したバックテストエンジン"""
    try:
        start_date = datetime.now() - timedelta(days=days_back)
        df = yf.download(ticker, start=start_date, interval="5m", progress=False, multi_level_index=False)
        if df.empty: return None
        
        # タイムゾーンを日本時間に統一
        df.index = df.index.tz_convert('Asia/Tokyo')
        df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
        
        pnls = []
        unique_dates = np.unique(df.index.date)
        for d in unique_dates:
            day = df[df.index.date == d].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            
            in_pos = False
            for ts, row in day.iterrows():
                cur_t = ts.time()
                if not in_pos and entry_start <= cur_t <= entry_end:
                    if not use_vwap or (row['Close'] > row['VWAP']):
                        entry_p = row['Close'] * 1.0003
                        in_pos = True; trail_high = row['High']
                elif in_pos:
                    if row['High'] > trail_high: trail_high = row['High']
                    if row['Low'] <= entry_p * 0.992 or cur_t >= time(14, 55):
                        exit_p = row['Close'] * 0.9997
                        pnls.append((exit_p - entry_p) / entry_p)
                        in_pos = False; break
        return np.mean(pnls) if pnls else None
    except: return None

# --- 5. メインレイアウト ---
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 class='main-title'>FORE CASTER</h1>
        <h3 class='sub-title'>SCREENING & BACKTEST | ver 1.4</h3>
    </div>
    """, unsafe_allow_html=True)

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    if st.button("🔄 更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        market_data = fetch_market_info()
        cards_html = '<div class="metric-grid">'
        for name, info in market_data.items():
            if info["val"] is not None:
                val = f"{info['val']:,.1f}" if info['val'] > 200 else f"{info['val']:,.2f}"
                pct = info['pct']; cls = "plus" if pct >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{name}</div><div class="card-value">{val}</div><div class="delta-badge {cls}">{"＋" if pct >= 0 else ""}{pct:.2f}%</div></div>'
            else: cards_html += f'<div class="metric-card"><div class="card-label">{name}</div><div class="card-value">N/A</div></div>'
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)
        
        vix_val = market_data.get("VIX指数", {}).get("val", 0)
        ai_msg = f"VIX指数は {vix_val:.1f} です。地合いに合わせた戦略を選択してください。"
        st.markdown(f'<div class="ai-box"><div style="color:#60a5fa; font-weight:bold;">🤖 AI予測</div><div style="color:#d1d5db; font-size:13px;">{ai_msg}</div></div>', unsafe_allow_html=True)

    st.divider()
    
    # --- スキャン条件設定パネル ---
    with st.expander("🔍 スキャン条件設定 (抽出されない場合はここを調整)", expanded=False):
        s_days = st.slider("分析期間 (過去日数)", 5, 30, 20)
        s_start = st.time_input("エントリー開始", time(9, 0))
        s_end = st.time_input("エントリー終了", time(9, 30))
        s_vwap = st.checkbox("VWAP条件を必須にする", value=True)

    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        results = []
        progress = st.progress(0)
        status = st.empty()
        
        tickers = list(TICKER_NAME_MAP.keys())
        for i, t in enumerate(tickers):
            status.text(f"スキャン中... {t} ({TICKER_NAME_MAP[t]})")
            progress.progress((i + 1) / len(tickers))
            ev = run_scan_engine(t, s_days, s_start, s_end, s_vwap)
            if ev is not None and ev > 0:
                results.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
        
        # 緩和モード (もし見つからない場合)
        if len(results) < 3:
            status.warning("条件を緩和して再走査中...")
            for t in tickers:
                if any(r['code'] == t for r in results): continue
                ev = run_scan_engine(t, s_days, s_start, time(11, 0), False)
                if ev is not None and ev > -0.001:
                    results.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
        
        status.empty(); progress.empty()
        
        if results:
            top5 = sorted(results, key=lambda x: x['ev'], reverse=True)[:5]
            st.session_state['target_tickers'] = ", ".join([d['code'] for d in top5])
            st.success("🎯 期待値Top5を選出しました。監視銘柄コードを更新しました。")
            st.table(pd.DataFrame(top5).rename(columns={'code':'コード','name':'銘柄名','ev':'期待値'}))
            st.rerun()
        else:
            st.error("残念ながら、現在の条件で推奨できる銘柄が見つかりませんでした。設定パネルで「期間」を延ばすか「終了時間」を遅くしてください。")
