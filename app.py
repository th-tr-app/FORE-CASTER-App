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
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }
    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 18px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 11px; color: #888888; margin-bottom: 5px; }
    .summary-value { font-size: 28px; font-weight: bold; color: #ffffff; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 銘柄名マッピング ---
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

# --- 4. サイドバー設定 (全項目復元) ---
st.sidebar.markdown("### 🎲 戦略プリセット")
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    if st.sidebar.button(l + (" [ 選択中 ]" if st.session_state['preset']==p else ""), type="primary" if st.session_state['preset']==p else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
start_entry = st.sidebar.time_input("開始時間", time(9, 0))
end_entry = st.sidebar.time_input("終了時間", time(9, 15))
st.sidebar.markdown("<br>", unsafe_allow_html=True)

st.sidebar.subheader("📉 エントリー条件")
use_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
use_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
use_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
use_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)

st.sidebar.divider()
gap_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05)/100
gap_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05)/100

st.sidebar.subheader("💰 決済ルール")
t_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05)/100
t_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05)/100
s_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05)/100

# --- 5. ロジック関数 ---
def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

@st.cache_data(ttl=300)
def fetch_market_info():
    indices = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "VIX指数": "^VIX", "NYダウ30種": "^DJI", "SOX指数": "^SOX"}
    data = {}
    for name, ticker in indices.items():
        try:
            df = yf.download(ticker, period="2d", progress=False)
            if not df.empty:
                data[name] = {"val": float(df['Close'].iloc[-1]), "pct": ((float(df['Close'].iloc[-1]) - float(df['Close'].iloc[-2])) / float(df['Close'].iloc[-2])) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        df = yf.download(ticker, start=start-timedelta(days=30), interval="1d", progress=False)
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom:20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.63</h3></div>", unsafe_allow_html=True)
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8267.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    if st.button("🔄 更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info(); cards = '<div class="metric-grid">'
        for n, i in m_data.items():
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"; cls = "plus" if i['pct'] >= 0 else "minus"
                cards += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards + '</div>', unsafe_allow_html=True)

with tab_bt:
    tickers = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        s_date = datetime.now() - timedelta(days=days_back); trades = []
        progress = st.progress(0)
        for i, ticker in enumerate(tickers):
            progress.progress((i + 1) / len(tickers))
            try:
                df = yf.download(ticker, start=s_date, interval="5m", progress=False)
                prev_m, open_m = fetch_daily_stats_maps(ticker, s_date)
                if df.empty: continue
                df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
                df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
                df['RSI14'] = RSIIndicator(close=df['Close'], window=14).rsi(); df['RSI_P'] = df['RSI14'].shift(1)
                macd = MACD(close=df['Close']); df['MH'] = macd.macd_diff(); df['MHP'] = df['MH'].shift(1)
                for date in np.unique(df.index.date):
                    day = df[df.index.date == date].copy().between_time('09:00', '15:00')
                    if day.empty: continue
                    day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
                    pc = prev_m.get(date.strftime('%Y-%m-%d')); do = open_m.get(date.strftime('%Y-%m-%d'))
                    if pc is None or do is None: continue
                    gap = (do - pc) / pc
                    in_pos = False; t_high = 0; t_active = False
                    for ts, row in day.iterrows():
                        if not in_pos:
                            if start_entry <= ts.time() <= end_entry and gap_min <= gap <= gap_max:
                                c_vwap = (row['Close'] > row['VWAP']) if use_vwap else True
                                c_ema = (row['Close'] > row['EMA5']) if use_ema else True
                                c_rsi = (row['RSI14'] > 45 and row['RSI14'] > row['RSI_P']) if use_rsi else True
                                c_macd = (row['MH'] > row['MHP']) if use_macd else True
                                if c_vwap and c_ema and c_rsi and c_macd:
                                    entry_p = row['Close'] * 1.0003; in_pos = True; stop_p = entry_p * (1 + s_loss); t_high = row['High']; pat = get_trade_pattern(row, gap)
                        else:
                            t_high = max(t_high, row['High'])
                            if not t_active and t_high >= entry_p * (1 + t_start): t_active = True
                            ex_p = None
                            if t_active and row['Low'] <= t_high * (1 - t_pct): ex_p = t_high * (1 - t_pct) * 0.9997
                            elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997
                            elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997
                            if ex_p:
                                trades.append({'Ticker': ticker, 'PnL': (ex_p - entry_p)/entry_p, 'Pattern': pat})
                                in_pos = False; break
            except: continue
        progress.empty(); res = pd.DataFrame(trades)
        if not res.empty:
            bt1, bt2, bt3 = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📝 詳細ログ"])
            with bt1:
                wins = res[res['PnL']>0]['PnL']; losses = res[res['PnL']<=0]['PnL']
                pf = wins.sum()/abs(losses.sum()) if not losses.empty and losses.sum() != 0 else 0
                st.markdown(f'<div class="summary-container"><div class="summary-box"><div class="summary-label">総トレード数</div><div class="summary-value">{len(res)}回</div></div><div class="summary-box"><div class="summary-label">勝率</div><div class="summary-value">{(res["PnL"]>0).mean():.1%}</div></div><div class="summary-box"><div class="summary-label">PF</div><div class="summary-value">{pf:.2f}</div></div><div class="summary-box"><div class="summary-label">期待値</div><div class="summary-value">{res["PnL"].mean():.2%}</div></div></div>', unsafe_allow_html=True)
                report = ["=================\n BACKTEST REPORT \n================="]
                for t in tickers:
                    tdf = res[res['Ticker'] == t]; t_name = TICKER_NAME_MAP.get(t, t)
                    if tdf.empty: continue
                    tw = tdf[tdf['PnL']>0]['PnL']; tl = tdf[tdf['PnL']<=0]['PnL']
                    tpf = tw.sum()/abs(tl.sum()) if not tl.empty and tl.sum() != 0 else 0
                    report.append(f">>> TICKER: {t} | {t_name}")
                    report.append(f"トレード数: {len(tdf)} | 勝率: {(tdf['PnL']>0).mean():.1%} | 利益平均: {tw.mean() if not tw.empty else 0:+.2%} | 損失平均: {tl.mean() if not tl.empty else 0:+.2%} | PF: {tpf:.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
                st.code("\n".join(report), language="text")
            with bt2:
                st.dataframe(res.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).style.format({'<lambda_0>': '{:.1%}', 'mean': '{:+.2%}'}), use_container_width=True)
            with bt3: st.dataframe(res, use_container_width=True)
