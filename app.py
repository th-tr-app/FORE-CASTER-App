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

# --- 2. カスタムCSS (確定デザイン) ---
st.markdown("""
    <style>
    /* タイトルデザイン固定 */
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }

    /* 指標カード (🏠) */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 15px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }

    /* サマリー (📈) */
    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 18px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 11px; color: #888888; margin-bottom: 5px; }
    .summary-value { font-size: 28px; font-weight: bold; color: #ffffff; }

    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. マッピング & セッション ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "1802.T": "大林組", "1812.T": "鹿島建設", "3436.T": "SUMCO",
    "4403.T": "日油", "4506.T": "住友ファーマ", "4507.T": "塩野義製薬", "4568.T": "第一三共",
    "5020.T": "ENEOS", "6315.T": "TOWA", "6361.T": "荏原製作所", "6460.T": "セガサミーHLDGS",
    "6501.T": "日立", "6506.T": "安川電機", "6702.T": "富士通", "6723.T": "ルネサスエレクトロニクス",
    "6758.T": "ソニーグループ", "6762.T": "TDK", "6902.T": "デンソー", "6920.T": "レーザーテック",
    "6963.T": "ローム", "6981.T": "村田製作所", "7003.T": "三井E&S", "7011.T": "三菱重工業",
    "7013.T": "I H I", "7203.T": "トヨタ自動車", "7269.T": "スズキ", "7270.T": "SUBARU",
    "7453.T": "良品計画", "7751.T": "キャノン", "7752.T": "リコー", "8002.T": "丸紅",
    "8031.T": "三井物産", "8053.T": "住友商事", "8058.T": "三菱商事", "8267.T": "イオン",
    "8306.T": "三菱UFJ", "9433.T": "KDDI", "9502.T": "中部電力", "9843.T": "ニトリ",
    "9984.T": "ソフトバンクG", "1570.T": "日経レバ"
}

MARKET_INDICES = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI", "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"}

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T, 8306.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"

# --- 4. ロジック関数 ---
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

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker):
    try:
        df = yf.download(ticker, period="60d", interval="1d", progress=False, auto_adjust=True)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

def run_scan_engine(ticker, days_back, entry_start, entry_end, use_vwap):
    try:
        df = yf.download(ticker, period="1mo", interval="5m", progress=False, auto_adjust=True)
        if df.empty: return None
        df.index = df.index.tz_convert('Asia/Tokyo')
        pnls = []
        for d in np.unique(df.index.date)[-days_back:]:
            day = df[df.index.date == d].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            in_pos = False
            for ts, row in day.iterrows():
                if not in_pos and entry_start <= ts.time() <= entry_end:
                    if not use_vwap or (row['Close'] > row['VWAP']):
                        entry_p = row['Close'] * 1.0003; in_pos = True
                elif in_pos:
                    if row['Low'] <= entry_p * 0.992 or ts.time() >= time(14, 55):
                        exit_p = row['Close'] * 0.9997
                        pnls.append((exit_p - entry_p) / entry_p); in_pos = False; break
        return np.mean(pnls) if pnls else None
    except: return None

# --- 5. サイドバー ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    if st.sidebar.button(l + (" [ 選択中 ]" if st.session_state['preset']==p else ""), type="primary" if st.session_state['preset']==p else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back_bt = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
start_entry_bt = st.sidebar.time_input("開始時間", time(9, 0))
end_entry_bt = st.sidebar.time_input("終了時間", time(9, 15))
st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.subheader("📉 エントリー条件")
use_vwap_bt = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
use_ema_bt = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
use_rsi_bt = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
use_macd_bt = st.sidebar.checkbox("**MACD** が上向き", value=True)
st.sidebar.divider()
gap_min_bt = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05)/100
gap_max_bt = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05)/100
st.sidebar.subheader("💰 決済ルール")
ts_val_bt = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05)/100
tp_val_bt = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05)/100
sl_val_bt = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05)/100

# --- 6. メインレイアウト ---
st.markdown(f"<div class='title-container'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.65</h3></div>", unsafe_allow_html=True)
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

# --- タブ1: ワンタッチ (復旧版) ---
with tab_top:
    if st.button("🔄 指標更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info(); cards = '<div class="metric-grid">'
        for n, i in m_data.items():
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"; cls = "plus" if i['pct'] >= 0 else "minus"
                cards += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards + '</div>', unsafe_allow_html=True)
        vix = m_data.get("VIX指数", {}).get("val", 0)
        st.markdown(f'<div class="ai-box"><div style="color:#60a5fa; font-weight:bold;">🤖 AI予測</div><div style="color:#d1d5db; font-size:13px;">VIX指数は {vix:.1f} です。地合いに合わせた戦略を選択してください。</div></div>', unsafe_allow_html=True)
    st.divider()
    with st.expander("🔍 スキャン条件設定", expanded=False):
        s_days = st.slider("分析期間", 5, 30, 20); s_start = st.time_input("開始", time(9, 0), key="s1"); s_end = st.time_input("終了", time(9, 30), key="s2"); s_vwap = st.checkbox("VWAP必須", value=True)
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        res_list = []; prg = st.progress(0); tks = list(TICKER_NAME_MAP.keys())
        for idx, t in enumerate(tks):
            prg.progress((idx + 1) / len(tks))
            ev = run_scan_engine(t, s_days, s_start, s_end, s_vwap)
            if ev and ev > 0: res_list.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
        if res_list:
            top5 = sorted(res_list, key=lambda x: x['ev'], reverse=True)[:5]
            st.session_state['target_tickers'] = ", ".join([d['code'] for d in top5])
            st.success("🎯 期待値Top5を選出しました。")
            st.table(pd.DataFrame(top5).rename(columns={'code':'コード','name':'銘柄名','ev':'期待値'}))
            st.rerun()

# --- タブ3: バックテスト (完全復旧) ---
with tab_bt:
    t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        trades = []; progress = st.progress(0)
        for i, ticker in enumerate(t_list):
            progress.progress((i + 1) / len(t_list))
            try:
                df = yf.download(ticker, period="1mo", interval="5m", progress=False, auto_adjust=True)
                prev_m, open_m = fetch_daily_stats_maps(ticker)
                if df.empty: continue
                df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
                df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
                df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi(); df['RSI_P'] = df['RSI'].shift(1)
                macd_o = MACD(close=df['Close']); df['MH'] = macd_o.macd_diff(); df['MHP'] = df['MH'].shift(1)
                for date in np.unique(df.index.date)[-days_back_bt:]:
                    day = df[df.index.date == date].copy().between_time('09:00', '15:00')
                    if day.empty: continue
                    tp = (day['High'] + day['Low'] + day['Close']) / 3
                    day['VWAP'] = (tp * day['Volume']).cumsum() / day['Volume'].cumsum()
                    pc = prev_m.get(date.strftime('%Y-%m-%d')); do = open_m.get(date.strftime('%Y-%m-%d'))
                    if pc is None or do is None: continue
                    gap = (do - pc) / pc
                    in_pos = False; t_high = 0; t_active = False
                    for ts, row in day.iterrows():
                        if not in_pos:
                            if start_entry_bt <= ts.time() <= end_entry_bt and gap_min_bt <= gap <= gap_max_bt:
                                c_v = (row['Close'] > row['VWAP']) if use_vwap_bt else True
                                c_e = (row['Close'] > row['EMA5']) if use_ema_bt else True
                                c_r = (row['RSI'] > 45 and row['RSI'] > row['RSI_P']) if use_rsi_bt else True
                                c_m = (row['MH'] > row['MHP']) if use_macd_bt else True
                                if c_v and c_e and c_r and c_m:
                                    entry_p = row['Close'] * 1.0003; in_pos = True; stop_p = entry_p * (1 + sl_val_bt); t_high = row['High']
                        else:
                            t_high = max(t_high, row['High'])
                            if not t_active and t_high >= entry_p * (1 + ts_val_bt): t_active = True
                            ex_p = None
                            if t_active and row['Low'] <= t_high * (1 - tp_val_bt): ex_p = t_high * (1 - tp_val_bt) * 0.9997
                            elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997
                            elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997
                            if ex_p: trades.append({'Ticker': ticker, 'PnL': (ex_p - entry_p)/entry_p}); in_pos = False; break
            except: continue
        progress.empty()
        if trades:
            res = pd.DataFrame(trades); w = res[res['PnL']>0]['PnL']; l = res[res['PnL']<=0]['PnL']
            pf = w.sum()/abs(l.sum()) if not l.empty and l.sum()!=0 else 0
            st.markdown(f"<div class='summary-container'><div class='summary-box'><div class='summary-label'>総トレード数</div><div class='summary-value'>{len(res)}回</div></div><div class='summary-box'><div class='summary-label'>勝率</div><div class='summary-value'>{(res['PnL']>0).mean():.1%}</div></div><div class='summary-box'><div class='summary-label'>PF</div><div class='summary-value'>{pf:.2f}</div></div><div class='summary-box'><div class='summary-label'>期待値</div><div class='summary-value'>{res['PnL'].mean():.2%}</div></div></div>", unsafe_allow_html=True)
            st.caption("右上のコピーボタンで全文コピーできます↓")
            rpt = ["=================\n BACKTEST REPORT \n================="]
            for tk in t_list:
                tdf = res[res['Ticker'] == tk]; nm = TICKER_NAME_MAP.get(tk, tk)
                if tdf.empty: continue
                tw = tdf[tdf['PnL']>0]['PnL']; tl = tdf[tdf['PnL']<=0]['PnL']
                rpt.append(f">>> TICKER: {tk} | {nm}")
                rpt.append(f"トレード数: {len(tdf)} | 勝率: {(tdf['PnL']>0).mean():.1%} | 利益平均: {tw.mean() if not tw.empty else 0:+.2%} | 損失平均: {tl.mean() if not tl.empty else 0:+.2%} | PF: {tw.sum()/abs(tl.sum()) if not tl.empty and tl.sum()!=0 else 0:.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            st.code("\n".join(rpt), language="text")
        else: st.warning("条件に合うトレードなし。条件を外して再試行してください。")
