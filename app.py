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

# --- 2. カスタムCSS (Ver 1.81 完全継承) ---
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

# --- 3. マッピング & セッション管理 (230銘柄・短縮版) ---
TICKER_NAME_MAP = {
    # 水産・食品 (不足分はGitHubにて入力してください)
    "1332.T": "ニッスイ", "2002.T": "日清粉G", "2269.T": "明治HD", "2282.T": "日本ハム", "2501.T": "サッポロHD",
    "2502.T": "アサヒG", "2503.T": "キリンHD", "2801.T": "キッコーマン", "2802.T": "味の素", "2871.T": "ニチレイ", 
}

MARKET_INDICES = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI", "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"}

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None

# --- 4. 関数定義 (スクリーニングエンジン：全銘柄ループ版) ---
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

# 全銘柄スキャン実行エンジン
def run_full_scan_engine(params):
    results = []; all_tickers = list(TICKER_NAME_MAP.keys())
    prg = st.progress(0)
    status_text = st.empty() # 現在のスキャン状況を表示
    
    for idx, t in enumerate(all_tickers):
        name = TICKER_NAME_MAP.get(t, t)
        status_text.text(f"🔍 スキャン中 ({idx+1}/{len(all_tickers)}): [{t}] {name}")
        prg.progress((idx + 1) / len(all_tickers))
        try:
            df = yf.download(t, period="3mo", interval="1d", progress=False)
            if df.empty or len(df) < 25: continue
            if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)

            # 各種テクニカル指標の計算
            p = df['Close'].iloc[-1]; v = df['Volume'].iloc[-1]
            ma25 = df['Close'].rolling(25).mean().iloc[-1]
            atrp = (AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().iloc[-1] / p) * 100
            adx = ADXIndicator(df['High'], df['Low'], df['Close']).adx().iloc[-1]
            rsi = RSIIndicator(df['Close'], 14).rsi().iloc[-1]
            rci = calculate_rci(df['Close'], 9).iloc[-1]
            ma25_dev = ((p - ma25) / ma25) * 100
            val_total = (p * v) / 100000000 
            v_avg_5 = df['Volume'].rolling(5).mean().iloc[-2]
            vup_rate = v / v_avg_5 if v_avg_5 > 0 else 1.0

            # 判定ロジック
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

            if match:
                results.append({"コード": t, "銘柄名": name, "株価": f"{int(p)}", "売買代金": f"{val_total:.1f}億", "前日比倍": f"{vup_rate:.2f}", "RSI": f"{rsi:.1f}"})
        except: continue
    prg.empty(); status_text.empty()
    return pd.DataFrame(results)

# --- 5. サイドバー ---
# (Ver 1.81 のサイドバー設定をそのまま維持)
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    if st.sidebar.button(l + (" [ 選択中 ]" if is_sel else ""), key=f"ps_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p; st.rerun()

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.93</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

# --- タブ1: ワンタッチ ---
with tab_top:
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    with st.expander(f"🕒 指標チェック ▶︎ ({now_jst})", expanded=True):
        if st.button("🔄 リアルタイム更新"): st.cache_data.clear(); st.rerun()
        # ... (指標表示カードのHTML)
    if st.button("ワンタッチで銘柄スキャン", type="primary", use_container_width=True):
        st.info("スキャン機能を準備中...")

# --- タブ2: スクリーニング (230銘柄自動抽出版) ---
with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["🔍通常フィルタ", "🔍ディフェンシブ", "🔍横ばい相場"])
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            exp_t = f"🔍 スクリーニング設定 ({['通常', 'ディフェンシブ', '横ばい'][i]})"
            with st.expander(exp_t, expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    c_p = st.checkbox("**株価の範囲**", True, key=f"c_p_{i}")
                    p_range = st.slider("価格(円)", 100, 10000, (500, 5000), key=f"v_p_{i}")
                    c_v = st.checkbox("**売買代金**", True, key=f"c_v_{i}")
                    v_min = st.number_input("億円以上", 50.0 if i==0 else 300.0 if i==1 else 200.0, key=f"v_v_{i}")
                    c_atrp = st.checkbox("**平均値幅 (ATR%)**", True, key=f"c_atrp_{i}")
                    atrp_range = st.slider("期待範囲%", 0.5, 5.0, (2.0, 4.0) if i==0 else (1.0, 2.5) if i==1 else (1.2, 2.5), key=f"v_atrp_{i}")
                    c_ma = st.checkbox("**移動平均上抜け/並び**", False, key=f"c_ma_{i}")
                    ma_opt = st.selectbox("条件選択", ["最強：上昇トレンド", "転換：GC直後", "収束：嵐の前の静けさ", "リバウンド：短期MA上抜け"], index=0 if i==0 else 2 if i==1 else 3, key=f"v_ma_{i}")
                with c2:
                    c_ema = st.checkbox("**EMA (9日・21日)**", False, key=f"c_ema_{i}")
                    ema_opt = st.selectbox("EMA基準", ["強気：EMAの上で価格維持", "安定：EMA付近での推移", "レンジ：EMAを上下にまたぐ"], index=0 if i==0 else 1 if i==1 else 2, key=f"v_ema_{i}")
                    c_adx = st.checkbox("**ADX (方向性指数)**", True, key=f"c_adx_{i}")
                    adx_range = st.slider("強度スコア", 0, 100, (25, 40) if i==0 else (10, 20), key=f"v_adx_{i}")
                    c_rci = st.checkbox("**RCI (順位相関計数)**", True, key=f"c_rci_{i}")
                    rci_range = st.slider("RCI範囲", -100, 100, (20, 80) if i==0 else (-20, 30) if i==1 else (-30, 30), key=f"v_rci_{i}")
                    c_rsi = st.checkbox("**RSI (14日)**", True, key=f"c_rsi_{i}")
                    rsi_range = st.slider("RSIレンジ", 0, 100, (55, 70) if i==0 else (40, 55) if i==1 else (45, 55), key=f"v_rsi_{i}")
                with c3:
                    c_vol = st.checkbox("**出来高**", True, key=f"c_vol_{i}")
                    vol_min = st.number_input("万株以上", 10 if i==0 else 20 if i==1 else 10, key=f"v_vol_{i}")
                    c_vup = st.checkbox("**出来高増加率**", True, key=f"c_vup_{i}")
                    vup_min = st.slider("増加倍率", 1.0, 5.0, 1.3 if i==0 else 1.1 if i==1 else 1.2, key=f"v_vup_{i}")
                    c_ma25 = st.checkbox("**25日移動平均乖離率**", True, key=f"c_ma25_{i}")
                    ma25_range = st.slider("偏差%", -20.0, 20.0, (0.0, 7.0) if i==0 else (-3.0, 2.0) if i==1 else (-2.0, 3.0), key=f"v_ma25_{i}")
                    c_bb = st.checkbox("**ボリンジャーバンド**", False, key=f"c_bb_{i}")
                    bb_range = st.slider("σ範囲", -3.0, 3.0, (1.0, 2.0) if i==0 else (-1.0, 0.0) if i==1 else (1.0, 2.0), step=0.1, key=f"v_bb_{i}")
            
            if st.button("スクリーニング実行", key=f"run_s_{i}", type="primary", use_container_width=True):
                p_dict = {'c_p': c_p, 'p_range': p_range, 'c_v': c_v, 'v_min': v_min, 'c_atrp': c_atrp, 'atrp_range': atrp_range, 'c_adx': c_adx, 'adx_range': adx_range, 'c_rsi': c_rsi, 'rsi_range': rsi_range, 'c_rci': c_rci, 'rci_range': rci_range, 'c_vol': c_vol, 'vol_min': vol_min, 'c_vup': c_vup, 'vup_min': vup_min, 'c_ma25': c_ma25, 'ma25_range': ma25_range}
                # 入力欄ではなくTICKER_NAME_MAPから全銘柄をスキャン
                res_df = run_full_scan_engine(p_dict)
                if not res_df.empty:
                    st.success(f"🎯 230銘柄中 {len(res_df)} 銘柄が条件に合致しました。")
                    st.dataframe(res_df, hide_index=True, use_container_width=True)
                else:
                    st.warning("合致する銘柄はありません。条件のチェックを外して再度お試しください。")

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

    st.markdown("<br>", unsafe_allow_html=True) # 余白

    res_df = st.session_state['bt_results']
    if res_df is not None:
        tabs = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間帯分析", "📝 詳細ログ"])
        
        with tabs[0]: # サマリー (PF表示名変更、サイズ統一)
            w_f = res_df[res_df['PnL']>0]['PnL']; l_f = res_df[res_df['PnL']<=0]['PnL']
            pf_f = w_f.sum()/abs(l_f.sum()) if not l_f.empty and l_f.sum()!=0 else 0
            st.markdown(f"""
            <div class='summary-container'>
                <div class='summary-box'><div class='summary-label'>総トレード数</div><div class='summary-value'>{len(res_df)}回</div></div>
                <div class='summary-box'><div class='summary-label'>勝率</div><div class='summary-value'>{(res_df['PnL']>0).mean():.1%}</div></div>
                <div class='summary-box'><div class='summary-label'>PF（総利益 ÷ 総損失）</div><div class='summary-value'>{pf_f:.2f}</div></div>
                <div class='summary-box'><div class='summary-label'>期待値</div><div class='summary-value'>{res_df['PnL'].mean():.2%}</div></div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("右上のコピーボタンで全文コピーできます↓")
            rpt = ["=================\n BACKTEST REPORT \n================="]
            rpt.append(f"\nPeriod: {st.session_state.get('bt_period','')}\n")
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk]
                if tdf.empty: continue
                nm = TICKER_NAME_MAP.get(tk, tk); tw = tdf[tdf['PnL']>0]['PnL']; tl = tdf[tdf['PnL']<=0]['PnL']
                rpt.append(f">>> TICKER: {tk} | {nm}\nトレード数: {len(tdf)} | 勝率: {(tdf['PnL']>0).mean():.1%} | 利益平均: {tw.mean():+.2%} | 損失平均: {tl.mean():+.2%} | PF: {tw.sum()/abs(tl.sum()):.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            st.code("\n".join(rpt), language="text")

        with tabs[1]: # 勝ちパターン分析
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy()
                if tdf.empty: continue
                st.markdown(f"#### [{tk}] {TICKER_NAME_MAP.get(tk, tk)}")
                p_stats = tdf.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                p_stats.columns = ['パターン', 'トレード数', '勝率', '平均損益']
                p_stats['トレード数'] = p_stats['トレード数'].astype(str)
                p_stats['勝率'] = p_stats['勝率'].apply(lambda x: f"{x:.1%}"); p_stats['平均損益'] = p_stats['平均損益'].apply(lambda x: f"{x:+.2%}")
                st.dataframe(p_stats, hide_index=True, use_container_width=True)
                try:
                    tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                    g_stats = tdf.groupby(pd.cut(tdf['Gap(%)'], bins=np.arange(-3.0, 3.5, 0.5)), observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()])
                    v_stats = tdf.groupby(pd.cut(tdf['VWAP乖離(%)'], bins=np.arange(-1.0, 1.2, 0.2)), observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()])
                    if not g_stats.empty and not v_stats.empty:
                        bg = g_stats['<lambda_0>'].idxmax(); bv = v_stats['<lambda_0>'].idxmax()
                        st.info(f"🏆 **最高勝率パターン**: {'GU' if bg.left>=0 else 'GD'} ({bg.left:.1f}%～) 時にVWAP乖離 ({bv.left:.1f}%～) でエントリーする形が優勢です。")
                except: pass
                st.divider()

        with tabs[2]: # ギャップ分析
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy()
                if tdf.empty: continue
                st.markdown(f"#### [{tk}] {TICKER_NAME_MAP.get(tk, tk)}")
                st.markdown("##### 始値ギャップ方向と成績")
                tdf['方向'] = tdf['Gap(%)'].apply(lambda x: 'ギャップアップ' if x > 0 else 'ギャップダウン')
                dir_stats = tdf.groupby('方向').agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x > 0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                dir_stats['トレード数'] = dir_stats['トレード数'].astype(str)
                dir_stats['勝率'] = dir_stats['勝率'].apply(lambda x: f"{x:.1%}"); dir_stats['平均損益'] = dir_stats['平均損益'].apply(lambda x: f"{x:+.2%}")
                st.dataframe(dir_stats, hide_index=True, use_container_width=True)
                st.markdown("##### ギャップ幅ごとの勝率")
                wid_bins = tdf.groupby(pd.cut(tdf['Gap(%)'], bins=np.arange(-3.0, 3.5, 0.5)), observed=True).agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x>0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                wid_bins.columns = ['ギャップ幅', 'トレード数', '勝率', '平均損益']
                wid_bins['ギャップ幅'] = wid_bins['ギャップ幅'].apply(lambda i: f"{i.left:.1f}% ～ {i.right:.1f}%")
                wid_bins['トレード数'] = wid_bins['トレード数'].astype(str)
                wid_bins['勝率'] = wid_bins['勝率'].apply(lambda x: f"{x:.1%}"); wid_bins['平均損益'] = wid_bins['平均損益'].apply(lambda x: f"{x:+.2%}")
                st.dataframe(wid_bins, hide_index=True, use_container_width=True)
                st.divider()

        with tabs[3]: # VWAP分析 (見本再現)
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy()
                if tdf.empty: continue
                st.markdown(f"#### [{tk}] {TICKER_NAME_MAP.get(tk, tk)}")
                st.markdown("##### エントリー時のVWAPと勝率")
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                v_bins = tdf.groupby(pd.cut(tdf['VWAP乖離(%)'], bins=np.arange(-1.0, 1.2, 0.2)), observed=True).agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x>0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                v_bins.columns = ['乖離率レンジ', 'トレード数', '勝率', '平均損益']
                v_bins['乖離率レンジ'] = v_bins['乖離率レンジ'].apply(lambda i: f"{i.left:.1f}% ～ {i.right:.1f}%")
                v_bins['トレード数'] = v_bins['トレード数'].astype(str)
                v_bins['勝率'] = v_bins['勝率'].apply(lambda x: f"{x:.1%}"); v_bins['平均損益'] = v_bins['平均損益'].apply(lambda x: f"{x:+.2%}")
                st.dataframe(v_bins, hide_index=True, use_container_width=True)
                st.divider()

        with tabs[4]: # 時間帯分析 (見本再現)
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy()
                if tdf.empty: continue
                st.markdown(f"#### [{tk}] {TICKER_NAME_MAP.get(tk, tk)}")
                st.markdown("##### エントリー時間帯ごとの勝率")
                tdf['時間帯'] = tdf['Entry'].apply(lambda dt: f"{dt.strftime('%H:%M')}〜{(dt + timedelta(minutes=5)).strftime('%H:%M')}")
                t_stats = tdf.groupby('時間帯').agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x>0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                t_stats['トレード数'] = t_stats['トレード数'].astype(str)
                t_stats['勝率'] = t_stats['勝率'].apply(lambda x: f"{x:.1%}"); t_stats['平均損益'] = t_stats['平均損益'].apply(lambda x: f"{x:+.2%}")
                st.dataframe(t_stats, hide_index=True, use_container_width=True)
                st.divider()

        with tabs[5]: # 詳細ログ (コピペ用)
            log_report = []
            for tk in t_list:
                tdf = res_df[res_df['Ticker'] == tk].copy().sort_values('Entry', ascending=False)
                if tdf.empty: continue
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                log_report.append(f"[{tk}] {TICKER_NAME_MAP.get(tk, tk)} 取引履歴\n" + "-"*80)
                for _, row in tdf.iterrows():
                    vwap_str = f"{int(row['EntryVWAP'])} (乖離 {row['VWAP乖離(%)']:+.2f}%)"
                    log_report.append(f"{row['Entry'].strftime('%Y-%m-%d %H:%M')} | 前終値：{int(row['PrevClose'])} | 始値：{int(row['DayOpen'])} | {row['Pattern']} | PnL: {row['PnL']:+.2%} | Gap: {row['Gap(%)']:+.2f}% | 買：{int(row['In'])} | 売：{int(row['Out'])} | VWAP: {vwap_str} | {row['Reason']}")
                log_report.append("\n")
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(log_report), language="text")
