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

    /* 指標カード (🏠タブ) */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { 
        background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; 
        padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; 
    }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; }
    .delta-badge { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }

    /* バックテストサマリー (📈タブ 5.8再現) */
    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { 
        background-color: #1e2129; border-radius: 6px; padding: 18px 5px; text-align: center; border: 1px solid #2d3139; 
    }
    .summary-label { font-size: 11px; color: #888888; margin-bottom: 5px; }
    .summary-value { font-size: 28px; font-weight: bold; color: #ffffff; }

    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. セッション管理 & 銘柄名マッピング ---
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8267.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"

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
    "9984.T": "ソフトバンクG", "1570.T": "日経レバ",
}

# --- 4. ロジック関数群 ---
@st.cache_data(ttl=300)
def fetch_market_info():
    indices = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI", "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"}
    data = {}
    for name, ticker in indices.items():
        try:
            df = yf.download(ticker, period="2d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=600)
def fetch_intraday(ticker, start):
    try: return yf.download(ticker, start=start, interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        df = yf.download(ticker, start=start-timedelta(days=30), interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# --- 5. サイドバー ---
st.sidebar.markdown("### 🎲 戦略プリセット")
if st.sidebar.button("通常フィルター" + (" [ 選択中 ]" if st.session_state['preset'] == "NORMAL" else ""), type="primary" if st.session_state['preset'] == "NORMAL" else "secondary"):
    st.session_state['preset'] = "NORMAL"; st.rerun()
if st.sidebar.button("ディフェンシブ" + (" [ 選択中 ]" if st.session_state['preset'] == "DEFENSIVE" else ""), type="primary" if st.session_state['preset'] == "DEFENSIVE" else "secondary"):
    st.session_state['preset'] = "DEFENSIVE"; st.rerun()
if st.sidebar.button("横ばい相場対応" + (" [ 選択中 ]" if st.session_state['preset'] == "RANGE" else ""), type="primary" if st.session_state['preset'] == "RANGE" else "secondary"):
    st.session_state['preset'] = "RANGE"; st.rerun()

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
gap_min = st.sidebar.slider("寄付ギャップダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
gap_max = st.sidebar.slider("寄付ギャップアップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100
st.sidebar.subheader("💰 決済ルール")
t_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05) / 100
t_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05) / 100
s_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05) / 100

# --- 6. メインレイアウト ---
st.markdown(f"""
    <div style='margin-bottom: 20px;'>
        <h1 class='main-title'>FORE CASTER</h1>
        <h3 class='sub-title'>SCREENING & BACKTEST | ver 1.63</h3>
    </div>
    """, unsafe_allow_html=True)

st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    if st.button("🔄 更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info()
        cards = '<div class="metric-grid">'
        for n, i in m_data.items():
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards + '</div>', unsafe_allow_html=True)

with tab_bt:
    tickers = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        s_date = datetime.now() - timedelta(days=days_back); trades = []
        progress = st.progress(0)
        for i, ticker in enumerate(tickers):
            progress.progress((i + 1) / len(tickers))
            df = fetch_intraday(ticker, s_date)
            prev_m, open_m = fetch_daily_stats_maps(ticker, s_date)
            if df.empty: continue
            df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
            df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
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
                            if (not use_vwap or row['Close'] > row['VWAP']) and (not use_ema or row['Close'] > row['EMA5']):
                                entry_p = row['Close'] * 1.0003; in_pos = True; entry_t = ts; stop_p = entry_p * (1 + s_loss); t_high = row['High']
                    else:
                        t_high = max(t_high, row['High'])
                        if not t_active and t_high >= entry_p * (1 + t_start): t_active = True
                        ex_p = None
                        if t_active and row['Low'] <= t_high * (1 - t_pct): ex_p = t_high * (1 - t_pct) * 0.9997
                        elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997
                        elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997
                        if ex_p:
                            trades.append({'Ticker': ticker, 'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p})
                            in_pos = False; break
        progress.empty()
        res = pd.DataFrame(trades)
        if not res.empty:
            bt1, bt2, bt3, bt4, bt5 = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "📝 詳細ログ"])
            with bt1:
                cnt = len(res); wr = (res['PnL']>0).mean(); ev = res['PnL'].mean()
                pf = (res[res['PnL']>0]['PnL'].sum() / abs(res[res['PnL']<=0]['PnL'].sum())) if abs(res[res['PnL']<=0]['PnL'].sum()) > 0 else 0
                st.markdown(f"""
                <div class="summary-container">
                    <div class="summary-box"><div class="summary-label">総トレード数</div><div class="summary-value">{cnt}回</div></div>
                    <div class="summary-box"><div class="summary-label">勝率</div><div class="summary-value">{wr:.1%}</div></div>
                    <div class="summary-box"><div class="summary-label">PF（総利益 ÷ 総損失）</div><div class="summary-value">{pf:.2f}</div></div>
                    <div class="summary-box"><div class="summary-label">期待値</div><div class="summary-value">{ev:.2%}</div></div>
                </div>
                """, unsafe_allow_html=True)
                
                # BACKTEST REPORT (銘柄名マッピング反映)
                report = ["=================\n BACKTEST REPORT \n================="]
                report.append(f"\nPeriod: {s_date.strftime('%Y-%m-%d')} - {datetime.now().strftime('%Y-%m-%d')}\n")
                for t in tickers:
                    tdf = res[res['Ticker'] == t]
                    if tdf.empty: continue
                    t_name = TICKER_NAME_MAP.get(t, t) # マッピングから取得、なければコード表示
                    wins = tdf[tdf['PnL'] > 0]; losses = tdf[tdf['PnL'] <= 0]
                    t_wr = (tdf['PnL']>0).mean(); t_ev = tdf['PnL'].mean()
                    t_pf = (wins['PnL'].sum() / abs(losses['PnL'].sum())) if not losses.empty and losses['PnL'].sum() != 0 else 0
                    report.append(f">>> TICKER: {t} | {t_name}") # 指定の形式で出力
                    report.append(f"トレード数: {len(tdf)} | 勝率: {t_wr:.1%} | 利益平均: {wins['PnL'].mean():+.2% if not wins.empty else 0} | 損失平均: {losses['PnL'].mean():+.2% if not losses.empty else 0} | PF: {t_pf:.2f} | 期待値: {t_ev:+.2%}\n")
                st.caption("右上のコピーボタンで全文コピーできます↓")
                st.code("\n".join(report), language="text")
