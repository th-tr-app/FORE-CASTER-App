import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time

# ★外部モジュールのインポート
from const import TICKER_NAME_MAP
import logic_core as core

# --- 1. ページ設定 ---
st.set_page_config(page_title="BACK TESTER 6.3", page_icon="image_10.png", layout="wide")
st.logo("image_11.png", icon_image="image_10.png")

# --- 2. カスタムCSS (デザイン維持) ---
st.markdown("""
    <style>
    h3 { font-size: 1.4rem !important; font-weight: 600 !important; margin-bottom: -5px !important; }
    h4 { font-size: 1.4rem !important; font-weight: 600 !important; }
    th, td { text-align: left !important; }
    [data-testid="stSidebar"] h3 { font-size: 1.2rem !important; font-weight: 700 !important; }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div style='margin-bottom: 20px;'>
        <h1 style='font-weight: 400; font-size: 46px; margin: 0; padding: 0;'>BACK TESTER</h1>
        <div style='font-weight: 300; font-size: 20px; margin: 0; padding: 0; color: #aaaaaa;'>DAY TRADING MANAGER｜ver 6.3 (Modular)</div>
    </div>
    """, unsafe_allow_html=True)

# --- 3. 内部用関数 ---
@st.cache_data(ttl=600)
def fetch_intraday(ticker, start, end):
    """5分足データの取得"""
    try:
        df = yf.download(ticker, start=start, end=end, interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
        return df
    except: return pd.DataFrame()

# --- 4. サイドバー設定 ---
st.sidebar.header("⚙️ パラメーター設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
s_t = st.sidebar.time_input("開始時間", time(9, 0), step=300)
e_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)

st.sidebar.subheader("📉 エントリー条件")
u_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
u_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
u_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
u_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)

g_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
g_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100

st.sidebar.subheader("💰 決済ルール")
ts_s = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
ts_w = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
sl_f = st.sidebar.number_input("損切り (%) ※ATR非使用時", -5.0, -0.1, -0.5, 0.05) / 100

st.sidebar.subheader("📉 **動的損切り設定 (ATR)**")
u_atr = st.sidebar.checkbox("ATR損切りを使用", value=True)
a_mul = st.sidebar.number_input("ATR倍率", 0.5, 5.0, 1.5, 0.1)
a_min = st.sidebar.number_input("最低損切り (%)", 0.1, 5.0, 0.5, 0.1) / 100

st.sidebar.divider()
st.sidebar.subheader("🏆 ランキング検索条件")
p_range = st.sidebar.slider("株価範囲 (円)", 0, 20000, (500, 5000), 500)
p_min, p_max = p_range

if st.sidebar.button("ランキング生成", type="primary", use_container_width=True, key="side_rank_btn"):
    st.session_state['trigger_rank_scan'] = True
    st.rerun()

params = {
    'days': days_back, 'start_t': s_t, 'end_t': e_t, 'u_vwap': u_vwap, 'u_ema': u_ema, 'u_rsi': u_rsi, 'u_macd': u_macd,
    'g_min': g_min, 'g_max': g_max, 'ts_start': ts_s, 'ts_width': ts_w, 'sl_fix': sl_f, 'u_atr': u_atr, 'atr_mul': a_mul, 'atr_min': a_min
}

# --- 5. メインロジック ---
ticker_input = st.text_input("銘柄コード (カンマ区切り)", "8267.T")
tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]

if st.button("バックテスト実行", type="primary"):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    all_trades = []
    t_names = {}
    
    pb = st.progress(0)
    st_text = st.empty()
    
    for i, t in enumerate(tickers):
        st_text.text(f"Testing {t}...")
        pb.progress((i+1)/len(tickers))
        
        # ★logic_core から関数を呼び出し
        df = fetch_intraday(t, start_date, end_date)
        p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
        all_trades.extend(core.run_ticker_simulation(t, df, p_map, o_map, a_map, params))
        t_names[t] = TICKER_NAME_MAP.get(t, t)
        
    st.session_state['res_df'] = pd.DataFrame(all_trades)
    st.session_state['t_names'] = t_names
    st.session_state['bt_period'] = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
    st.rerun()

# --- 6. 結果表示タブ ---
if 'res_df' in st.session_state or 'last_rank_df' in st.session_state or st.session_state.get('trigger_rank_scan', False):
    res_df = st.session_state.get('res_df', pd.DataFrame())
    ticker_names = st.session_state.get('t_names', {})

    tabs = st.tabs(["📊 サマリー", "🏅 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ", "🏆 ランキング"])

    with tabs[0]: # 📊 サマリー
        if not res_df.empty and 'PnL' in res_df.columns:
            # メトリクス計算
            wins = res_df[res_df['PnL'] > 0]
            losses = res_df[res_df['PnL'] <= 0]
            pf = wins['PnL'].sum() / abs(losses['PnL'].sum()) if not losses.empty and losses['PnL'].sum() != 0 else 0
            
            st.markdown(f"""
            <div style='display: flex; gap: 10px; margin-bottom: 15px;'>
                <div style='background:#262730; padding:15px; border-radius:8px; flex:1; text-align:center;'>
                    <div style='font-size:12px; color:#aaa;'>総トレード数</div><div style='font-size:24px; font-weight:bold;'>{len(res_df)}回</div>
                </div>
                <div style='background:#262730; padding:15px; border-radius:8px; flex:1; text-align:center;'>
                    <div style='font-size:12px; color:#aaa;'>勝率</div><div style='font-size:24px; font-weight:bold;'>{(len(wins)/len(res_df)):.1%}</div>
                </div>
                <div style='background:#262730; padding:15px; border-radius:8px; flex:1; text-align:center;'>
                    <div style='font-size:12px; color:#aaa;'>PF</div><div style='font-size:24px; font-weight:bold;'>{pf:.2f}</div>
                </div>
                <div style='background:#262730; padding:15px; border-radius:8px; flex:1; text-align:center;'>
                    <div style='font-size:12px; color:#aaa;'>期待値</div><div style='font-size:24px; font-weight:bold;'>{res_df['PnL'].mean():.2%}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            rpt = ["=================\n BACKTEST REPORT \n================="]
            rpt.append(f"Period: {st.session_state.get('bt_period','')}\n")
            for t in res_df['Ticker'].unique():
                tdf = res_df[res_df['Ticker'] == t]
                tw = tdf[tdf['PnL']>0]['PnL']; tl = tdf[tdf['PnL']<=0]['PnL']
                nm = ticker_names.get(t, t)
                rpt.append(f">>> TICKER: {t} | {nm}\nトレード数: {len(tdf)} | 勝率: {(len(tw)/len(tdf)):.1%} | 利益平均: {tw.mean():+.2%} | 損失平均: {tl.mean():+.2%} | PF: {tw.sum()/abs(tl.sum()) if not tl.empty else 9.9:.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            st.code("\n".join(rpt), language="text")
            if st.button("♻️ 個別テスト結果をリセット", key="reset_t1", use_container_width=True):
                st.session_state['res_df'] = pd.DataFrame(); st.rerun()
        else: st.info("💡 個別バックテストの結果はありません。")

    # (tab1以外の分析タブも同様に、core.get_trade_pattern等を利用して構築します)
    # ここでは詳細ログ(tab6)とランキング(tab_rank)に絞って記述します

    with tabs[5]: # 📝 詳細ログ
        if not res_df.empty and 'Ticker' in res_df.columns:
            log_report = []
            for t in res_df['Ticker'].unique():
                tdf = res_df[res_df['Ticker'] == t].copy().sort_values('Entry', ascending=False)
                log_report.append(f"[{t}] {ticker_names.get(t, t)} 取引履歴\n" + "-"*80)
                for _, row in tdf.iterrows():
                    vwap_str = f"{int(row['EntryVWAP'])} (乖離 {((row['In']-row['EntryVWAP'])/row['EntryVWAP']*100):+.2f}%)"
                    log_report.append(f"{row['Entry'].strftime('%Y-%m-%d %H:%M')} | {row['Pattern']} | PnL: {row['PnL']:+.2%} | 買：{int(row['In'])} | 売：{int(row['Out'])} | VWAP: {vwap_str} | {row['Reason']}")
                log_report.append("\n")
            st.code("\n".join(log_report), language="text")
            if st.button("♻️ 個別テスト結果をリセット", key="reset_t6", use_container_width=True):
                st.session_state['res_df'] = pd.DataFrame(); st.rerun()
        else: st.info("💡 個別バックテストの結果はありません。")

    with tabs[6]: # 🏆 ランキング
        st.markdown("### 🏆 登録銘柄ランキング")
        st.markdown("""<p style='font-size:0.85rem; color:#808495;'>サイドバーの『ランキング生成』から実行。<br><span style='color:yellow;'>『個別テスト結果をリセット』してからご利用ください。</span></p>""", unsafe_allow_html=True)
        
        if st.session_state.get('trigger_rank_scan', False):
            st.session_state['trigger_rank_scan'] = False
            rank_list = []
            all_tickers = list(TICKER_NAME_MAP.keys())
            with st.status("🔍 全銘柄スキャン中...", expanded=True) as status:
                pb_r = st.progress(0)
                for i, t in enumerate(all_tickers):
                    status.update(label=f"Scanning {i+1}/{len(all_tickers)}: {t}")
                    pb_r.progress((i+1)/len(all_tickers))
                    df_r = fetch_intraday(t, datetime.now()-timedelta(days=days_back), datetime.now())
                    if df_r.empty: continue
                    if not (p_min <= df_r['Close'].iloc[-1] <= p_max): continue
                    p_map, o_map, a_map = core.fetch_daily_stats_maps(t, datetime.now()-timedelta(days=days_back))
                    t_trades = core.run_ticker_simulation(t, df_r, p_map, o_map, a_map, params)
                    if t_trades:
                        score_data = core.get_one_touch_score(t_trades)
                        rank_list.append({
                            'コード': t, '銘柄名': TICKER_NAME_MAP.get(t,t), '勝率': score_data['win_rate'],
                            'PF': score_data['pf'], '期待値': score_data['ev']
                        })
                status.update(label="✅ スキャン完了！", state="complete")
            if rank_list:
                st.session_state['last_rank_df'] = pd.DataFrame(rank_list).sort_values('期待値', ascending=False)
                st.rerun()

        if 'last_rank_df' in st.session_state:
            st.dataframe(st.session_state['last_rank_df'].style.format({'勝率': '{:.1%}', '期待値': '{:+.2%}', 'PF': '{:.2f}'}), use_container_width=True, hide_index=True)
            if st.button("ランキング表示をクリア"): del st.session_state['last_rank_df']; st.rerun()
