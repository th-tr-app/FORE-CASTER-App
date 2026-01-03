import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time, timezone

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS (Ver 1.68 デザイン完全継承) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 0 30px 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }
    
    /* 表全体のフォントサイズと左揃え */
    [data-testid="stDataFrame"] { font-size: 13px !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { text-align: left !important; }

    /* リアルタイム指標カード */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 15px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 16px; font-weight: 600; padding: 0; margin-top: 2px; }
    .plus { color: #ff4b4b; }
    .minus { color: #00f0a8; }

    /* バックテストサマリー */
    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 10px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 12px; color: #aaaaaa; margin-bottom: 2px; }
    .summary-value { font-size: 26px; font-weight: 600; color: #ffffff; }

    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. マッピング ＆ 重要定数 (復旧) ---
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

# 業種・MA・EMA共通選択肢
SECTOR_OPTIONS = ["電機", "商社", "銀行", "自動車", "部品", "機械", "重工", "エネルギー", "建設", "プラント", "電力・ガス", "医薬品", "食品", "通信", "鉄道", "インフラ", "半導体周辺", "石油・ガス"]
MA_CRITERIA = ["5MA ＞ 10MA ＞ 25MA (5MAが25MAを上抜けた直後)", "5MA ≒ 10MA（収束 / 5MAが10MAを上抜けた直後）", "5営業日以内に5MA or 10MAを上抜け (25MA横ばい/緩やか)"]
EMA_CRITERIA = ["EMA9 ＞ EMA21 ＞ EMA50 (価格はEMA9～21の上)", "EMA9 ≒ EMA21 (価格はEMA21付近 or やや上)", "EMA9 と EMA21 が収束・クロス (価格はEMA9～21の間)"]

# デフォルト設定値
DEFAULT_CONFIG = {
    "NORMAL": {"sector": ["電機", "商社", "銀行", "自動車", "部品", "機械", "重工", "エネルギー", "建設", "プラント"], "val": 50.0, "atr_p": (2.0, 4.0), "mcap": 500, "price": (500, 5000), "ma25": (0.0, 7.0), "vol": 10, "cross": MA_CRITERIA[0], "margin": (3.0, 10.0), "per": (10.0, 30.0), "ema": EMA_CRITERIA[0], "adx": (25, 40), "atr": (1.5, 3.5), "rci": (20, 80), "rsi": (55, 70), "bb": (1.0, 2.0), "rate": 4, "vol_up": 1.3},
    "DEFENSIVE": {"sector": ["電力・ガス", "医薬品", "食品", "通信", "鉄道", "インフラ", "エネルギー", "銀行"], "val": 300.0, "atr_p": (1.0, 2.5), "mcap": 2000, "price": (500, 5000), "ma25": (-3.0, 2.0), "vol": 20, "cross": MA_CRITERIA[1], "margin": (1.5, 3.0), "per": (10.0, 20.0), "ema": EMA_CRITERIA[1], "adx": (10, 20), "atr": (1.0, 2.0), "rci": (-20, 30), "rsi": (40, 55), "bb": (-1.0, 0.0), "rate": 4, "vol_up": 1.1},
    "RANGE": {"sector": ["商社", "石油・ガス", "銀行", "電機", "半導体周辺", "建設", "プラント"], "val": 200.0, "atr_p": (1.2, 2.5), "mcap": 300, "price": (500, 5000), "ma25": (-2.0, 3.0), "vol": 10, "cross": MA_CRITERIA[2], "margin": (2.0, 8.0), "per": (8.0, 25.0), "ema": EMA_CRITERIA[2], "adx": (10, 20), "atr": (0.8, 2.0), "rci": (-30, 30), "rsi": (45, 55), "bb": (1.0, 2.0), "rate": 3, "vol_up": 1.2}
}

# --- セッション一括初期化 ---
if 'params' not in st.session_state:
    st.session_state['params'] = {k: v.copy() for k, v in DEFAULT_CONFIG.items()}
    st.session_state['enabled'] = {k: {p: True for p in v.keys()} for k, v in DEFAULT_CONFIG.items()}

if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None
if 'sc_results' not in st.session_state: st.session_state['sc_results'] = None

# --- 4. 関数定義 (成功版 app_1.69.py のコードを完全維持) ---
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

def run_scan_engine(ticker, days_back, entry_start, entry_end, use_vwap):
    try:
        df = yf.download(ticker, period="1mo", interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return None
        df.index = df.index.tz_convert('Asia/Tokyo'); pnls = []
        for d in np.unique(df.index.date)[-days_back:]:
            day = df[df.index.date == d].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            in_pos = False
            for ts, row in day.iterrows():
                if not in_pos and entry_start <= ts.time() <= entry_end:
                    if not use_vwap or (row['Close'] > row['VWAP']): entry_p = row['Close'] * 1.0003; in_pos = True
                elif in_pos:
                    if row['Low'] <= entry_p * 0.992 or ts.time() >= time(14, 55):
                        exit_p = row['Close'] * 0.9997; pnls.append((exit_p - entry_p) / entry_p); in_pos = False; break
        return np.mean(pnls) if pnls else None
    except: return None

def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

# --- 5. サイドバー ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    label = l + (" [ 選択中 ]" if is_sel else "")
    if st.sidebar.button(label, key=f"side_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back_p = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
s_entry_t = st.sidebar.time_input("開始時間", time(9, 0), step=300)
e_entry_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)
st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.subheader("📉 エントリー条件")
u_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
u_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
u_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
u_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)
st.sidebar.divider()
g_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
g_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100
st.sidebar.subheader("💰 決済ルール")
ts_v = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05) / 100
tp_v = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05) / 100
sl_v = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05) / 100

# --- 6. メインレイアウト ---
st.markdown(f"<h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.79</h3>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top: # app_1.69.py 復旧
    if st.button("🔄 指標更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        cards_html = '<div class="metric-grid">'
        for n in ["日経平均", "日経先物(CME)", "ドル/円", "NYダウ30種", "原油先物(WTI)", "Gold先物(COMEX)", "VIX指数", "SOX指数"]:
            i = m_data.get(n, {})
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        res = []; prg = st.progress(0); tks = list(TICKER_NAME_MAP.keys())
        for idx, t in enumerate(tks):
            prg.progress((idx + 1) / len(tks))
            ev = run_scan_engine(t, 20, time(9,0), time(9,30), True)
            if ev and ev > 0: res.append({"コード": t, "銘柄名": TICKER_NAME_MAP[t], "期待値": f"{ev:+.2%}"})
        if res: st.session_state['sc_results'] = sorted(res, key=lambda x: x['期待値'], reverse=True)[:5]
        prg.empty()
    if st.session_state['sc_results']:
        st.success("🎯 期待値Top5を選出しました。")
        st.dataframe(pd.DataFrame(st.session_state['sc_results']), hide_index=True, use_container_width=True)

with tab_screen: # スクリーニング管理 (MA・EMA選択式 ＆ リセット強化)
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["🔍通常フィルタ", "🔍ディフェンシブ", "🔍横ばい相場"])
    p_keys = ["NORMAL", "DEFENSIVE", "RANGE"]

    for i, s_tab in enumerate(s_tabs):
        pid = p_keys[i]
        with s_tab:
            with st.expander(f"🔍 スクリーニング設定 ({['通常', 'ディフェンシブ', '横ばい'][i]})", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.session_state['enabled'][pid]['sector'] = st.checkbox("業種", st.session_state['enabled'][pid]['sector'], key=f"e1_{pid}")
                    st.session_state['params'][pid]['sector'] = st.multiselect("選択", SECTOR_OPTIONS, st.session_state['params'][pid]['sector'], key=f"v1_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['val'] = st.checkbox("売買代金", st.session_state['enabled'][pid]['val'], key=f"e2_{pid}")
                    st.session_state['params'][pid]['val'] = st.number_input("億円以上", value=st.session_state['params'][pid]['val'], key=f"v2_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['atr_p'] = st.checkbox("平均値幅 (ATR%)", st.session_state['enabled'][pid]['atr_p'], key=f"e3_{pid}")
                    st.session_state['params'][pid]['atr_p'] = st.slider("期待%", 0.5, 5.0, st.session_state['params'][pid]['atr_p'], key=f"v3_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['mcap'] = st.checkbox("時価総額", st.session_state['enabled'][pid]['mcap'], key=f"e4_{pid}")
                    st.session_state['params'][pid]['mcap'] = st.number_input("億円以上 (総額)", value=st.session_state['params'][pid]['mcap'], key=f"v4_{pid}"); st.divider()
                with c2:
                    st.session_state['enabled'][pid]['price'] = st.checkbox("株価の範囲", st.session_state['enabled'][pid]['price'], key=f"e5_{pid}")
                    st.session_state['params'][pid]['price'] = st.slider("円", 100, 10000, st.session_state['params'][pid]['price'], key=f"v5_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['ma25'] = st.checkbox("25日線乖離率", st.session_state['enabled'][pid]['ma25'], key=f"e6_{pid}")
                    st.session_state['params'][pid]['ma25'] = st.slider("偏差%", -20.0, 20.0, st.session_state['params'][pid]['ma25'], key=f"v6_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['vol'] = st.checkbox("出来高", st.session_state['enabled'][pid]['vol'], key=f"e7_{pid}")
                    st.session_state['params'][pid]['vol'] = st.number_input("万株以上", value=st.session_state['params'][pid]['vol'], key=f"v7_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['cross'] = st.checkbox("移動平均上抜け", st.session_state['enabled'][pid]['cross'], key=f"e8_{pid}")
                    st.session_state['params'][pid]['cross'] = st.selectbox("条件選択", MA_CRITERIA, index=MA_CRITERIA.index(st.session_state['params'][pid]['cross']) if st.session_state['params'][pid]['cross'] in MA_CRITERIA else 0, key=f"v8_{pid}"); st.divider()
                with c3:
                    st.session_state['enabled'][pid]['ema'] = st.checkbox("EMA (9/21)", st.session_state['enabled'][pid]['ema'], key=f"e11_{pid}")
                    st.session_state['params'][pid]['ema'] = st.selectbox("EMA基準", EMA_CRITERIA, index=EMA_CRITERIA.index(st.session_state['params'][pid]['ema']) if st.session_state['params'][pid]['ema'] in EMA_CRITERIA else 0, key=f"v11_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['bb'] = st.checkbox("ボリンジャーバンド", st.session_state['enabled'][pid]['bb'], key=f"e16_{pid}")
                    st.session_state['params'][pid]['bb'] = st.slider("σ範囲", -3.0, 3.0, st.session_state['params'][pid]['bb'], step=0.1, key=f"v16_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['rate'] = st.checkbox("コンセンサス", st.session_state['enabled'][pid]['rate'], key=f"e17_{pid}")
                    st.session_state['params'][pid]['rate'] = st.select_slider("メモリ", options=[0,1,2,3,4,5], value=st.session_state['params'][pid]['rate'], key=f"v17_{pid}"); st.divider()
                    st.session_state['enabled'][pid]['vol_up'] = st.checkbox("出来高増加率", st.session_state['enabled'][pid]['vol_up'], key=f"e18_{pid}")
                    st.session_state['params'][pid]['vol_up'] = st.slider("倍率", 1.0, 5.0, st.session_state['params'][pid]['vol_up'], key=f"v18_{pid}"); st.divider()

                if st.button("デフォルトの設定に戻す", key=f"reset_btn_{pid}", use_container_width=True):
                    st.session_state['params'][pid] = DEFAULT_CONFIG[pid].copy()
                    st.session_state['enabled'][pid] = {k: True for k in DEFAULT_CONFIG[pid].keys()}
                    st.rerun()

            if st.button(f"スクリーニング実行", key=f"scr_btn_{pid}", type="primary", use_container_width=True):
                st.dataframe(pd.DataFrame([{"コード": "7203.T", "銘柄名": "トヨタ", "株価": "計算中...", "前日比%": "+1.2%"}]))

with tab_bt: # app_1.69.py 継承
    t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        trades = []; prg = st.progress(0); end_d = datetime.now(); start_d = end_d - timedelta(days=days_back_p)
        for idx, ticker in enumerate(t_list):
            prg.progress((idx + 1) / len(t_list))
            try:
                df = yf.download(ticker, start=start_d, end=end_d, interval="5m", progress=False, auto_adjust=False)
                pc_map, co_map = fetch_daily_stats_maps(ticker, start_d)
                if df.empty: continue
                df.index = df.index.tz_convert('Asia/Tokyo'); df['EMA5'] = EMAIndicator(df['Close'], 5).ema_indicator()
                df['RSI14'] = RSIIndicator(df['Close'], 14).rsi(); df['RSI14_P'] = df['RSI14'].shift(1)
                macd_o = MACD(df['Close']); df['MH'] = macd_o.macd_diff(); df['MH_P'] = df['MH'].shift(1)
                for d in np.unique(df.index.date):
                    day = df[df.index.date == d].copy().between_time('09:00', '15:00')
                    if day.empty: continue
                    day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
                    pc, do = pc_map.get(d.strftime('%Y-%m-%d')), co_map.get(d.strftime('%Y-%m-%d'))
                    if pc is None or do is None: continue
                    gap_v = (do - pc) / pc; in_pos = False; t_high = 0; t_active = False
                    for ts, row in day.iterrows():
                        if not in_pos:
                            if s_entry_t <= ts.time() <= e_entry_t and g_min <= gap_v <= g_max:
                                if (not u_vwap or row['Close'] > row['VWAP']) and (not u_ema or row['Close'] > row['EMA5']) and (not u_rsi or row['RSI14'] > 45):
                                    entry_p = row['Close'] * 1.0003; in_pos = True; entry_t = ts; entry_vwap = row['VWAP']; stop_p = entry_p * (1 + sl_v); t_high = row['High']; pat = get_trade_pattern(row, gap_v)
                        else:
                            t_high = max(t_high, row['High'])
                            if not t_active and t_high >= entry_p * (1 + ts_v): t_active = True
                            ex_p = None
                            if t_active and row['Low'] <= t_high * (1 - tp_v): ex_p = t_high * (1 - tp_v) * 0.9997; rsn = "トレーリング"
                            elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997; rsn = "損切り"
                            elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997; rsn = "時間切れ"
                            if ex_p:
                                trades.append({'Ticker': ticker, 'Entry': entry_t, 'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p, 'Pattern': pat, 'Gap(%)': gap_v*100, 'EntryVWAP': entry_vwap, 'Reason': rsn, 'PrevClose': pc, 'DayOpen': do})
                                in_pos = False; break
            except: continue
        st.session_state['bt_results'] = pd.DataFrame(trades) if trades else None
        st.session_state['bt_period'] = f"{start_d.strftime('%Y-%m-%d')} - {end_d.strftime('%Y-%m-%d')}"

    res_df = st.session_state['bt_results']
    if res_df is not None:
        tabs = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間帯分析", "📝 詳細ログ"])
        with tabs[0]: # サマリー
            w_f = res_df[res_df['PnL']>0]['PnL']; l_f = res_df[res_df['PnL']<=0]['PnL']
            pf_f = w_f.sum()/abs(l_f.sum()) if not l_f.empty and l_f.sum()!=0 else 0
            st.markdown(f"<div class='summary-container'><div class='summary-box'><div class='summary-label'>総トレード数</div><div class='summary-value'>{len(res_df)}回</div></div><div class='summary-box'><div class='summary-label'>勝率</div><div class='summary-value'>{(res_df['PnL']>0).mean():.1%}</div></div><div class='summary-box'><div class='summary-label'>PF（総利益 ÷ 総損失）</div><div class='summary-value'>{pf_f:.2f}</div></div><div class='summary-box'><div class='summary-label'>期待値</div><div class='summary-value'>{res_df['PnL'].mean():.2%}</div></div></div>", unsafe_allow_html=True)
            st.code("\n".join(["=================\n BACKTEST REPORT \n=================", f"Period: {st.session_state.get('bt_period','')}\n"]), language="text")
        with tabs[3]: # VWAP
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy()
                if tdf.empty: continue
                st.markdown(f"#### [{tk}] {TICKER_NAME_MAP.get(tk, tk)}\n##### エントリー時のVWAPと勝率")
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                v_bins = tdf.groupby(pd.cut(tdf['VWAP乖離(%)'], bins=np.arange(-1.0, 1.2, 0.2)), observed=True).agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x>0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                v_bins.columns = ['乖離率レンジ', 'トレード数', '勝率', '平均損益']
                v_bins['乖離率レンジ'] = v_bins['乖離率レンジ'].apply(lambda i: f"{i.left:.1f}% ～ {i.right:.1f}%")
                v_bins['トレード数'] = v_bins['トレード数'].astype(str)
                v_bins['勝率'] = v_bins['勝率'].apply(lambda x: f"{x:.1%}"); v_bins['平均損益'] = v_bins['平均損益'].apply(lambda x: f"{x:+.2%}")
                st.dataframe(v_bins, hide_index=True, use_container_width=True)
        with tabs[5]: # 詳細ログ
            log = []
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy().sort_values('Entry', ascending=False)
                if tdf.empty: continue
                log.append(f"[{tk}] {TICKER_NAME_MAP.get(tk, tk)} 取引履歴\n" + "-"*80)
                for _, r in tdf.iterrows(): log.append(f"{r['Entry'].strftime('%Y-%m-%d %H:%M')} | PnL: {r['PnL']:+.2%} | {r['Pattern']} | {r['Reason']}")
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(log), language="text")
