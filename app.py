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

# --- 2. カスタムCSS (Ver 1.68 デザインを完全継承) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }
    
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
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 10px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 12px; color: #aaaaaa; margin-bottom: 2px; }
    .summary-value { font-size: 26px; font-weight: 600; color: #ffffff; }

    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. マッピング & セッション管理 ---
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

MARKET_INDICES = {
    "日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None

# --- 4. 関数定義 (Ver 1.68 の計算エンジンを完全維持) ---
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

def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

# --- 5. サイドバー (Ver 1.68 構成) ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    label = l + (" [ 選択中 ]" if is_sel else "")
    if st.sidebar.button(label, key=f"ps_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back_param = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
start_entry_t = st.sidebar.time_input("開始時間", time(9, 0), step=300)
end_entry_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)
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
ts_val = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05) / 100
tp_val = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05) / 100
sl_val = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05) / 100

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.68</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

# --- タブ1: ワンタッチ (Ver 1.68 復旧) ---
with tab_top:
    if st.button("🔄 指標更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info(); cards_html = '<div class="metric-grid">'
        for n in MARKET_INDICES.keys():
            i = m_data.get(n, {})
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
        vix = m_data.get("VIX指数", {}).get("val", 0)
        st.markdown(f'<div class="ai-box"><div style="color:#60a5fa; font-weight:bold;">🤖 AI予測</div><div style="color:#d1d5db; font-size:13px;">VIX指数は {vix:.1f} です。地合いに合わせた戦略を選択してください。</div></div>', unsafe_allow_html=True)
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        res_list = []; prg = st.progress(0); tks = list(TICKER_NAME_MAP.keys())
        for idx, t in enumerate(tks):
            prg.progress((idx + 1) / len(tks))
            ev = run_scan_engine(t, 20, time(9,0), time(9,30), True)
            if ev and ev > 0: res_list.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
        if res_list:
            top5 = sorted(res_list, key=lambda x: x['ev'], reverse=True)[:5]
            st.session_state['target_tickers'] = ", ".join([d['code'] for d in top5]); st.rerun()

# --- タブ2: スクリーニング (新規構築) ---
with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["🔍通常フィルタ", "🔍ディフェンシブ", "🔍横ばい相場"])
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            exp_t = f"🔍 スクリーニング設定 ({['通常', 'ディフェンシブ', '横ばい'][i]})"
            with st.expander(exp_t, expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.checkbox("業種", True, key=f"c1_{i}"); st.multiselect("業種選択", ["情報・通信", "電気機器", "銀行業"], key=f"v1_{i}"); st.divider()
                    st.checkbox("売買代金", True, key=f"c2_{i}"); st.number_input("億円以上", 10.0, key=f"v2_{i}"); st.divider()
                    st.checkbox("平均値幅 (ATR%)", True, key=f"c3_{i}"); st.slider("最小%", 0.5, 5.0, 1.5, key=f"v3_{i}"); st.divider()
                    st.checkbox("時価総額", True, key=f"c4_{i}"); st.number_input("億円以上 (総額)", 500, key=f"v4_{i}"); st.divider()
                    st.checkbox("株価の範囲", True, key=f"c5_{i}"); st.slider("価格(円)", 100, 10000, (500, 5000), key=f"v5_{i}"); st.divider()
                    st.checkbox("25日移動平均乖離率", True, key=f"c6_{i}"); st.slider("乖離%", -20.0, 20.0, (-5.0, 5.0), key=f"v6_{i}"); st.divider()
                with c2:
                    st.checkbox("出来高", True, key=f"c7_{i}"); st.number_input("万株以上", 10, key=f"v7_{i}"); st.divider()
                    st.checkbox("移動平均上抜け", False, key=f"c8_{i}"); st.selectbox("MA種類", ["5日線", "25日線", "75日線"], key=f"v8_{i}"); st.divider()
                    st.checkbox("信用倍率", True, key=f"c9_{i}"); st.number_input("倍率以下", 10.0, key=f"v9_{i}"); st.divider()
                    st.checkbox("PER (株価収益率)", True, key=f"c10_{i}"); st.slider("PER範囲", 0.0, 100.0, (10.0, 30.0), key=f"v10_{i}"); st.divider()
                    st.checkbox("EMA (9日・21日)", False, key=f"c11_{i}"); st.multiselect("EMA条件", ["9日上抜け", "21日上抜け"], key=f"v11_{i}"); st.divider()
                    st.checkbox("ADX (方向性指数)", True, key=f"c12_{i}"); st.slider("強度スコア", 0, 100, 25, key=f"v12_{i}"); st.divider()
                with c3:
                    st.checkbox("ATR (最小値幅)", True, key=f"c13_{i}"); st.number_input("円単位", 10.0, key=f"v13_{i}"); st.divider()
                    st.checkbox("RCI (順位相関計数)", False, key=f"c14_{i}"); st.slider("9日RCI", -100, 100, 0, key=f"v14_{i}"); st.divider()
                    st.checkbox("RSI (14日)", True, key=f"c15_{i}"); st.slider("RSIレンジ", 0, 100, (30, 70), key=f"v15_{i}"); st.divider()
                    st.checkbox("ボリンジャーバンド", False, key=f"c16_{i}"); st.slider("σ範囲", -3.0, 3.0, (1.0, 2.0), step=0.1, key=f"v16_{i}"); st.divider()
                    st.checkbox("コンセンサス", True, key=f"c17_{i}"); st.select_slider("メモリ", options=[0,1,2,3,4,5], value=3, key=f"v17_{i}"); st.divider()
                    st.checkbox("出来高増加率", True, key=f"c18_{i}"); st.slider("前日比倍", 1.0, 5.0, 1.2, key=f"v18_{i}"); st.divider()
            st.button("スクリーニング実行", key=f"run_s_{i}", type="primary", use_container_width=True)

# --- タブ3: バックテスト (Ver 1.68 ロジックを完全維持) ---
with tab_bt:
    t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        all_trades = []; progress_bar = st.progress(0)
        end_dt = datetime.now(); start_dt = end_dt - timedelta(days=days_back_param)
        for idx, ticker in enumerate(t_list):
            progress_bar.progress((idx + 1) / len(t_list))
            try:
                df = yf.download(ticker, start=start_dt, end=end_dt, interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
                pc_map, co_map = fetch_daily_stats_maps(ticker, start_dt)
                if df.empty: continue
                df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
                df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
                df['RSI14'] = RSIIndicator(close=df['Close'], window=14).rsi(); df['RSI14_P'] = df['RSI14'].shift(1)
                macd_o = MACD(close=df['Close']); df['MH'] = macd_o.macd_diff(); df['MH_P'] = df['MH'].shift(1)
                for d in np.unique(df.index.date):
                    day = df[df.index.date == d].copy().between_time('09:00', '15:00')
                    if day.empty: continue
                    day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
                    pc = pc_map.get(d.strftime('%Y-%m-%d')); do = co_map.get(d.strftime('%Y-%m-%d'))
                    if pc is None or do is None: continue
                    gap_v = (do - pc) / pc
                    in_pos = False; t_high = 0; t_active = False
                    for ts, row in day.iterrows():
                        if not in_pos:
                            if start_entry_t <= ts.time() <= end_entry_t and g_min <= gap_v <= g_max:
                                if (not u_vwap or row['Close'] > row['VWAP']) and (not u_ema or row['Close'] > row['EMA5']) and (not u_rsi or row['RSI14'] > 45):
                                    entry_p = row['Close'] * 1.0003; in_pos = True; entry_t = ts; entry_vwap = row['VWAP']; stop_p = entry_p * (1 + sl_val); t_high = row['High']; pat = get_trade_pattern(row, gap_v)
                        else:
                            t_high = max(t_high, row['High'])
                            if not t_active and t_high >= entry_p * (1 + ts_val): t_active = True
                            ex_p = None
                            if t_active and row['Low'] <= t_high * (1 - tp_val): ex_p = t_high * (1 - tp_val) * 0.9997; rsn = "トレーリング"
                            elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997; rsn = "損切り"
                            elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997; rsn = "時間切れ"
                            if ex_p:
                                all_trades.append({'Ticker': ticker, 'Entry': entry_t, 'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p, 'Pattern': pat, 'Gap(%)': gap_v*100, 'EntryVWAP': entry_vwap, 'Reason': rsn, 'PrevClose': pc, 'DayOpen': do})
                                in_pos = False; break
            except: continue
        progress_bar.empty()
        st.session_state['bt_results'] = pd.DataFrame(all_trades) if not len(all_trades)==0 else None
        st.session_state['bt_period'] = f"{start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}"

    st.markdown("<br>", unsafe_allow_html=True)
    res_df = st.session_state['bt_results']
    if res_df is not None:
        tabs = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間帯分析", "📝 詳細ログ"])
        with tabs[0]: # サマリー
            w_f = res_df[res_df['PnL']>0]['PnL']; l_f = res_df[res_df['PnL']<=0]['PnL']
            pf_f = w_f.sum()/abs(l_f.sum()) if not l_f.empty and l_f.sum()!=0 else 0
            st.markdown(f"<div class='summary-container'><div class='summary-box'><div class='summary-label'>総トレード数</div><div class='summary-value'>{len(res_df)}回</div></div><div class='summary-box'><div class='summary-label'>勝率</div><div class='summary-value'>{(res_df['PnL']>0).mean():.1%}</div></div><div class='summary-box'><div class='summary-label'>PF（総利益 ÷ 総損失）</div><div class='summary-value'>{pf_f:.2f}</div></div><div class='summary-box'><div class='summary-label'>期待値</div><div class='summary-value'>{res_df['PnL'].mean():.2%}</div></div></div>", unsafe_allow_html=True)
            rpt = ["=================\n BACKTEST REPORT \n=================", f"Period: {st.session_state.get('bt_period','')}\n"]
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk]
                if tdf.empty: continue
                rpt.append(f">>> TICKER: {tk} | {TICKER_NAME_MAP.get(tk, tk)}\nトレード数: {len(tdf)} | 勝率: {(tdf['PnL']>0).mean():.1%} | PF: {tdf[tdf['PnL']>0]['PnL'].sum()/abs(tdf[tdf['PnL']<=0]['PnL'].sum() or 0.0001):.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            st.code("\n".join(rpt), language="text")
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
                for _, r in tdf.iterrows():
                    log.append(f"{r['Entry'].strftime('%Y-%m-%d %H:%M')} | PnL: {r['PnL']:+.2%} | {r['Pattern']} | {r['Reason']}")
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(log), language="text")
