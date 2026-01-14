import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time
from const import TICKER_NAME_MAP

# --- ページ設定 ---
st.set_page_config(page_title="BACK TESTER", page_icon="image_10.png", layout="wide")
st.logo("image_11.png", icon_image="image_10.png")

# CSS (左揃え・テーブル調整)
st.markdown("""
    <style>
    @media (max-width: 640px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 10px !important; }
        [data-testid="column"] { flex: 0 0 45% !important; max-width: 45% !important; min-width: 45% !important; }
        [data-testid="stMetricLabel"] { font-size: 12px !important; }
        [data-testid="stMetricValue"] { font-size: 18px !important; }
    }

/* 見出し（###）のサイズを一括で小さくする */
    h3 {
        font-size: 1.4rem !important;
        font-weight: 600 !important;
        margin-top: 10px !important;
        margin-bottom: -5px !important;
    }
    
/* 見出し2（####）のサイズを一括で小さくする */
    h4 {
        font-size: 1.4rem !important;
        font-weight: 600 !important;
        margin-top: 10px !important;
    }
    
/* 小見出し（#####）のサイズを一括で小さくする */
    h5 {
        font-size: 1.2rem !important;
        font-weight: 500 !important;
        margin-top: 10px !important;
    }
    
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>BACK TESTER</h1>
        <div style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>DAY TRADING MANAGER｜ver 6.3</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
    <style>
    /* --- サイドバー専用の設定 (メイン画面には影響しません) --- */

    /* パラメーター設定 (header) のサイズ調整 */
    [data-testid="stSidebar"] h2 {
        font-size: 1.2rem !important;
        font-weight: 700 !important;
    }

    /* ⏰ 時間設定 / エントリー条件 / 決済ルール (subheader) */
    [data-testid="stSidebar"] h3 {
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        margin-top: 15px !important;
    }

    /* 説明テキスト */
    [data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.9rem !important;
    }

    /* チェックボックスのラベル (VWAPより上でエントリーなど) */
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 基本関数 ---
def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

# データ取得（5分足）
@st.cache_data(ttl=600)
def fetch_intraday(ticker, start, end):
    try:
        df = yf.download(ticker, start=start, end=datetime.now(), interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
        return df
    except: return pd.DataFrame()

# ATR算出ロジックを含む関数
@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    p_map, o_map, a_map = {}, {}, {}
    try:
        d_start = start - timedelta(days=60)
        df = yf.download(ticker, start=d_start, end=datetime.now(), interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return p_map, o_map, a_map
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_prev = tr.rolling(window=14).mean().shift(1)
        p_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}
        o_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        a_map = {d.strftime('%Y-%m-%d'): a for d, a in zip(df.index, atr_prev) if pd.notna(a)}
        return p_map, o_map, a_map
    except: return p_map, o_map, a_map

# 銘柄名取得（辞書優先）
@st.cache_data(ttl=86400)
def get_ticker_name(ticker):
    return TICKER_NAME_MAP.get(ticker, ticker)

# --- シミュレーション・コアロジック (個別・ランキング共通) ---
def run_ticker_simulation(ticker, df, pc_map, co_map, a_map, params):
    trades = []
    if df.empty: return trades
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
    
    df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
    df['RSI14'] = RSIIndicator(close=df['Close'], window=14).rsi()
    df['RSI14_P'] = df['RSI14'].shift(1)
    macd = MACD(close=df['Close'])
    df['MH'] = macd.macd_diff(); df['MH_P'] = df['MH'].shift(1)
    
    unique_dates = np.unique(df.index.date)
    for d in unique_dates:
        day = df[df.index.date == d].copy().between_time('09:00', '15:00')
        if day.empty: continue
        day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum().replace(0, np.nan)
        date_str = d.strftime('%Y-%m-%d')
        pc = pc_map.get(date_str); do = co_map.get(date_str)
        if pc is None or do is None: continue
        gap_v = (do - pc) / pc
        
        in_pos = False; entry_p = 0; stop_p = 0; t_high = 0; t_active = False; sl_rec = 0
        for ts, row in day.iterrows():
            if not in_pos:
                if params['start_t'] <= ts.time() <= params['end_t'] and params['g_min'] <= gap_v <= params['g_max']:
                    c_vwap = (row['Close'] > row['VWAP']) if params['u_vwap'] else True
                    c_ema = (row['Close'] > row['EMA5']) if params['u_ema'] else True
                    c_rsi = (row['RSI14'] > 45 and row['RSI14'] > row['RSI14_P']) if params['u_rsi'] else True
                    c_macd = (row['MH'] > row['MH_P']) if params['u_macd'] else True
                    
                    if c_vwap and c_ema and c_rsi and c_macd:
                        entry_p = row['Close'] * 1.0003; in_pos = True; entry_t = ts; entry_vwap = row['VWAP']
                        # ATR損切り計算
                        if params['u_atr']:
                            av = a_map.get(date_str)
                            sl_rec = max(params['atr_min'], (av/entry_p)*params['atr_mul']) if av and entry_p>0 else abs(params['sl_fix'])
                        else: sl_rec = abs(params['sl_fix'])
                        stop_p = entry_p * (1 - sl_rec); t_high = row['High']; t_active = False
            else:
                t_high = max(t_high, row['High'])
                if not t_active and t_high >= entry_p * (1 + params['ts_start']): t_active = True
                ex_p = None; rsn = ""
                if t_active and row['Low'] <= t_high * (1 - params['ts_width']):
                    ex_p = t_high * (1 - params['ts_width']) * 0.9997; rsn = "トレーリング"
                elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997; rsn = "損切り"
                elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997; rsn = "時間切れ"
                
                if ex_p:
                    trades.append({'Ticker': ticker, 'Entry': entry_t, 'Exit': ts, 'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p, 'Reason': rsn, 'Pattern': get_trade_pattern(row, gap_v), 'Gap(%)': gap_v*100, 'EntryVWAP': entry_vwap, 'PrevClose': pc, 'DayOpen': do, 'SL設定(%)': sl_rec*100})
                    in_pos = False; break
    return trades

# --- UI サイドバー ---
st.sidebar.header("⚙️ パラメーター設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
s_t = st.sidebar.time_input("開始時間", time(9, 0), step=300)
e_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)
st.sidebar.write("")
st.sidebar.subheader("📉 エントリー条件")
u_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
u_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
u_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
u_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)
st.sidebar.divider()

g_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
g_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100

st.sidebar.subheader("💰 決済ルール")
ts_s = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
ts_w = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
sl_f = st.sidebar.number_input("損切り (%) ※ATR非使用時", -5.0, -0.1, -0.5, 0.05) / 100
st.sidebar.divider()

st.sidebar.subheader("📉 **動的損切り設定 (ATR)**")
u_atr = st.sidebar.checkbox("ATR損切りを使用", value=True)
a_mul = st.sidebar.number_input("ATR倍率", 0.5, 5.0, 1.5, 0.1)
a_min = st.sidebar.number_input("最低損切り (%)", 0.1, 5.0, 0.5, 0.1) / 100

# --- 🔍 ランキング検索条件 (サイドバー下部) ---
st.sidebar.divider()
st.sidebar.subheader("🔍 ランキング検索条件")
p_range = st.sidebar.slider("株価範囲 (円)", 0, 20000, (500, 5000), 500)
p_min, p_max = p_range

# ★サイドバーのボタン
if st.sidebar.button("ランキング生成", type="primary", use_container_width=True, key="side_rank_btn"):
    st.session_state['trigger_rank_scan'] = True
    st.rerun()

# パラメータ辞書の更新 (株価フィルター用の値を追加)
params = {
    'days': days_back, 'start_t': s_t, 'end_t': e_t, 'u_vwap': u_vwap, 'u_ema': u_ema, 'u_rsi': u_rsi, 'u_macd': u_macd,
    'g_min': g_min, 'g_max': g_max, 'ts_start': ts_s, 'ts_width': ts_w, 'sl_fix': sl_f, 'u_atr': u_atr, 'atr_mul': a_mul, 'atr_min': a_min,
    'p_min': p_min, 'p_max': p_max # ★株価フィルター用
}

# --- メインロジック ---
ticker_input = st.text_input("銘柄コード (カンマ区切り)", "8267.T")
tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]
if st.button("バックテスト実行", type="primary", key="main_btn"):
    end_date = datetime.now(); start_date = end_date - timedelta(days=days_back); all_trades = []
    pb = st.progress(0); st_text = st.empty(); t_names = {}
    for i, t in enumerate(tickers):
        st_text.text(f"Testing {t}..."); pb.progress((i+1)/len(tickers))
        df = fetch_intraday(t, start_date, end_date)
        p_map, o_map, a_map = fetch_daily_stats_maps(t, start_date)
        all_trades.extend(run_ticker_simulation(t, df, p_map, o_map, a_map, params))
        t_names[t] = get_ticker_name(t)
    pb.empty(); st_text.empty()
    st.session_state['res_df'] = pd.DataFrame(all_trades)
    st.session_state['start_date'] = start_date
    st.session_state['end_date'] = end_date # ★修正：end_dateを保存
    st.session_state['t_names'] = t_names

    # --- 結果表示タブ ---
# 個別テスト結果がある、またはランキング結果がある、またはスキャンが指示された場合に表示
if 'res_df' in st.session_state or 'last_rank_df' in st.session_state or st.session_state.get('trigger_rank_scan', False):
    # res_df がない場合は空の DataFrame を作成してエラーを回避
    res_df = st.session_state.get('res_df', pd.DataFrame())
    start_date = st.session_state.get('start_date', datetime.now() - timedelta(days=days_back))
    end_date = st.session_state.get('end_date', datetime.now())
    ticker_names = st.session_state.get('t_names', {})

    # タブの定義 (v5.9の5つ + ランキング)
    tab1, tab2, tab3, tab4, tab5, tab6, tab_rank = st.tabs(["📊 サマリー", "🏅 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ", "🏆 ランキング"])

    with tab1: # サマリー
        if not res_df.empty and 'PnL' in res_df.columns:
            
            # 1. 全体集計
            count_all = len(res_df)
            wins_all = res_df[res_df['PnL'] > 0]
            losses_all = res_df[res_df['PnL'] <= 0]
            win_rate_all = len(wins_all) / count_all if count_all > 0 else 0
            
            gross_win = wins_all['PnL'].sum()
            gross_loss = abs(losses_all['PnL'].sum())
            pf_all = gross_win / gross_loss if gross_loss > 0 else float('inf')
            expectancy_all = res_df['PnL'].mean()

            # 2. メトリクス表示
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
        
            # 3. テキストレポート生成（修正箇所）
            report = []
            report.append("=================\n BACKTEST REPORT \n=================")
            # セッション状態から日付を取得、なければデフォルトを表示
            s_date = st.session_state.get('start_date', datetime.now() - timedelta(days=days_back))
            e_date = st.session_state.get('end_date', datetime.now())
            report.append(f"\nPeriod: {s_date.strftime('%Y-%m-%d')} - {e_date.strftime('%Y-%m-%d')}\n")
            
            if 'Ticker' in res_df.columns:
                for t in res_df['Ticker'].unique():
                    tdf = res_df[res_df['Ticker'] == t]
                    if tdf.empty: continue
                    
                    # 各項目の算出
                    t_wins = tdf[tdf['PnL'] > 0]
                    t_losses = tdf[tdf['PnL'] <= 0]
                    t_cnt = len(tdf)
                    t_wr = len(t_wins) / t_cnt if t_cnt > 0 else 0
                    
                    # 利益平均・損失平均の算出
                    avg_win = t_wins['PnL'].mean() if not t_wins.empty else 0
                    avg_loss = t_losses['PnL'].mean() if not t_losses.empty else 0
                    
                    # PFの算出
                    t_pf = t_wins['PnL'].sum() / abs(t_losses['PnL'].sum()) if not t_losses.empty and t_losses['PnL'].sum() != 0 else float('inf')
                    
                    # 期待値の算出
                    t_exp = tdf['PnL'].mean()
                    
                    t_name = ticker_names.get(t, t)
                    report.append(f">>> TICKER: {t} | {t_name}")
                    # 指定された順番でフォーマット
                    report.append(f"トレード数: {t_cnt} | 勝率: {t_wr:.1%} | 利益平均: {avg_win:+.2%} | 損失平均: {avg_loss:+.2%} | PF: {t_pf:.2f} | 期待値: {t_exp:+.2%}\n")
            
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(report), language="text")

            # ★追加：リセットボタン
            if st.button("♻️ バックテスト結果をクリア", key="reset_t1"):
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()
                
        else:
            st.info("""
            **💡 個別バックテストの結果はありません。**

            以下の手順で操作してください：
            1. 画面上部の入力欄に銘柄コードを入れる
            2. バックテスト実行ボタンを押す
            
            ランキング結果トップ20は『🏆 ランキング』から確認できます
            """)
            
    with tab2: # 🏅 勝ちパターン
        st.markdown("### 🏅 勝ちパターン分析")
        st.caption("チャートパターン別の成績分析と、ベストなエントリー条件を言語化して勝ちパターンを抽出します。")
        
        # --- データの存在チェック ---
        # res_dfにデータがあり、かつ 'Ticker' 列が存在する場合のみ実行
        if not res_df.empty and 'Ticker' in res_df.columns:
            # 安全のため、実際に結果が存在する銘柄コードのみを抽出してループ
            unique_res_tickers = res_df['Ticker'].unique()

            for t in unique_res_tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                
                t_name = ticker_names.get(t, t)
                st.markdown(f"#### [{t}] {t_name}")
                
                # パターン別統計
                pat_stats = tdf.groupby('Pattern', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                pat_stats.columns = ['パターン', 'トレード数', '勝率', '平均損益']
                pat_stats['勝率'] = pat_stats['勝率'].apply(lambda x: f"{x:.1%}")
                pat_stats['平均損益'] = pat_stats['平均損益'].apply(lambda x: f"{x:+.2%}")
                pat_stats['トレード数'] = pat_stats['トレード数'].astype(str)
                st.dataframe(pat_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                
                # ベストパターンの抽出 (try文で予期せぬ計算エラーを保護)
                try:
                    # 1. ギャップ分析
                    min_g = np.floor(tdf['Gap(%)'].min()); max_g = np.ceil(tdf['Gap(%)'].max())
                    if np.isnan(min_g): min_g=-3.0; max_g=1.0
                    bins_g = np.arange(min_g, max_g+0.5, 0.5)
                    tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=bins_g)
                    gap_stats = tdf.groupby('GapRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                    gap_valid = gap_stats[gap_stats['count']>=1] # 閾値を1以上に緩和
                    best_g = gap_valid.loc[gap_valid['<lambda_0>'].idxmax()]
                    
                    # 2. VWAP分析
                    tdf['VWAP_Diff'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                    min_v = np.floor(tdf['VWAP_Diff'].min()*2)/2; max_v = np.ceil(tdf['VWAP_Diff'].max()*2)/2
                    if np.isnan(min_v): min_v=-1.0; max_v=1.0
                    bins_v = np.arange(min_v, max_v+0.2, 0.2)
                    tdf['VwapRange'] = pd.cut(tdf['VWAP_Diff'], bins=bins_v)
                    vwap_stats = tdf.groupby('VwapRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                    vwap_valid = vwap_stats[vwap_stats['count']>=1]
                    best_v = vwap_valid.loc[vwap_valid['<lambda_0>'].idxmax()]
                    
                    # 3. 時間分析
                    def get_time_range(dt): return f"{dt.strftime('%H:%M')}～{(dt + timedelta(minutes=5)).strftime('%H:%M')}"
                    tdf['TimeRange'] = tdf['Entry'].apply(get_time_range)
                    time_stats = tdf.groupby('TimeRange')['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                    time_valid = time_stats[time_stats['count']>=1]
                    best_t = time_valid.loc[time_valid['<lambda_0>'].idxmax()]
                    
                    gap_txt = "ギャップアップ" if best_g['GapRange'].left >= 0 else "ギャップダウン"
                    st.info(f"**🏆 最高勝率パターン**\n\n"
                            f"最も勝率が高かったのは、**{gap_txt} ({best_g['GapRange'].left:.1f}% ～ {best_g['GapRange'].right:.1f}%)** スタートで、"
                            f"VWAPから **{best_v['VwapRange'].left:.1f}% ～ {best_v['VwapRange'].right:.1f}%** の位置にある時、"
                            f"**{best_t['TimeRange']}** にエントリーするパターンです。\n\n"
                            f"(GAP勝率: {best_g['<lambda_0>']:.1%} / VWAP勝率: {best_v['<lambda_0>']:.1%} / 時間勝率: {best_t['<lambda_0>']:.1%})")
                except Exception:
                    st.warning(f"[{t}] パターン分析を生成するためのデータが不足しています。")
                
                st.divider()

            # ★追加：リセットボタン
            if st.button("♻️ バックテスト結果をクリア", key="reset_t2"): 
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()
                
        else:
            st.info("""
            **💡 個別バックテストの結果はありません。**

            以下の手順で操作してください：
            1. 画面上部の入力欄に銘柄コードを入れる
            2. バックテスト実行ボタンを押す
            
            ランキング結果トップ20は『🏆 ランキング』から確認できます
            """)
            
    with tab3: # 📉 ギャップ分析
        # --- データの存在チェック ---
        # res_dfにデータがあり、かつ 'Ticker' 列が存在する場合のみ実行
        if not res_df.empty and 'Ticker' in res_df.columns:
            # 安全のため、実際に結果が存在する銘柄コードのみを抽出してループ
            unique_res_tickers = res_df['Ticker'].unique()

            for t in unique_res_tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                
                t_name = ticker_names.get(t, t)
                st.markdown(f"### [{t}] {t_name}")
                
                # --- 1. 始値ギャップ方向の分析 ---
                st.markdown("##### 始値ギャップ方向と成績")
                tdf['GapDir'] = tdf['Gap(%)'].apply(lambda x: 'ギャップアップ' if x > 0 else ('ギャップダウン' if x < 0 else 'フラット'))
                
                # 統計集計
                gap_dir_stats = tdf.groupby('GapDir', observed=True).agg(
                    Count=('PnL', 'count'), 
                    WinRate=('PnL', lambda x: (x > 0).mean()), 
                    AvgPnL=('PnL', 'mean')
                ).reset_index()
                
                # 表示用に整形
                gap_dir_disp = gap_dir_stats.copy()
                gap_dir_disp['WinRate'] = gap_dir_disp['WinRate'].apply(lambda x: f"{x:.1%}")
                gap_dir_disp['AvgPnL'] = gap_dir_disp['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                gap_dir_disp['Count'] = gap_dir_disp['Count'].astype(str)
                gap_dir_disp.columns = ['方向', 'トレード数', '勝率', '平均損益']
                
                # 表を表示
                st.dataframe(gap_dir_disp.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)

                # --- 2. ギャップ幅ごとの分析 ---
                st.markdown("##### ギャップ幅ごとの勝率")
                try:
                    min_g = np.floor(tdf['Gap(%)'].min()); max_g = np.ceil(tdf['Gap(%)'].max())
                    if np.isnan(min_g): min_g = -3.0; max_g = 1.0
                    bins_g = np.arange(min_g, max_g + 0.5, 0.5)
                    tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=bins_g)
                    
                    gap_range_stats = tdf.groupby('GapRange', observed=True).agg(
                        Count=('PnL', 'count'), 
                        WinRate=('PnL', lambda x: (x > 0).mean()), 
                        AvgPnL=('PnL', 'mean')
                    ).reset_index()
                    
                    def format_interval(i): return f"{i.left:.1f}% ～ {i.right:.1f}%"
                    gap_range_stats['RangeLabel'] = gap_range_stats['GapRange'].apply(format_interval)
                    
                    disp_gap = gap_range_stats[['RangeLabel', 'Count', 'WinRate', 'AvgPnL']].copy()
                    disp_gap['WinRate'] = disp_gap['WinRate'].apply(lambda x: f"{x:.1%}")
                    disp_gap['AvgPnL'] = disp_gap['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                    disp_gap['Count'] = disp_gap['Count'].astype(str)
                    disp_gap.columns = ['ギャップ幅', 'トレード数', '勝率', '平均損益']
                    
                    st.dataframe(disp_gap.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                except Exception:
                    st.warning(f"[{t}] ギャップ幅の分析を生成するためのデータが不足しています。")
                
                st.divider()

            # ★追加：リセットボタン
            if st.button("♻️ バックテスト結果をクリア", key="reset_t3"): 
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()
                
        else:
            st.info("""
            **💡 個別バックテストの結果はありません。**

            以下の手順で操作してください：
            1. 画面上部の入力欄に銘柄コードを入れる
            2. バックテスト実行ボタンを押す
            
            ランキング結果トップ20は『🏆 ランキング』から確認できます
            """)
                
    with tab4: # 🧐 VWAP分析
        # --- データの存在チェック ---
        # res_dfにデータがあり、かつ 'Ticker' 列が存在する場合のみ実行
        if not res_df.empty and 'Ticker' in res_df.columns:
            # 安全のため、実際に結果が存在する銘柄コードのみを抽出してループ
            unique_res_tickers = res_df['Ticker'].unique()
            
            for t in unique_res_tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                
                t_name = ticker_names.get(t, t)
                st.markdown(f"### [{t}] {t_name}")
                st.markdown("##### エントリー時のVWAPと勝率")
                
                # --- VWAP乖離の計算 ---
                # EntryVWAPが0やNaNでないことを確認して計算
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                
                try:
                    # レンジ（bin）の作成
                    min_dev = np.floor(tdf['VWAP乖離(%)'].min() * 2) / 2
                    max_dev = np.ceil(tdf['VWAP乖離(%)'].max() * 2) / 2
                    if np.isnan(min_dev): min_dev = -1.0; max_dev = 1.0
                    
                    bins = np.arange(min_dev, max_dev + 0.2, 0.2)
                    tdf['Range'] = pd.cut(tdf['VWAP乖離(%)'], bins=bins)
                    
                    # 統計集計（Named Aggregation形式）
                    vwap_stats = tdf.groupby('Range', observed=True).agg(
                        Count=('PnL', 'count'), 
                        WinRate=('PnL', lambda x: (x > 0).mean()), 
                        AvgPnL=('PnL', 'mean')
                    ).reset_index()
                    
                    # ラベルの整形
                    def format_vwap_interval(i): return f"{i.left:.1f}% ～ {i.right:.1f}%"
                    vwap_stats['RangeLabel'] = vwap_stats['Range'].apply(format_vwap_interval)
                    
                    # 表示用データフレームの構築
                    display_stats = vwap_stats[['RangeLabel', 'Count', 'WinRate', 'AvgPnL']].copy()
                    display_stats['WinRate'] = display_stats['WinRate'].apply(lambda x: f"{x:.1%}")
                    display_stats['AvgPnL'] = display_stats['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                    display_stats['Count'] = display_stats['Count'].astype(str)
                    display_stats.columns = ['乖離率レンジ', 'トレード数', '勝率', '平均損益']
                    
                    # 表の表示
                    st.dataframe(display_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                
                except Exception:
                    st.warning(f"[{t}] VWAP乖離分析を生成するためのデータが不足しています。")
                
                st.divider()
     
            # ★追加：リセットボタン
            if st.button("♻️ バックテスト結果をクリア", key="reset_t4"): 
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()        
        
        else:
            st.info("""
            **💡 個別バックテストの結果はありません。**

            以下の手順で操作してください：
            1. 画面上部の入力欄に銘柄コードを入れる
            2. バックテスト実行ボタンを押す
            
            ランキング結果トップ20は『🏆 ランキング』から確認できます
            """)
                
    with tab5: # 🕒 時間分析
        # --- データの存在チェック ---
        # res_dfにデータがあり、かつ 'Ticker' 列が存在する場合のみ実行
        if not res_df.empty and 'Ticker' in res_df.columns:
            # 安全のため、実際に結果が存在する銘柄コードのみを抽出してループ
            unique_res_tickers = res_df['Ticker'].unique()

            for t in unique_res_tickers:
                tdf = res_df[res_df['Ticker'] == t].copy()
                if tdf.empty: continue
                
                t_name = ticker_names.get(t, t)
                st.markdown(f"### [{t}] {t_name}")
                st.markdown("##### エントリー時間帯ごとの勝率")
                
                # エントリー時間帯の文字列作成
                def get_time_range(dt): 
                    return f"{dt.strftime('%H:%M')}～{(dt + timedelta(minutes=5)).strftime('%H:%M')}"
                
                tdf['TimeRange'] = tdf['Entry'].apply(get_time_range)
                
                # 時間帯ごとの集計
                try:
                    time_stats = tdf.groupby('TimeRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                    
                    # 表示用に整形
                    time_disp = time_stats.copy()
                    time_disp.columns = ['時間帯', 'count', 'win_rate', 'mean']
                    time_disp['WinRate'] = time_disp['win_rate'].apply(lambda x: f"{x:.1%}")
                    time_disp['AvgPnL'] = time_disp['mean'].apply(lambda x: f"{x:+.2%}")
                    time_disp['Count'] = time_disp['count'].astype(str)
                    
                    # 最終的な表示用カラム
                    final_disp = time_disp[['時間帯', 'Count', 'WinRate', 'AvgPnL']]
                    final_disp.columns = ['時間帯', 'トレード数', '勝率', '平均損益']
                    
                    st.dataframe(final_disp, hide_index=True, use_container_width=True)
                except Exception:
                    st.warning(f"[{t}] 時間分析を生成するためのデータが不足しています。")
                
                st.divider()

            # ★追加：リセットボタン
            if st.button("♻️ バックテスト結果をクリア", key="reset_t5"): 
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()        
        
        else:
            st.info("""
            **💡 個別バックテストの結果はありません。**

            以下の手順で操作してください：
            1. 画面上部の入力欄に銘柄コードを入れる
            2. バックテスト実行ボタンを押す
            
            ランキング結果トップ20は『🏆 ランキング』から確認できます
            """)
                
    with tab6: # 📝 詳細ログ
        st.markdown("### 📝 詳細取引ログ")
        
        # --- データの存在チェック ---
        if not res_df.empty and 'Ticker' in res_df.columns:
            # ★修正点1：リストの初期化（これがないとappendでエラーになります）
            log_report = []
            
            # 安全のため、実際に結果が存在する銘柄コードのみを抽出してループ
            unique_res_tickers = res_df['Ticker'].unique()

            for t in unique_res_tickers:
                # データの抽出とソート
                tdf = res_df[res_df['Ticker'] == t].copy().sort_values('Entry', ascending=False).reset_index(drop=True)
                if tdf.empty: continue
                
                # VWAP乖離の計算
                tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                t_name = ticker_names.get(t, t)
                
                log_report.append(f"[{t}] {t_name} 取引履歴")
                log_report.append("-" * 80)
                
                for i, row in tdf.iterrows():
                    entry_str = row['Entry'].strftime('%Y-%m-%d %H:%M')
                    if pd.notna(row['EntryVWAP']) and row['EntryVWAP'] != 0:
                        vwap_val = int(round(row['EntryVWAP']))
                        vwap_dev = f"{row['VWAP乖離(%)']:+.2f}%"
                        vwap_str = f"{vwap_val} (乖離 {vwap_dev})"
                    else:
                        vwap_str = "- (乖離 -)"
                    
                    # 買・売の金額を int() で切り捨て整形
                    line = (
                        f"{entry_str} | "
                        f"前終値：{int(row['PrevClose'])} | 始値：{int(row['DayOpen'])} | "
                        f"{row['Pattern']} | "
                        f"PnL: {row['PnL']:+.2%} | Gap: {row['Gap(%)']:+.2f}% | "
                        f"買：{int(row['In'])} | 売：{int(row['Out'])} | "
                        f"VWAP: {vwap_str} | "
                        f"{row['Reason']}"
                    )
                    log_report.append(line)
                log_report.append("\n")
            
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(log_report), language="text")

            # ★修正点2：リセットボタンを「表示コードの直後」に移動
            if st.button("♻️ バックテスト結果をクリア", key="reset_t6"): 
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()

        else:
            # データがない時の案内
            st.info("""
            **💡 個別バックテストの結果はありません。**

            以下の手順で操作してください：
            1. 画面上部の入力欄に銘柄コードを入れる
            2. バックテスト実行ボタンを押す
            
            ランキング結果トップ20は『🏆 ランキング』から確認できます
            """)

    with tab_rank:
        st.markdown("### 🏆 登録銘柄ランキング")        
        # st.caption の代わりに st.markdown (HTML) を使用して色とサイズを調整します
        st.markdown("""
            <p style="font-size: 0.85rem; color: #9c9d9f; margin-bottom: 1rem;">
                サイドバーの『ランキング生成』ボタンから実行してください。日経225＋αから上位20銘柄を抽出します。<br>
                『バックテスト結果をクリア』してからご利用ください。
            </p>
            """, unsafe_allow_html=True)
        
        # 進行状況を表示するエリア
        ranking_container = st.container()

        # サイドバーのボタンが押された（合図がある）場合にのみ実行
        if st.session_state.get('trigger_rank_scan', False):
            st.session_state['trigger_rank_scan'] = False # 合図をリセット
            rank_list = []
            all_tickers = list(TICKER_NAME_MAP.keys())
            
            with ranking_container:
                with st.status("🔍 全登録銘柄を分析中...", expanded=True) as status:
                    pb_r = st.progress(0)
                    for i, t in enumerate(all_tickers):
                        status.update(label=f"Scanning {i+1}/{len(all_tickers)}: {t}")
                        pb_r.progress((i+1)/len(all_tickers))
                        
                        # 1. データ取得と空チェック
                        df_r = fetch_intraday(t, start_date, end_date)
                        if df_r.empty: continue
                        
                        # 2. 株価範囲のフィルタリング
                        current_price = df_r['Close'].iloc[-1]
                        if not (p_min <= current_price <= p_max): continue

                        # 3. マップデータの取得
                        p_maps, o_maps, a_maps = fetch_daily_stats_maps(t, start_date)

                        # 4. 前日比（change_pct）の計算
                        change_pct = 0.0
                        try:
                            d_close = df_r['Close'].dropna()
                            if not d_close.empty:
                                last_p = d_close.iloc[-1]
                                # 最新足の日付をキーにして前日終値を取得
                                date_key = d_close.index[-1].strftime('%Y-%m-%d')
                                prev_p = p_maps.get(date_key)
                                if prev_p:
                                    change_pct = (last_p - prev_p) / prev_p
                        except:
                            pass

                        # 5. シミュレーション実行
                        t_trades = run_ticker_simulation(t, df_r, p_maps, o_maps, a_maps, params)
                        if t_trades:
                            tdf = pd.DataFrame(t_trades)
                            wins = tdf[tdf['PnL'] > 0]; losses = tdf[tdf['PnL'] <= 0]
                            rank_list.append({
                                '銘柄コード': t, '銘柄名': get_ticker_name(t), '前日比': change_pct,
                                '回数': len(tdf), '勝率': len(wins)/len(tdf), 
                                '利益平均': wins['PnL'].mean() if not wins.empty else 0,
                                '損失平均': losses['PnL'].mean() if not losses.empty else 0,
                                'PF': wins['PnL'].sum()/abs(losses['PnL'].sum()) if not losses.empty and losses['PnL'].sum()!=0 else 9.99,
                                '期待値': tdf['PnL'].mean()
                            })
                    status.update(label="✅ スキャン完了！", state="complete")

            if rank_list:
                st.session_state['last_rank_df'] = pd.DataFrame(rank_list).sort_values('期待値', ascending=False)
                st.rerun()
            
        # 結果の表示エリア
        if 'last_rank_df' in st.session_state:
            st.write("---")
            rdf = st.session_state['last_rank_df'].head(20)
            st.dataframe(
                rdf.style.format({
                    '前日比': '{:+.2%}', '勝率': '{:.1%}', '利益平均': '{:+.2%}', '損失平均': '{:+.2%}', '期待値': '{:+.2%}', 'PF': '{:.2f}'
                }),
                use_container_width=True, hide_index=True, height=735
            )
            # リセットボタン（これは残しておきます）
            if st.button("ランキング表示をクリア"):
                del st.session_state['last_rank_df']
                st.rerun()
