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
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } .card-value { font-size: 22px !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; }
    .card-label { font-size: 12px; color: #aaaaaa; margin: 0; padding: 0; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; padding: 0; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; width: fit-content; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }
    div.stButton > button { padding: 2px 12px !important; font-size: 13px !important; border-radius: 4px !important; }
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    .ai-label { color: #60a5fa; font-weight: bold; font-size: 14px; margin-bottom: 5px; }
    .ai-text { color: #d1d5db; font-size: 13px; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 定数 & データ取得 ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "1802.T": "大林組", "1812.T": "鹿島建設", "3436.T": "SUMCO",
    "4403.T": "日油", "4506.T": "住友ファーマ", "4507.T": "塩野義製薬", "4568.T": "第一三共",
    "5020.T": "ENEOS", "6315.T": "TOWA", "6361.T": "荏原製作所", "6460.T": "セガサミー",
    "6501.T": "日立", "6506.T": "安川電機", "6702.T": "富士通", "6723.T": "ルネサス",
    "6758.T": "ソニーG", "6762.T": "TDK", "6902.T": "デンソー", "6920.T": "レーザーテック",
    "6963.T": "ローム", "6981.T": "村田製作所", "7003.T": "三井E&S", "7011.T": "三菱重工",
    "7013.T": "IHI", "7203.T": "トヨタ", "7269.T": "スズキ", "7270.T": "SUBARU",
    "7453.T": "良品計画", "7751.T": "キャノン", "7752.T": "リコー", "8002.T": "丸紅",
    "8031.T": "三井物産", "8053.T": "住友商事", "8058.T": "三菱商事", "8267.T": "イオン",
    "8306.T": "三菱UFJ", "9433.T": "KDDI", "9502.T": "中部電力", "9843.T": "ニトリ",
    "9984.T": "ソフトバンクG", "1570.T": "日経レバ"
}

MARKET_INDICES = {
    "日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
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

def run_fast_backtest(ticker, days_back, strict_mode=True):
    """スキャン用の高速バックテストロジック"""
    start_date = datetime.now() - timedelta(days=days_back)
    try:
        df = yf.download(ticker, start=start_date, interval="5m", progress=False, multi_level_index=False)
        if df.empty or len(df) < 15: return None
        
        df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
        pnls = []
        unique_dates = np.unique(df.index.date)
        
        for date in unique_dates:
            day = df[df.index.date == date].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            
            # 条件緩和の制御
            entry_end = time(9, 20) if strict_mode else time(10, 0)
            
            in_pos = False
            for ts, row in day.iterrows():
                cur_t = ts.time()
                if not in_pos and time(9,0) <= cur_t <= entry_end:
                    # 判定条件
                    c_vwap = row['Close'] > row['VWAP']
                    c_ema = row['Close'] > row['EMA5']
                    
                    if strict_mode:
                        can_entry = c_vwap and c_ema
                    else:
                        can_entry = c_vwap # 緩和モードはVWAPのみ
                    
                    if can_entry:
                        entry_p = row['Close'] * 1.0003
                        in_pos = True; trail_high = row['High']
                elif in_pos:
                    if row['High'] > trail_high: trail_high = row['High']
                    # 利確・損切り（損切り-0.8%固定）
                    if row['Low'] <= entry_p * 0.992 or cur_t >= time(14, 55):
                        exit_p = row['Close'] * 0.9997
                        pnls.append((exit_p - entry_p) / entry_p)
                        in_pos = False; break
        return np.mean(pnls) if pnls else None
    except: return None

# --- 4. メインレイアウト ---
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 class='main-title'>FORE CASTER</h1>
        <h3 class='sub-title'>SCREENING & BACKTEST | ver 1.3</h3>
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
        ai_msg = "地合いは中立的です。個別のテクニカルサインを重視しましょう。"
        if vix_val and vix_val > 20: ai_msg = f"VIX指数が {vix_val:.1f} と警戒水準です。突発的な変動に備えリスク管理を徹底してください。"
        elif vix_val and vix_val < 15: ai_msg = f"VIX指数は {vix_val:.1f} で安定しています。順張りロジックが機能しやすい良好な地合いです。"
        st.markdown(f'<div class="ai-box"><div class="ai-label">🤖 AI予測</div><div class="ai-text">{ai_msg}</div></div>', unsafe_allow_html=True)
        st.write("")

    st.divider()
    if st.button("ワンタッチで銘柄スキャン", type="primary", use_container_width=True):
        results = []
        status_area = st.empty()
        progress_bar = st.progress(0)
        
        ticker_list = list(TICKER_NAME_MAP.keys())
        
        # --- SCAN STEP 1: STRICT ---
        status_area.info("Step 1: 厳選スキャン実行中...")
        for i, t in enumerate(ticker_list):
            progress_bar.progress((i + 1) / len(ticker_list))
            ev = run_fast_backtest(t, days_back=15, strict_mode=True)
            if ev is not None and ev > 0:
                results.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
        
        # --- SCAN STEP 2: FALLBACK (if results < 5) ---
        if len(results) < 5:
            status_area.warning("期待値プラスの銘柄をさらに探索中（条件緩和モード）...")
            existing_codes = [r['code'] for r in results]
            for t in ticker_list:
                if t in existing_codes: continue
                ev = run_fast_backtest(t, days_back=20, strict_mode=False)
                if ev is not None and ev > -0.001: # ほぼトントンの銘柄まで許容
                    results.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
                    if len(results) >= 10: break # 最大10銘柄まで
        
        status_area.empty()
        progress_bar.empty()
        
        if results:
            # 期待値順に並べてTop5抽出
            top5 = sorted(results, key=lambda x: x['ev'], reverse=True)[:5]
            st.session_state['target_tickers'] = ", ".join([d['code'] for d in top5])
            
            st.success("🎯 スキャン完了！期待値Top5を選出しました。")
            # 結果表示
            res_df = pd.DataFrame(top5)
            res_df.columns = ["コード", "銘柄名", "期待値(Avg PnL)"]
            res_df["期待値(Avg PnL)"] = res_df["期待値(Avg PnL)"].apply(lambda x: f"{x:+.3%}")
            st.table(res_df)
            st.rerun() # 上部のテキスト入力欄を更新するためにリロード
        else:
            st.error("残念ながら、現在の地合いで推奨できる銘柄が見つかりませんでした。")
