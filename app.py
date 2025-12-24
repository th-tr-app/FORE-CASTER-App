import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & デザイン ---
st.set_page_config(page_title="FORE CASTER", page_icon="📊", layout="wide")

# BACK TESTER v5.8 のCSSを継承 + 統合版用の調整
st.markdown("""
    <style>
    @media (max-width: 640px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 10px !important; }
        [data-testid="column"] { flex: 0 0 45% !important; max-width: 45% !important; min-width: 45% !important; }
        [data-testid="stMetricLabel"] { font-size: 12px !important; }
        [data-testid="stMetricValue"] { font-size: 18px !important; }
    }
    th, td { text-align: left !important; }
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 10px; }
    .metric-box { background-color: #262730; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #444; }
    .metric-label { font-size: 12px; color: #aaaaaa; }
    .metric-value { font-size: 24px; font-weight: bold; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 & マッピング ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "1802.T": "大林組", "1812.T": "鹿島建設", "3436.T": "SUMCO",
    "4403.T": "日油", "4506.T": "住友ファーマ", "4507.T": "塩野義製薬", "4568.T": "第一三共",
    "5020.T": "ENEOS", "6315.T": "TOWA", "6361.T": "荏原製作所", "6460.T": "セガサミーHLDGS",
    "6501.T": "日立", "6506.T": "安川電機", "6702.T": "富士通", "6723.T": "ルネサス",
    "6758.T": "ソニーG", "6762.T": "TDK", "6902.T": "デンソー", "6920.T": "レーザーテック",
    "6963.T": "ローム", "6981.T": "村田製作所", "7003.T": "三井E&S", "7011.T": "三菱重工",
    "7013.T": "IHI", "7203.T": "トヨタ", "7269.T": "スズキ", "7270.T": "SUBARU",
    "7453.T": "良品計画", "7751.T": "キャノン", "7752.T": "リコー", "8002.T": "丸紅",
    "8031.T": "三井物産", "8053.T": "住友商事", "8058.T": "三菱商事", "8267.T": "イオン",
    "8306.T": "三菱UFJ", "9433.T": "KDDI", "9502.T": "中部電力", "9843.T": "ニトリ",
    "9984.T": "ソフトバンクG", "1570.T": "日経レバ",
}

MARKET_INDICES = {
    "日経先物(CME)": "NIY=F", "NYダウ": "^DJI", "ナスダック": "^IXIC",
    "ドル/円": "JPY=X", "原油先物(WTI)": "CL=F", "Gold先物": "GC=F",
    "米10年金利": "^TNX", "VIX指数": "^VIX"
}

# --- 3. セッションステート初期化 ---
if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"

# --- 4. ロジック関数 (v5.8継承) ---

@st.cache_data(ttl=600)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change_pct = ((latest - prev) / prev) * 100
                data[name] = {"val": latest, "pct": change_pct}
            else: data[name] = {"val": None, "pct": None}
        except: data[name] = {"val": None, "pct": None}
    return data

def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row['RSI14'] >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

@st.cache_data(ttl=600)
def fetch_intraday(ticker, start, end):
    try:
        df = yf.download(ticker, start=start, end=datetime.now(), interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        d_start = start - timedelta(days=30)
        df = yf.download(ticker, start=d_start, end=datetime.now(), interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
        prev_close_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}
        curr_open_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        return prev_close_map, curr_open_map
    except: return {}, {}

@st.cache_data(ttl=86400)
def get_ticker_name(ticker):
    if ticker in TICKER_NAME_MAP: return TICKER_NAME_MAP[ticker]
    try:
        t = yf.Ticker(ticker)
        return t.info.get('longName', ticker)
    except: return ticker

# --- 5. サイドバー ---
st.sidebar.title("FORE CASTER 📊")
st.sidebar.subheader("🛡️ 戦略プリセット")
col_p1, col_p2, col_p3 = st.sidebar.columns(3)
if col_p1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_p2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_p3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.subheader("⚙️ 詳細パラメーター")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
start_entry_time = st.sidebar.time_input("開始時間", time(9, 0), step=300)
end_entry_time = st.sidebar.time_input("終了時間", time(9, 15), step=300)

use_vwap = st.sidebar.checkbox("VWAPより上でエントリー", value=True)
use_ema = st.sidebar.checkbox("EMA5より上でエントリー", value=True)
use_rsi = st.sidebar.checkbox("RSI 45以上or上向き", value=True)
use_macd = st.sidebar.checkbox("MACD 上向き", value=True)

trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5) / 100
trailing_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7) / 100

# --- 6. メインレイアウト ---
st.markdown("""
    <div style='margin-bottom: 10px;'>
        <h1 style='font-weight: 400; font-size: 42px; margin: 0;'>FORE CASTER</h1>
        <h3 style='font-weight: 300; font-size: 18px; margin: 0; color: #aaaaaa;'>Integrated Trading Manager | v1.0</h3>
    </div>
    """, unsafe_allow_html=True)

# 共通銘柄入力
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード (カンマ区切り)", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 トップ画面", "🔍 スクリーニング", "📈 バックテスト詳細分析"])

# --- タブ1: トップ画面 ---
with tab_top:
    with st.expander("🌍 リアルタイム市場情報 (タップで開閉)", expanded=True):
        m_info = fetch_market_info()
        m_cols = st.columns(4)
        for i, (name, info) in enumerate(m_info.items()):
            if info["val"] is not None:
                m_cols[i % 4].metric(name, f"{info['val']:,.1f}", f"{info['pct']:+.2f}%")
            else:
                m_cols[i % 4].metric(name, "取得不可", "---")
        
        vix_val = m_info.get("VIX指数", {}).get("val", 0)
        if vix_val and vix_val > 20:
            st.warning(f"⚠️ VIX指数が {vix_val:.1f} と高めです。ボラティリティ警戒が必要です。")
        else:
            st.info("💡 市場は比較的安定しています。順張りロジックが機能しやすい地合いです。")

    st.divider()
    st.subheader("🚀 One-Touch 期待値スキャン")
    if st.button("主要銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        st.write("※現在はデモ動作です。上位銘柄をロードします...")
        st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
        st.rerun()

# --- タブ2: スクリーニング (将来実装用) ---
with tab_screen:
    st.write("🔍 ここに詳細なスクリーニング条件の設定画面を実装予定です。")

# --- タブ3: バックテスト詳細 (v5.8 移植部分) ---
with tab_bt:
    tickers = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("詳細バックテスト実行"):
        start_date = datetime.now() - timedelta(days=days_back)
        all_trades = []
        p_bar = st.progress(0)
        
        for i, ticker in enumerate(tickers):
            p_bar.progress((i + 1) / len(tickers))
            t_name = get_ticker_name(ticker)
            df_intraday = fetch_intraday(ticker, start_date, datetime.now())
            prev_map, curr_map = fetch_daily_stats_maps(ticker, start_date)
            
            if df_intraday.empty: continue
            df_intraday = df_intraday[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df_intraday.index = df_intraday.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df_intraday.index.tzinfo is None else df_intraday.index.tz_convert('Asia/Tokyo')
            
            # 指標計算
            df_intraday['EMA5'] = EMAIndicator(close=df_intraday['Close'], window=5).ema_indicator()
            macd = MACD(close=df_intraday['Close'])
            df_intraday['MACD_H'] = macd.macd_diff()
            df_intraday['RSI14'] = RSIIndicator(close=df_intraday['Close'], window=14).rsi()
            
            unique_dates = np.unique(df_intraday.index.date)
            for date in unique_dates:
                day = df_intraday[df_intraday.index.date == date].copy().between_time('09:00', '15:00')
                if day.empty: continue
                # VWAP計算
                tp = (day['High'] + day['Low'] + day['Close']) / 3
                day['VWAP'] = (tp * day['Volume']).cumsum() / day['Volume'].cumsum()
                
                d_str = date.strftime('%Y-%m-%d')
                p_close = prev_map.get(d_str); d_open = curr_map.get(d_str)
                if p_close is None or d_open is None: continue
                gap = (d_open - p_close) / p_close
                
                # エントリーループ (簡略化)
                in_pos = False
                for ts, row in day.iterrows():
                    cur_t = ts.time()
                    if not in_pos and start_entry_time <= cur_t <= end_entry_time:
                        if (row['Close'] > row['VWAP'] if use_vwap else True) and (row['Close'] > row['EMA5'] if use_ema else True):
                            entry_p = row['Close'] * 1.0003
                            in_pos = True; entry_t = ts; trail_high = row['High']
                    elif in_pos:
                        if row['Low'] <= entry_p * (1 + stop_loss) or cur_t >= time(14, 55):
                            exit_p = row['Close'] * 0.9997
                            all_trades.append({'Ticker': ticker, 'PnL': (exit_p - entry_p)/entry_p, 'Pattern': get_trade_pattern(row, gap)})
                            in_pos = False; break
        p_bar.empty()
        
        if all_trades:
            res_df = pd.DataFrame(all_trades)
            st.success(f"分析完了: 全 {len(res_df)} トレード")
            # サマリー表示
            st.metric("平均勝率", f"{(res_df['PnL']>0).mean():.1%}")
            st.dataframe(res_df)
        else:
            st.warning("条件に合う取引がありませんでした。")
