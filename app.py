import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from datetime import datetime, timedelta, time, timezone

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS (Ver 1.81 デザイン完全継承) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }
    [data-testid="stDataFrame"] { font-size: 13px !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { text-align: left !important; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 15px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 16px; font-weight: 600; padding: 0; margin-top: 2px; }
    .plus { color: #ff4b4b; }
    .minus { color: #00f0a8; }
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. マッピング & セッション管理 (短縮版) ---
TICKER_NAME_MAP = {
    # 水産・食品 (不足分はGitHubにて入力してください)
    "1332.T": "ニッスイ", "2002.T": "日清粉G", "2269.T": "明治HD", "2282.T": "日本ハム", "2501.T": "サッポロHD",
    "2502.T": "アサヒG", "2503.T": "キリンHD", "2801.T": "キッコーマン", "2802.T": "味の素", "2871.T": "ニチレイ", 
}

MARKET_INDICES = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI", "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"}

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None

# --- 4. 関数定義 (スクリーニング・エンジン) ---
# ... (fetch_market_info, fetch_daily_stats_maps, calculate_rci は維持)
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
def fetch_daily_stats_maps(ticker, start):
    try:
        d_start = start - timedelta(days=30)
        df = yf.download(ticker, start=d_start, interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

def calculate_rci(series, period=9):
    def get_rci(sub):
        n = len(sub); d = ((np.arange(n) + 1) - sub.rank(ascending=False)).pow(2).sum()
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(get_rci)

def run_full_scan_engine(params):
    results = []; all_tickers = list(TICKER_NAME_MAP.keys()); prg = st.progress(0); status_text = st.empty()
    for idx, t in enumerate(all_tickers):
        name = TICKER_NAME_MAP.get(t, t); status_text.text(f"🔍 スキャン中 ({idx+1}/{len(all_tickers)}): [{t}] {name}"); prg.progress((idx + 1) / len(all_tickers))
        try:
            df = yf.download(t, period="3mo", interval="1d", progress=False)
            if df.empty or len(df) < 25: continue
            if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)
            p, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]; prev_p = df['Close'].iloc[-2]; ma25 = df['Close'].rolling(25).mean().iloc[-1]
            atrp = (AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().iloc[-1] / p) * 100
            adx = ADXIndicator(df['High'], df['Low'], df['Close']).adx().iloc[-1]; rsi = RSIIndicator(df['Close'], 14).rsi().iloc[-1]
            rci = calculate_rci(df['Close'], 9).iloc[-1]; ma25_dev = ((p - ma25) / ma25) * 100; val_total = (p * v) / 100000000 
            v_avg_5 = df['Volume'].rolling(5).mean().iloc[-2]; vup_rate = v / v_avg_5 if v_avg_5 > 0 else 1.0; price_change_pct = ((p - prev_p) / prev_p) * 100
            match = True
            if params['c_p'] and not (params['p_range'][0] <= p <= params['p_range'][1]): match = False
            if params['c_v'] and val_total < params['v_min']: match = False
            if params['c_atrp'] and not (params['atrp_range'][0] <= atrp <= params['atrp_range'][1]): match = False
            if params['c_adx'] and not (params['adx_range'][0] <= adx <= params['adx_range'][1]): match = False
            if params['c_rsi'] and not (params['rsi_range'][0] <= rsi <= params['rsi_range'][1]): match = False
            if params['c_rci'] and not (params['rci_range'][0] <= rci <= params['rci_range'][1]): match = False
            if params['c_vol'] and (v / 10000) < params['vol_min']: match = False
            if params['c_vup'] and vup_rate < params['vup_min']: match = False
            if params['c_ma25'] and not (params['ma25_range'][0] <= ma25_dev <= params['ma25_range'][1]): match = False
            if match: results.append({"コード": t, "銘柄名": name, "株価": f"{int(p)}", "出来高": f"{int(v):,}", "前日比": f"{price_change_pct:+.2f}%"})
        except: continue
    prg.empty(); status_text.empty()
    return pd.DataFrame(results)

# --- 5. サイドバー (Ver 1.68 構成) ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    if st.sidebar.button(l + (" [ 選択中 ]" if is_sel else ""), key=f"ps_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p; st.rerun()
# ... (設定スライダー等は維持)

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.97</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    with st.expander(f"🕒 指標チェック ▶︎ ({now_jst})", expanded=True):
        if st.button("🔄 リアルタイム更新"): st.cache_data.clear(); st.rerun()
        # ... (指標表示HTML)

# --- タブ2: スクリーニング (通常フィルタ初期チェック反映版) ---
with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["🔍通常フィルタ", "🔍ディフェンシブ", "🔍横ばい相場"])
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            exp_t = f"🔍 スクリーニング設定 ({['通常', 'ディフェンシブ', '横ばい'][i]})"
            with st.expander(exp_t, expanded=False):
                c1, c2, c3 = st.columns(3)
                with c1:
                    c_p = st.checkbox("**株価の範囲 (500~5000円)**", True, key=f"c_p_{i}"); st.caption("予算に合わせたフィルタリング")
                    p_range = st.slider("価格(円)", 100, 10000, (500, 5000), step=100, key=f"v_p_{i}"); st.divider()
                    c_v = st.checkbox("**売買代金 (50億円以上)**", True, key=f"c_v_{i}"); st.caption("株価 × 出来高")
                    v_min = st.number_input("億円以上", value=50.0 if i==0 else 300.0 if i==1 else 200.0, step=10.0, key=f"v_v_{i}"); st.divider()
                    c_atrp = st.checkbox("**平均値幅 (ATR% 2.0~4.0%)**", False if i==0 else True, key=f"c_atrp_{i}"); st.caption("ボラティリティの強さ")
                    atrp_range = st.slider("期待範囲%", 0.5, 5.0, (2.0, 4.0) if i==0 else (1.0, 2.5) if i==1 else (1.2, 2.5), step=0.5, key=f"v_atrp_{i}"); st.divider()
                    c_ma = st.checkbox("**移動平均上抜け/並び**", True if i==0 else False, key=f"c_ma_{i}"); st.caption("5MA/10MA/25MAの相関")
                    ma_opt = st.selectbox("条件選択", ["最強：上昇トレンド", "転換：GC直後", "収束：嵐の前の静けさ", "リバウンド：短期MA上抜け"], index=0 if i==0 else 2 if i==1 else 3, key=f"v_ma_{i}"); st.divider()
                with c2:
                    c_ema = st.checkbox("**EMA (9日・21日)**", True if i==0 else False, key=f"c_ema_{i}"); st.caption("直近の価格トレンド")
                    ema_opt = st.selectbox("EMA基準", ["強気：EMAの上で価格維持", "安定：EMA付近での推移", "レンジ：EMAを上下にまたぐ"], index=0 if i==0 else 1 if i==1 else 2, key=f"v_ema_{i}"); st.divider()
                    c_adx = st.checkbox("**ADX (強度 25~40)**", False if i==0 else True, key=f"c_adx_{i}"); st.caption("トレンドの強弱")
                    adx_range = st.slider("強度スコア", 0, 100, (25, 40) if i==0 else (10, 20), step=5, key=f"v_adx_{i}"); st.divider()
                    c_rci = st.checkbox("**RCI (過熱感 20~80)**", False if i==0 else True, key=f"c_rci_{i}"); st.caption("価格の過熱感：カスタム計算")
                    rci_range = st.slider("RCI範囲", -100, 100, (20, 80) if i==0 else (-20, 30) if i==1 else (-30, 30), step=5, key=f"v_rci_{i}"); st.divider()
                    c_rsi = st.checkbox("**RSI (レンジ 55~70)**", True, key=f"c_rsi_{i}"); st.caption("相対的な買われすぎ・売られすぎ")
                    rsi_range = st.slider("RSIレンジ", 0, 100, (55, 70) if i==0 else (40, 55) if i==1 else (45, 55), step=5, key=f"v_rsi_{i}"); st.divider()
                with c3:
                    c_vol = st.checkbox("**出来高 (10万株以上)**", True, key=f"c_vol_{i}"); st.caption("最低限の流動性確保")
                    vol_min = st.number_input("万株以上", value=10.0 if i==0 else 20.0 if i==1 else 10.0, step=10.0, key=f"v_vol_{i}"); st.divider()
                    c_vup = st.checkbox("**出来高増加率 (1.3倍以上)**", False if i==0 else True, key=f"c_vup_{i}"); st.caption("前日比での注目度アップ")
                    vup_min = st.slider("増加倍率", 1.0, 5.0, 1.3 if i==0 else 1.1 if i==1 else 1.2, step=0.1, key=f"v_vup_{i}"); st.divider()
                    c_ma25 = st.checkbox("**25日移動平均乖離率 (0.0~7.0%)**", True, key=f"c_ma25_{i}"); st.caption("中長期トレンドからの乖離")
                    ma25_range = st.slider("偏差%", -20.0, 20.0, (0.0, 7.0) if i==0 else (-3.0, 2.0) if i==1 else (-2.0, 3.0), step=1.0, key=f"v_ma25_{i}"); st.divider()
                    c_bb = st.checkbox("**ボリンジャーバンド (1.0~2.0σ)**", True if i==0 else False, key=f"c_bb_{i}"); st.caption("α範囲による逆張り・順張り目安")
                    bb_range = st.slider("σ範囲", -3.0, 3.0, (1.0, 2.0) if i==0 else (-1.0, 0.0) if i==1 else (1.0, 2.0), step=1.0, key=f"v_bb_{i}"); st.divider()

            if st.button("スクリーニング実行", key=f"run_s_{i}", type="primary", use_container_width=True):
                p_dict = {'c_p': c_p, 'p_range': p_range, 'c_v': c_v, 'v_min': v_min, 'c_atrp': c_atrp, 'atrp_range': atrp_range, 'c_ma': c_ma, 'ma_opt': ma_opt, 'c_ema': c_ema, 'ema_opt': ema_opt, 'c_adx': c_adx, 'adx_range': adx_range, 'c_rsi': c_rsi, 'rsi_range': rsi_range, 'c_rci': c_rci, 'rci_range': rci_range, 'c_vol': c_vol, 'vol_min': vol_min, 'c_vup': c_vup, 'vup_min': vup_min, 'c_ma25': c_ma25, 'ma25_range': ma25_range, 'c_bb': c_bb, 'bb_range': bb_range}
                res_df = run_full_scan_engine(p_dict)
                if not res_df.empty: st.success(f"🎯 230銘柄中 {len(res_df)} 銘柄が合致しました。"); st.dataframe(res_df, hide_index=True, use_container_width=True)
                else: st.warning("合致なし。条件を緩めてください。")

# --- タブ3: バックテスト ---
with tab_bt: st.info("バックテストを実行します...")
