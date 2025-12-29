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
    /* タイトルエリアデザイン */
    .main-title { font-weight: 400; font-size: 46px; margin: 0; padding: 0; }
    .sub-title { font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa; }

    /* 指標カードデザイン */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { 
        background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; 
        padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; 
    }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; }
    .delta-badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }

    /* バックテスト・サマリーボックス */
    .metric-container { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px; }
    @media (max-width: 640px) { .metric-container { grid-template-columns: 1fr 1fr; } }
    .metric-box { background-color: #262730; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #3d414b; }
    .metric-label { font-size: 12px; color: #aaaaaa; }
    .metric-value { font-size: 24px; font-weight: bold; color: #ffffff; }

    /* AI予測ボックス */
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    
    /* サイドバーボタン幅 */
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; }

    /* エントリー条件のチェックボックスフォントサイズ調整 */
    div[data-testid="stCheckbox"] label p {
        font-size: 14px !important;
    }

    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. セッション管理 & 定数 ---
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8267.T"
if 'scan_results' not in st.session_state: st.session_state['scan_results'] = []

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
    "9984.T": "ソフトバンクG", "1570.T": "日経レバ"
}

# --- 4. ロジック関数 ---

def get_trade_pattern(row, gap_pct):
    """勝ちパターン判定ロジック（B救済版）"""
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row['RSI14'] >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

@st.cache_data(ttl=600)
def fetch_intraday(ticker, start):
    try:
        df = yf.download(ticker, start=start, interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        d_start = start - timedelta(days=30)
        df = yf.download(ticker, start=d_start, interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        else: df.index = df.index.tz_convert('Asia/Tokyo')
        prev_close = df['Close'].shift(1)
        prev_close_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, prev_close) if pd.notna(c)}
        curr_open_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        return prev_close_map, curr_open_map
    except: return {}, {}

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

# --- 5. サイドバー (戦略プリセット & 修正) ---
st.sidebar.markdown("### ♟️ 戦略プリセット")
col_s1, col_s2, col_s3 = st.sidebar.columns(3)
if col_s1.button("通常フィルター"): st.session_state['preset'] = "NORMAL"
if col_s2.button("ディフェンシブ"): st.session_state['preset'] = "DEFENSIVE"
if col_s3.button("横ばい相場対応"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
start_entry_time = st.sidebar.time_input("開始時間", time(9, 0), step=300)
end_entry_time = st.sidebar.time_input("終了時間", time(9, 15), step=300)

# 余白の追加
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
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
trailing_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, 0.05) / 100

# --- 6. メインレイアウト ---
st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>FORE CASTER</h1>
        <h3 style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>SCREENING & BACKTEST | ver 1.62</h3>
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
        ai_msg = f"VIX指数は {vix:.1f} です。地合いに合わせた戦略を選択してください。"
        st.markdown(f'<div class="ai-box"><div style="color:#60a5fa; font-weight:bold;">🤖 AI予測</div><div style="color:#d1d5db; font-size:13px;">{ai_msg}</div></div>', unsafe_allow_html=True)

    st.divider()
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        st.success("スキャン完了！(ver 1.4のロジックでTop5を抽出しました)")
        st.rerun()

# --- タブ3: バックテスト ---
with tab_bt:
    tickers = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    bt_exec = st.button("バックテスト実行", type="primary", use_container_width=True)
    
    if bt_exec:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        all_trades = []
        progress_bar = st.progress(0)
        
        SLIPPAGE_PCT = 0.0003
        FORCE_CLOSE_TIME = time(14, 55)

        for i, ticker in enumerate(tickers):
            progress_bar.progress((i + 1) / len(tickers))
            df = fetch_intraday(ticker, start_date)
            prev_close_map, curr_open_map = fetch_daily_stats_maps(ticker, start_date)
            
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')

            df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
            macd = MACD(close=df['Close']); df['MACD_H'] = macd.macd_diff(); df['MACD_H_Prev'] = df['MACD_H'].shift(1)
            rsi = RSIIndicator(close=df['Close'], window=14); df['RSI14'] = rsi.rsi(); df['RSI14_Prev'] = df['RSI14'].shift(1)
            
            def compute_vwap(d):
                tp = (d['High'] + d['Low'] + d['Close']) / 3
                cum_vp = (tp * d['Volume']).cumsum()
                return (cum_vp / d['Volume'].cumsum().replace(0, np.nan)).ffill()

            for date in np.unique(df.index.date):
                day = df[df.index.date == date].copy().between_time('09:00', '15:00')
                if day.empty: continue
                day['VWAP'] = compute_vwap(day)
                date_str = date.strftime('%Y-%m-%d')
                prev_c = prev_close_map.get(date_str); day_o = curr_open_map.get(date_str)
                if prev_c is None or day_o is None: continue
                gap_p = (day_o - prev_c) / prev_c
                
                in_pos = False; entry_p = 0; trail_high = 0; trail_active = False

                for ts, row in day.iterrows():
                    cur_t = ts.time()
                    if pd.isna(row['EMA5']): continue
                    if not in_pos:
                        if start_entry_time <= cur_t <= end_entry_time and gap_min <= gap_p <= gap_max:
                            c_vwap = (row['Close'] > row['VWAP']) if use_vwap else True
                            c_ema = (row['Close'] > row['EMA5']) if use_ema else True
                            c_rsi = ((row['RSI14'] > 45) and (row['RSI14'] > row['RSI14_Prev'])) if use_rsi else True
                            c_macd = (row['MACD_H'] > row['MACD_H_Prev']) if use_macd else True
                            if c_vwap and c_ema and c_rsi and c_macd:
                                entry_p = row['Close'] * (1 + SLIPPAGE_PCT); in_pos = True; entry_t = ts
                                stop_p = entry_p * (1 + stop_loss); trail_high = row['High']
                                pattern = get_trade_pattern(row, gap_p)
                    else:
                        if row['High'] > trail_high: trail_high = row['High']
                        if not trail_active and (trail_high >= entry_p * (1 + trailing_start)): trail_active = True
                        exit_p = None; reason = ""
                        if trail_active and (row['Low'] <= trail_high * (1 - trailing_pct)):
                            exit_p = trail_high * (1 - trailing_pct) * (1 - SLIPPAGE_PCT); reason = "トレーリング"
                        elif row['Low'] <= stop_p:
                            exit_p = stop_p * (1 - SLIPPAGE_PCT); reason = "損切り"
                        elif cur_t >= FORCE_CLOSE_TIME:
                            exit_p = row['Close'] * (1 - SLIPPAGE_PCT); reason = "時間切れ"
                        if exit_p:
                            all_trades.append({'Ticker': ticker, 'Entry': entry_t, 'Exit': ts, 'PnL': (exit_p - entry_p) / entry_p, 'Reason': reason, 'Pattern': pattern, 'In': int(entry_p), 'Out': int(exit_p)})
                            in_pos = False; break
        progress_bar.empty()
        res_df = pd.DataFrame(all_trades)
        
        if res_df.empty:
            st.warning("条件に合うトレードはありませんでした。")
        else:
            b_tab1, b_tab2, b_tab3, b_tab4 = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "📝 詳細ログ"])
            with b_tab1:
                cnt = len(res_df); wr = (res_df['PnL']>0).mean()
                ev = res_df['PnL'].mean(); pf = res_df[res_df['PnL']>0]['PnL'].sum() / abs(res_df[res_df['PnL']<=0]['PnL'].sum())
                st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-box"><div class="metric-label">総トレード数</div><div class="metric-value">{cnt}回</div></div>
                    <div class="metric-box"><div class="metric-label">勝率</div><div class="metric-value">{wr:.1%}</div></div>
                    <div class="metric-box"><div class="metric-label">PF</div><div class="metric-value">{pf:.2f}</div></div>
                    <div class="metric-box"><div class="metric-label">期待値</div><div class="metric-value">{ev:.2%}</div></div>
                </div>
                """, unsafe_allow_html=True)
            with b_tab2:
                pat_stats = res_df.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                pat_stats.columns = ['パターン', '数', '勝率', '平均']
                st.dataframe(pat_stats, use_container_width=True, hide_index=True)
            with b_tab3:
                st.write("ギャップ方向別の分析")
            with b_tab4:
                st.dataframe(res_df, use_container_width=True)
