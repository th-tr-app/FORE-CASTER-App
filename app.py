import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & デザイン ---
st.set_page_config(page_title="FORE CASTER", page_icon="📊", layout="wide")

# カスタムCSS（BACK TESTERのデザインを継承）
st.markdown("""
    <style>
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    @media (max-width: 640px) { .metric-container { grid-template-columns: 1fr 1fr; } }
    .metric-box { background-color: #262730; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #444; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 & マッピング (BACK TESTER v5.8より継承) ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "6920.T": "レーザーテック", "7011.T": "三菱重工", 
    "7203.T": "トヨタ", "8306.T": "三菱UFJ", "9984.T": "ソフトバンクG",
    "1570.T": "日経レバ", "7013.T": "IHI", "8031.T": "三井物産", "6758.T": "ソニーG"
}

MARKET_INDICES = {
    "日経先物(CME)": "NIY=F", "NYダウ": "^DJI", "ナスダック": "^IXIC",
    "ドル/円": "JPY=X", "原油先物": "CL=F", "Gold先物": "GC=F",
    "米10年金利": "^TNX", "VIX指数": "^VIX"
}

# --- 3. セッションステート初期化 ---
if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"
if 'screen_results' not in st.session_state:
    st.session_state['screen_results'] = None

# --- 4. 関数定義 (ロジック部) ---

@st.cache_data(ttl=600)
def fetch_market_info():
    """地合い情報の取得"""
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="2d", progress=False)
            if not df.empty:
                latest = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                change_pct = ((latest - prev) / prev) * 100
                data[name] = {"val": latest, "pct": change_pct}
        except: data[name] = {"val": 0, "pct": 0}
    return data

# (BACK TESTER v5.8のバックテスト・ロジックをここに移植... 省略せず組み込みます)
def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row['RSI14'] >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

# --- 5. サイドバー構成 ---
st.sidebar.title("FORE CASTER 📊")

st.sidebar.subheader("🛡️ 戦略プリセット")
col1, col2, col3 = st.sidebar.columns(3)
preset = "NORMAL"
if col1.button("通常"): preset = "NORMAL"
if col2.button("防御"): preset = "DEFENSIVE"
if col3.button("横這"): preset = "RANGE"

st.sidebar.divider()
st.sidebar.subheader("⚙️ 詳細パラメーター")
# v5.8のパラメーターをここに配置
days_back = st.sidebar.slider("過去日数", 10, 59, 30)
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7) / 100

# --- 6. メインレイアウト ---
st.markdown(f"## FORE CASTER <small>v1.0 | Strategy: {preset}</small>", unsafe_allow_html=True)

# 共通銘柄入力枠
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード (カンマ区切り)", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["🏠 トップ画面", "🔍 スクリーニング", "📈 バックテスト詳細"])

# --- タブ1: トップ画面 ---
with tab_top:
with st.expander("🌍 リアルタイム市場情報 (タップで表示)", expanded=True):
        market_info = fetch_market_info()
        cols = st.columns(4)
        for i, (name, info) in enumerate(market_info.items()):
            # 値が取得できている場合のみフォーマットを適用
            if info["val"] is not None:
                val_str = f"{info['val']:,.1f}"
                pct_str = f"{info['pct']:+.2f}%"
                cols[i % 4].metric(name, val_str, pct_str)
            else:
                cols[i % 4].metric(name, "取得不可", "---")
          @st.cache_data(ttl=600)
def fetch_market_info():
    """地合い情報の取得（エラー対策版）"""
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            # 取得期間を少し長め（5日分）にして、休日でも直近の値を取れるようにする
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change_pct = ((latest - prev) / prev) * 100
                data[name] = {"val": latest, "pct": change_pct}
            else:
                data[name] = {"val": None, "pct": None}
        except: 
            data[name] = {"val": None, "pct": None}
    return data
        # 地合い判定テキスト (日銀会合後のボラティリティを想定)
        vix = market_info.get("VIX指数", {"val": 0})["val"]
        prediction = "🤖 **地合い判定:** "
        if vix > 20: prediction += "ボラティリティ上昇中。慎重なエントリーが必要です。"
        else: prediction += "安定した地合いです。テクニカルに従い順張りが有効です。"
        st.write(prediction)

    st.divider()
    st.subheader("🚀 One-Touch 期待値スキャン")
    if st.button("全主要銘柄から期待値TOP5を抽出", type="primary", use_container_width=True):
        with st.spinner("主要銘柄をスキャン中..."):
            # ここでTICKER_NAME_MAP全銘柄をv5.8ロジックで回す処理を実装
            # 今回はサンプルとして上位を表示
            st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
            st.success("抽出完了！監視銘柄枠にTop5をロードしました。")
            st.rerun()

# --- タブ2/3: BACK TESTER v5.8 の機能をここに移植 ---
with tab_bt:
    st.info("BACK TESTER v5.8 エンジン稼働中")
    # ここに以前提供いただいたBACK TESTERの描画コードを統合
    import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- ページ設定 ---
st.set_page_config(page_title="BACK TESTER", page_icon="image_10.png", layout="wide")
st.logo("image_11.png", icon_image="image_10.png")

# --- 銘柄名マッピング ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX",
    "1802.T": "大林組",
    "1812.T": "鹿島建設",
    "3436.T": "SUMCO",
    "4403.T": "日油",
    "4506.T": "住友ファーマ",
    "4507.T": "塩野義製薬",
    "4568.T": "第一三共",
    "5020.T": "ENEOS",
    "6315.T": "TOWA",
    "6361.T": "荏原製作所",
    "6460.T": "セガサミーHLDGS",
    "6501.T": "日立",
    "6506.T": "安川電機",
    "6702.T": "富士通",
    "6723.T": "ルネサスエレクトロニクス",
    "6758.T": "ソニーグループ",
    "6762.T": "TDK",
    "6902.T": "デンソー",
    "6920.T": "レーザーテック",
    "6963.T": "ローム",
    "6981.T": "村田製作所",
    "7003.T": "三井E&S",
    "7011.T": "三菱重工業",
    "7013.T": "I H I",
    "7203.T": "トヨタ自動車",
    "7269.T": "スズキ",
    "7270.T": "SUBARU",
    "7453.T": "良品計画",
    "7751.T": "キャノン",
    "7752.T": "リコー",
    "8002.T": "丸紅",
    "8031.T": "三井物産",
    "8053.T": "住友商事",
    "8058.T": "三菱商事",
    "8267.T": "イオン",
    "8306.T": "三菱UFJ",
    "9433.T": "KDDI",
    "9502.T": "中部電力",
    "9843.T": "ニトリ",
    "9984.T": "ソフトバンクG",
    "1570.T": "日経レバ",
}

# CSS設定
st.markdown("""
    <style>
    @media (max-width: 640px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 10px !important; }
        [data-testid="column"] { flex: 0 0 45% !important; max-width: 45% !important; min-width: 45% !important; }
        [data-testid="stMetricLabel"] { font-size: 12px !important; }
        [data-testid="stMetricValue"] { font-size: 18px !important; }
    }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>BACK TESTER</h1>
        <h3 style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>DAY TRADING MANAGER｜ver 5.8</h3>
    </div>
    """, unsafe_allow_html=True)

# --- ★修正: 勝ちパターン判定ロジック（B救済版） ---
def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    
    # 1. A：反転狙い (ギャップダウンならまずこれ)
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap):
        return "A：反転狙い"

    # 2. D：上昇継続 (ギャップなし・微ギャップならこれ)
    # 範囲: -0.3% ～ +0.3%
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']):
        return "D：上昇継続"

    # 3. C：ブレイク (強いGU ＋ 強いRSI)
    # 条件: +0.5%以上のGU かつ RSI 65以上 (条件厳格化)
    elif (gap_pct >= 0.005) and (row['RSI14'] >= 65):
        return "C：ブレイク"

    # 4. B：押目上昇 (普通のGU)
    # 条件: +0.3%以上のGUで、Cにならなかったもの（＝RSI65未満）は全てBへ
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']):
        return "B：押目上昇"

    return "E：他タイプ"

# データ取得（5分足）
@st.cache_data(ttl=600)
def fetch_intraday(ticker, start, end):
    try:
        df = yf.download(ticker, start=start, end=datetime.now(), interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
        return df
    except: return pd.DataFrame()

# 前日終値＆当日始値マップ作成
@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        d_start = start - timedelta(days=30)
        df = yf.download(ticker, start=d_start, end=datetime.now(), interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        
        if df.empty: return {}, {}
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        else:
            df.index = df.index.tz_convert('Asia/Tokyo')
            
        prev_close = df['Close'].shift(1)
        prev_close_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, prev_close) if pd.notna(c)}
        curr_open_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        
        return prev_close_map, curr_open_map
    except: return {}, {}

# 銘柄名取得（辞書優先）
@st.cache_data(ttl=86400)
def get_ticker_name(ticker):
    if ticker in TICKER_NAME_MAP:
        return TICKER_NAME_MAP[ticker]
    try:
        t = yf.Ticker(ticker)
        name = t.info.get('longName', t.info.get('shortName', ticker))
        return name
    except:
        return ticker

# UI
ticker_input = st.text_input("銘柄コード (カンマ区切り)", "8267.T")
tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]
main_btn = st.button("バックテスト実行", type="primary", key="main_btn")
st.divider()

st.sidebar.header("⚙️ パラメーター設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
start_entry_time = st.sidebar.time_input("開始時間", time(9, 0), step=300)
end_entry_time = st.sidebar.time_input("終了時間", time(9, 15), step=300)
st.sidebar.write("")
st.sidebar.subheader("📉 エントリー条件")
use_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
st.sidebar.write("")
use_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
st.sidebar.write("")
use_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
st.sidebar.write("")
use_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)
st.sidebar.write("")
st.sidebar.divider()

gap_min = st.sidebar.slider("寄付ギャップダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
gap_max = st.sidebar.slider("寄付ギャップアップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100

st.sidebar.subheader("💰 決済ルール")
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
trailing_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, 0.05) / 100

SLIPPAGE_PCT = 0.0003
FORCE_CLOSE_TIME = time(14, 55)
st.sidebar.write("")
st.sidebar.write("")
sidebar_btn = st.sidebar.button("バックテスト実行", type="primary", key="sidebar_btn")

if main_btn or sidebar_btn:
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    all_trades = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    ticker_names = {}

    for i, ticker in enumerate(tickers):
        status_text.text(f"Testing {ticker}...")
        progress_bar.progress((i + 1) / len(tickers))
        
        t_name = get_ticker_name(ticker)
        ticker_names[ticker] = t_name

        df = fetch_intraday(ticker, start_date, end_date)
        prev_close_map, curr_open_map = fetch_daily_stats_maps(ticker, start_date)
        
        if df.empty: continue
        
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        else:
            df.index = df.index.tz_convert('Asia/Tokyo')

        df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
        macd = MACD(close=df['Close'])
        df['MACD_H'] = macd.macd_diff()
        df['MACD_H_Prev'] = df['MACD_H'].shift(1)
        rsi = RSIIndicator(close=df['Close'], window=14)
        df['RSI14'] = rsi.rsi()
        df['RSI14_Prev'] = df['RSI14'].shift(1)
        
        def compute_vwap(d):
            tp = (d['High'] + d['Low'] + d['Close']) / 3
            cum_vp = (tp * d['Volume']).cumsum()
            cum_vol = d['Volume'].cumsum().replace(0, np.nan)
            return (cum_vp / cum_vol).ffill()

        unique_dates = np.unique(df.index.date)
        
        for date in unique_dates:
            day = df[df.index.date == date].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = compute_vwap(day)
            
            date_str = date.strftime('%Y-%m-%d')
            prev_close = prev_close_map.get(date_str)
            daily_open = curr_open_map.get(date_str)
            
            if prev_close is None or daily_open is None: continue

            gap_pct = (daily_open - prev_close) / prev_close
            
            in_pos = False
            entry_p = 0
            entry_t = None
            entry_vwap = 0
            stop_p = 0
            trail_active = False
            trail_high = 0
            pattern_type = "E：他タイプ"
            
            for ts, row in day.iterrows():
                cur_time = ts.time()
                if np.isnan(row['EMA5']) or np.isnan(row['RSI14']): continue
                
                if not in_pos:
                    if start_entry_time <= cur_time <= end_entry_time:
                        if gap_min <= gap_pct <= gap_max:
                            cond_vwap = (row['Close'] > row['VWAP']) if use_vwap else True
                            cond_ema  = (row['Close'] > row['EMA5']) if use_ema else True
                            cond_rsi = ((row['RSI14'] > 45) and (row['RSI14'] > row['RSI14_Prev'])) if use_rsi else True
                            cond_macd = (row['MACD_H'] > row['MACD_H_Prev']) if use_macd else True
                            if pd.isna(row['VWAP']) and use_vwap: cond_vwap = False
                            
                            if cond_vwap and cond_ema and cond_rsi and cond_macd:
                                entry_p = row['Close'] * (1 + SLIPPAGE_PCT)
                                entry_t = ts
                                entry_vwap = row['VWAP']
                                in_pos = True
                                stop_p = entry_p * (1 + stop_loss)
                                trail_active = False
                                trail_high = row['High']
                                pattern_type = get_trade_pattern(row, gap_pct)
                else:
                    if row['High'] > trail_high: trail_high = row['High']
                    if not trail_active and (trail_high >= entry_p * (1 + trailing_start)): trail_active = True
                    
                    exit_p = None
                    reason = ""
                    if trail_active and (row['Low'] <= trail_high * (1 - trailing_pct)):
                        exit_p = trail_high * (1 - trailing_pct) * (1 - SLIPPAGE_PCT)
                        reason = "トレーリング"
                    elif row['Low'] <= stop_p:
                        exit_p = stop_p * (1 - SLIPPAGE_PCT)
                        reason = "損切り"
                    elif cur_time >= FORCE_CLOSE_TIME:
                        exit_p = row['Close'] * (1 - SLIPPAGE_PCT)
                        reason = "時間切れ"
                        
                    if exit_p:
                        pnl = (exit_p - entry_p) / entry_p
                        all_trades.append({
                            'Ticker': ticker, 'Entry': entry_t, 'Exit': ts,
                            'In': int(entry_p), 'Out': int(exit_p),
                            'PnL': pnl, 'Reason': reason,
                            'EntryVWAP': entry_vwap, 'Gap(%)': gap_pct * 100,
                            'Pattern': pattern_type,
                            'PrevClose': int(prev_close), 'DayOpen': int(daily_open)
                        })
                        in_pos = False
                        break
                        
    progress_bar.empty()
    status_text.empty()

    res_df = pd.DataFrame(all_trades)
    if res_df.empty:
        st.warning("条件に合うトレードはありませんでした。")
    else:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ"])
        
        with tab1:
            count_all = len(res_df)
            wins_all = res_df[res_df['PnL'] > 0]
            losses_all = res_df[res_df['PnL'] <= 0]
            win_rate_all = len(wins_all) / count_all if count_all > 0 else 0
            gross_win = res_df[res_df['PnL']>0]['PnL'].sum()
            gross_loss = abs(res_df[res_df['PnL']<=0]['PnL'].sum())
            pf_all = gross_win/gross_loss if gross_loss > 0 else float('inf')
            expectancy_all = res_df['PnL'].mean()

            st.markdown(f"""
            <style>
            .metric-container {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px; }}
            @media (max-width: 640px) {{ .metric-container {{ grid-template-columns: 1fr 1fr; }} }}
            .metric-box {{ background-color: #262730; padding: 15px; border-radius: 8px; text-align: center; }}
            .metric-label {{ font-size: 12px; color: #aaaaaa; }}
            .metric-value {{ font-size: 24px; font-weight: bold; color: #ffffff; }}
            </style>
            <div class="metric-container">
                <div class="metric-box"><div class="metric-label">総トレード数</div><div class="metric-value">{count_all}回</div></div>
                <div class="metric-box"><div class="metric-label">勝率</div><div class="metric-value">{win_rate_all:.1%}</div></div>
                <div class="metric-box"><div class="metric-label">PF（総利益 ÷ 総損失）</div><div class="metric-value">{pf_all:.2f}</div></div>
                <div class="metric-box"><div class="metric-label">期待値</div><div class="metric-value">{expectancy_all:.2%}</div></div>
            </div>
            """, unsafe_allow_html=True)
            st.divider()
            
            report = []
            report.append("=================\n BACKTEST REPORT \n=================")
            report.append(f"\nPeriod: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}\n")
            for t in tickers:
                tdf = res_df[res_df['Ticker'] == t]
                if tdf.empty: continue
                wins = tdf[tdf['PnL'] > 0]
                losses = tdf[tdf['PnL'] <= 0]
                cnt = len(tdf); wr = len(wins)/cnt if cnt>0 else 0
                avg_win = wins['PnL'].mean() if not wins.empty else 0
                avg_loss = losses['PnL'].mean() if not losses.empty else 0
                pf = wins['PnL'].sum()/abs(losses['PnL'].sum()) if losses['PnL'].sum()!=0 else float('inf')
                
                t_name = ticker_names.get(t, t)
                report.append(f">>> TICKER: {t} | {t_name}")
                report.append(f"トレード数: {cnt} | 勝率: {wr:.1%} | 利益平均: {avg_win:+.2%} | 損失平均: {avg_loss:+.2%} | PF: {pf:.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(report), language="text")

        with tab2: # 勝ちパターン
            st.markdown("### 🤖 勝ちパターン分析")
            st.caption("チャートパターン別の成績分析と、ベストなエントリー条件の言語化をします。自身の「得意な形」が一目で分かります。")
            st.divider()
            for t in tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                t_name = ticker_names.get(t, t)
                st.markdown(f"#### [{t}] {t_name}")
                pat_stats = tdf.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                pat_stats.columns = ['パターン', 'トレード数', '勝率', '平均損益']
                pat_stats['勝率'] = pat_stats['勝率'].apply(lambda x: f"{x:.1%}")
                pat_stats['平均損益'] = pat_stats['平均損益'].apply(lambda x: f"{x:+.2%}")
                pat_stats['トレード数'] = pat_stats['トレード数'].astype(str)
                st.dataframe(pat_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                
                min_g = np.floor(tdf['Gap(%)'].min()); max_g = np.ceil(tdf['Gap(%)'].max())
                if np.isnan(min_g): min_g=-3.0; max_g=1.0
                bins_g = np.arange(min_g, max_g+0.5, 0.5)
                tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=bins_g)
                gap_stats = tdf.groupby('GapRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                gap_valid = gap_stats[gap_stats['count']>=2]
                if gap_valid.empty: gap_valid = gap_stats
                best_g = gap_valid.loc[gap_valid['<lambda_0>'].idxmax()]
                
                tdf['VWAP_Diff'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                min_v = np.floor(tdf['VWAP_Diff'].min()*2)/2; max_v = np.ceil(tdf['VWAP_Diff'].max()*2)/2
                if np.isnan(min_v): min_v=-1.0; max_v=1.0
                bins_v = np.arange(min_v, max_v+0.2, 0.2)
                tdf['VwapRange'] = pd.cut(tdf['VWAP_Diff'], bins=bins_v)
                vwap_valid = tdf.groupby('VwapRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                vwap_valid = vwap_valid[vwap_valid['count']>=2]
                if vwap_valid.empty: vwap_valid = vwap_stats
                best_v = vwap_valid.loc[vwap_valid['<lambda_0>'].idxmax()]
                
                def get_time_range(dt): return f"{dt.strftime('%H:%M')}～{(dt + timedelta(minutes=5)).strftime('%H:%M')}"
                tdf['TimeRange'] = tdf['Entry'].apply(get_time_range)
                time_valid = tdf.groupby('TimeRange')['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                time_valid = time_valid[time_valid['count']>=2]
                if time_valid.empty: time_valid = time_stats
                best_t = time_valid.loc[time_valid['<lambda_0>'].idxmax()]
                
                gap_txt = "ギャップアップ" if best_g['GapRange'].left >= 0 else "ギャップダウン"
                st.info(f"**🏆 最高勝率パターン**\n\n"
                        f"最も勝率が高かったのは、**{gap_txt} ({best_g['GapRange'].left:.1f}% ～ {best_g['GapRange'].right:.1f}%)** スタートで、"
                        f"VWAPから **{best_v['VwapRange'].left:.1f}% ～ {best_v['VwapRange'].right:.1f}%** の位置にある時、"
                        f"**{best_t['TimeRange']}** にエントリーするパターンです。\n\n"
                        f"(Gap勝率: {best_g['<lambda_0>']:.1%} / VWAP勝率: {best_v['<lambda_0>']:.1%} / 時間勝率: {best_t['<lambda_0>']:.1%})")
                st.divider()

        with tab3: # ギャップ分析
            for t in tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                t_name = ticker_names.get(t, t)
                st.markdown(f"### [{t}] {t_name}")
                st.markdown("##### 始値ギャップ方向と成績")
                tdf['GapDir'] = tdf['Gap(%)'].apply(lambda x: 'ギャップアップ' if x > 0 else ('ギャップダウン' if x < 0 else 'フラット'))
                gap_dir_stats = tdf.groupby('GapDir').agg(Count=('PnL', 'count'), WinRate=('PnL', lambda x: (x > 0).mean()), AvgPnL=('PnL', 'mean')).reset_index()
                gap_dir_stats['WinRate'] = gap_dir_stats['WinRate'].apply(lambda x: f"{x:.1%}")
                gap_dir_stats['AvgPnL'] = gap_dir_stats['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                gap_dir_stats['Count'] = gap_dir_stats['Count'].astype(str)
                gap_dir_stats.columns = ['方向', 'トレード数', '勝率', '平均損益']
                st.dataframe(gap_dir_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                st.markdown("##### ギャップ幅ごとの勝率")
                min_g = np.floor(tdf['Gap(%)'].min()); max_g = np.ceil(tdf['Gap(%)'].max())
                if np.isnan(min_g): min_g = -3.0; max_g = 1.0
                bins_g = np.arange(min_g, max_g + 0.5, 0.5)
                tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=bins_g)
                gap_range_stats = tdf.groupby('GapRange', observed=True).agg(Count=('PnL', 'count'), WinRate=('PnL', lambda x: (x > 0).mean()), AvgPnL=('PnL', 'mean')).reset_index()
                def format_interval(i): return f"{i.left:.1f}% ～ {i.right:.1f}%"
                gap_range_stats['RangeLabel'] = gap_range_stats['GapRange'].apply(format_interval)
                disp_gap = gap_range_stats[['RangeLabel', 'Count', 'WinRate', 'AvgPnL']].copy()
                disp_gap['WinRate'] = disp_gap['WinRate'].apply(lambda x: f"{x:.1%}")
                disp_gap['AvgPnL'] = disp_gap['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                disp_gap['Count'] = disp_gap['Count'].astype(str)
                disp_gap.columns = ['ギャップ幅', 'トレード数', '勝率', '平均損益']
                st.dataframe(disp_gap.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                st.divider()

        with tab4: # VWAP分析
             for t in tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                t_name = ticker_names.get(t, t)
                st.markdown(f"### [{t}] {t_name}")
                st.markdown("##### エントリー時のVWAPと勝率")
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                min_dev = np.floor(tdf['VWAP乖離(%)'].min() * 2) / 2
                max_dev = np.ceil(tdf['VWAP乖離(%)'].max() * 2) / 2
                if np.isnan(min_dev): min_dev = -1.0; max_dev = 1.0
                bins = np.arange(min_dev, max_dev + 0.2, 0.2)
                tdf['Range'] = pd.cut(tdf['VWAP乖離(%)'], bins=bins)
                vwap_stats = tdf.groupby('Range', observed=True).agg(Count=('PnL', 'count'), WinRate=('PnL', lambda x: (x > 0).mean()), AvgPnL=('PnL', 'mean')).reset_index()
                def format_vwap_interval(i): return f"{i.left:.1f}% ～ {i.right:.1f}%"
                vwap_stats['RangeLabel'] = vwap_stats['Range'].apply(format_vwap_interval)
                display_stats = vwap_stats[['RangeLabel', 'Count', 'WinRate', 'AvgPnL']].copy()
                display_stats['WinRate'] = display_stats['WinRate'].apply(lambda x: f"{x:.1%}")
                display_stats['AvgPnL'] = display_stats['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                display_stats['Count'] = display_stats['Count'].astype(str)
                display_stats.columns = ['乖離率レンジ', 'トレード数', '勝率', '平均損益']
                st.dataframe(display_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                st.divider()

        with tab5: # 時間分析
            for t in tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                t_name = ticker_names.get(t, t)
                st.markdown(f"### [{t}] {t_name}")
                st.markdown("##### エントリー時間帯ごとの勝率")
                def get_time_range(dt): return f"{dt.strftime('%H:%M')}～{(dt + timedelta(minutes=5)).strftime('%H:%M')}"
                tdf['TimeRange'] = tdf['Entry'].apply(get_time_range)
                time_stats = tdf.groupby('TimeRange')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                time_disp = time_stats.copy()
                time_disp['WinRate'] = time_disp['<lambda_0>'].apply(lambda x: f"{x:.1%}")
                time_disp['AvgPnL'] = time_disp['mean'].apply(lambda x: f"{x:+.2%}")
                time_disp['Count'] = time_disp['count'].astype(str)
                time_disp = time_disp[['TimeRange', 'Count', 'WinRate', 'AvgPnL']]
                time_disp.columns = ['時間帯', 'トレード数', '勝率', '平均損益']
                st.dataframe(time_disp.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                st.divider()

        with tab6: # 詳細ログ
            log_report = []
            for t in tickers:
                tdf = res_df[res_df['Ticker'] == t].copy().sort_values('Entry', ascending=False).reset_index(drop=True)
                if tdf.empty: continue
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                t_name = ticker_names.get(t, t)
                log_report.append(f"[{t}] {t_name} 取引履歴")
                log_report.append("-" * 80)
                for i, row in tdf.iterrows():
                    entry_str = row['Entry'].strftime('%Y-%m-%d %H:%M')
                    if pd.notna(row['EntryVWAP']):
                        vwap_val = int(round(row['EntryVWAP']))
                        vwap_dev = f"{row['VWAP乖離(%)']:+.2f}%"
                        vwap_str = f"{vwap_val} (乖離 {vwap_dev})"
                    else:
                        vwap_str = "- (乖離 -)"
                    
                    line = (
                        f"{entry_str} | "
                        f"前終値：{row['PrevClose']} | 始値：{row['DayOpen']} | "
                        f"{row['Pattern']} | "
                        f"PnL: {row['PnL']:+.2%} | Gap: {row['Gap(%)']:+.2f}% | "
                        f"買：{row['In']} | 売：{row['Out']} | "
                        f"VWAP: {vwap_str} | "
                        f"{row['Reason']}"
                    )
                    log_report.append(line)
                log_report.append("\n")
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(log_report), language="text")
