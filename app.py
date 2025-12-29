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

# --- 2. カスタムCSS (確定デザイン完全固定) ---
st.markdown("""
    <style>
    /* メインタイトル: font-weight 400 */
    .main-title { 
        font-weight: 400 !important; 
        font-size: 46px !important; 
        margin: 0 !important; 
        padding: 0 !important; 
    }
    /* サブタイトル: font-weight 300, size 20px */
    .sub-title { 
        font-weight: 300 !important; 
        font-size: 20px !important; 
        margin: 0 !important; 
        padding: 0 !important; 
        color: #aaaaaa !important; 
    }

    /* バックテストサマリーボックス (5.8再現) */
    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 18px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 11px; color: #888888; margin-bottom: 5px; }
    .summary-value { font-size: 28px; font-weight: bold; color: #ffffff; }

    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    th, td { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 銘柄名マッピング & セッション管理 ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "3436.T": "SUMCO", "6920.T": "レーザーテック", "7011.T": "三菱重工業", 
    "7203.T": "トヨタ自動車", "8267.T": "イオン", "8306.T": "三菱UFJ", "9984.T": "ソフトバンクG", "1570.T": "日経レバ"
}

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"

# --- 4. サイドバー設定 ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    if st.sidebar.button(l + (" [ 選択中 ]" if st.session_state['preset']==p else ""), type="primary" if st.session_state['preset']==p else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back_input = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
start_entry_in = st.sidebar.time_input("開始時間", time(9, 0))
end_entry_in = st.sidebar.time_input("終了時間", time(9, 15))
st.sidebar.markdown("<br>", unsafe_allow_html=True)

st.sidebar.subheader("📉 エントリー条件")
use_vwap_check = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
use_ema_check = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
use_rsi_check = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
use_macd_check = st.sidebar.checkbox("**MACD** が上向き", value=True)

st.sidebar.divider()
gap_min_val = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05)/100
gap_max_val = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05)/100

st.sidebar.subheader("💰 決済ルール")
t_start_val = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05)/100
t_pct_val = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05)/100
s_loss_val = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05)/100

# --- 5. ロジック関数 ---
def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker):
    try:
        df = yf.download(ticker, period="60d", interval="1d", progress=False)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# --- 6. メインレイアウト ---
st.markdown(f"""
    <div style='margin-bottom: 20px;'>
        <h1 class='main-title'>FORE CASTER</h1>
        <h3 class='sub-title'>SCREENING & BACKTEST | ver 1.63</h3>
    </div>
    """, unsafe_allow_html=True)

st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_bt:
    tickers_arr = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        trades_list = []
        progress_bar = st.progress(0)
        for idx, ticker in enumerate(tickers_arr):
            progress_bar.progress((idx + 1) / len(tickers_arr))
            try:
                # 取得期間を広げて確実にデータをキャッチ
                df_raw = yf.download(ticker, period="60d", interval="5m", progress=False)
                prev_m, open_m = fetch_daily_stats_maps(ticker)
                if df_raw.empty: continue
                
                df_raw.index = df_raw.index.tz_convert('Asia/Tokyo') if df_raw.index.tzinfo else df_raw.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
                
                # 指標計算
                df_raw['EMA5'] = EMAIndicator(close=df_raw['Close'], window=5).ema_indicator()
                df_raw['RSI14'] = RSIIndicator(close=df_raw['Close'], window=14).rsi()
                df_raw['RSI_P'] = df_raw['RSI14'].shift(1)
                macd_o = MACD(close=df_raw['Close']); df_raw['MH'] = macd_o.macd_diff(); df_raw['MHP'] = df_raw['MH'].shift(1)
                
                for date_obj in np.unique(df_raw.index.date)[-days_back_input:]:
                    day_data = df_raw[df_raw.index.date == date_obj].copy().between_time('09:00', '15:00')
                    if day_data.empty: continue
                    
                    # VWAP計算
                    tp_val = (day_data['High'] + day_data['Low'] + day_data['Close']) / 3
                    day_data['VWAP'] = (tp_val * day_data['Volume']).cumsum() / day_data['Volume'].cumsum()
                    
                    d_str = date_obj.strftime('%Y-%m-%d')
                    pc_val = prev_m.get(d_str); do_val = open_m.get(d_str)
                    if pc_val is None or do_val is None: continue
                    gap_pct_val = (do_val - pc_val) / pc_val
                    
                    in_pos = False; t_high_val = 0; t_active_val = False; entry_p_val = 0; stop_p_val = 0; entry_t_val = None
                    
                    for ts_idx, row_val in day_data.iterrows():
                        cur_t_val = ts_idx.time()
                        if not in_pos:
                            if start_entry_in <= cur_t_val <= end_entry_in and gap_min_val <= gap_pct_val <= gap_max_val:
                                # サイドバーの条件連動ロジック
                                cond_v = (row_val['Close'] > row_val['VWAP']) if use_vwap_check else True
                                cond_e = (row_val['Close'] > row_val['EMA5']) if use_ema_check else True
                                cond_r = (row_val['RSI14'] > 45 and row_val['RSI14'] > row_val['RSI_P']) if use_rsi_check else True
                                cond_m = (row_val['MH'] > row_val['MHP']) if use_macd_check else True
                                
                                if cond_v and cond_e and cond_r and cond_m:
                                    entry_p_val = row_val['Close'] * 1.0003
                                    in_pos = True; entry_t_val = ts_idx; stop_p_val = entry_p_val * (1 + s_loss_val); t_high_val = row_val['High']
                                    pat_str = get_trade_pattern(row_val, gap_pct_val); vwap_val = row_val['VWAP']
                        else:
                            t_high_val = max(t_high_val, row_val['High'])
                            if not t_active_val and t_high_val >= entry_p_val * (1 + t_start_val): t_active_val = True
                            
                            exit_p_val = None; rsn_msg = ""
                            if t_active_val and row_val['Low'] <= t_high_val * (1 - t_pct_val):
                                exit_p_val = t_high_val * (1 - t_pct_val) * 0.9997; rsn_msg = "トレーリング"
                            elif row_val['Low'] <= stop_p_val:
                                exit_p_val = stop_p_val * 0.9997; rsn_msg = "損切り"
                            elif cur_t_val >= time(14, 55):
                                exit_p_val = row_val['Close'] * 0.9997; rsn_msg = "時間切れ"
                                
                            if exit_p_val:
                                trades_list.append({
                                    'Ticker': ticker, 'Entry': entry_t_val, 'PnL': (exit_p_val - entry_p_val)/entry_p_val, 
                                    'In': entry_p_val, 'Out': exit_p_val, 'Pattern': pat_str, 'Gap': gap_pct_val, 
                                    'Reason': rsn_msg, 'EntryVWAP': vwap_val, 'PrevClose': pc_val, 'DayOpen': do_val
                                })
                                in_pos = False; break
            except: continue
                
        progress_bar.empty()
        if trades_list:
            res_df = pd.DataFrame(trades_list)
            b1, b2, b3, b4, b5 = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "📝 詳細ログ"])
            with b1:
                wins_df = res_df[res_df['PnL']>0]['PnL']; losses_df = res_df[res_df['PnL']<=0]['PnL']
                pf_score = wins_df.sum()/abs(losses_df.sum()) if not losses_df.empty and losses_df.sum() != 0 else 0
                st.markdown(f"""
                <div class='summary-container'>
                    <div class='summary-box'><div class='summary-label'>総トレード数</div><div class='summary-value'>{len(res_df)}回</div></div>
                    <div class='summary-box'><div class='summary-label'>勝率</div><div class='summary-value'>{(res_df['PnL']>0).mean():.1%}</div></div>
                    <div class='summary-box'><div class='summary-label'>PF</div><div class='summary-value'>{pf_score:.2f}</div></div>
                    <div class='summary-box'><div class='summary-label'>期待値</div><div class='summary-value'>{res_df['PnL'].mean():.2%}</div></div>
                </div>
                """, unsafe_allow_html=True)
                
                # REPORT
                rpt = ["=================\n BACKTEST REPORT \n================="]
                for tk in tickers_arr:
                    tdf = res_df[res_df['Ticker'] == tk]
                    if tdf.empty: continue
                    nm = TICKER_NAME_MAP.get(tk, tk); w = tdf[tdf['PnL']>0]['PnL']; l = tdf[tdf['PnL']<=0]['PnL']
                    rpt.append(f">>> TICKER: {tk} | {nm}")
                    rpt.append(f"トレード数: {len(tdf)} | 勝率: {(tdf['PnL']>0).mean():.1%} | 利益平均: {w.mean() if not w.empty else 0:+.2%} | 損失平均: {l.mean() if not l.empty else 0:+.2%} | PF: {w.sum()/abs(l.sum()) if not l.empty and l.sum()!=0 else 0:.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
                st.code("\n".join(rpt), language="text")
            with b2:
                # 勝ちパターン分析 (表表示)
                st.dataframe(res_df.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).style.format({'<lambda_0>': '{:.1%}', 'mean': '{:+.2%}'}), use_container_width=True)
            with b5:
                # 詳細ログ
                log_df = res_df[['Ticker', 'Entry', 'Pattern', 'PnL', 'Reason', 'In', 'Out']].copy()
                log_df['Entry'] = log_df['Entry'].dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(log_df.style.format({'PnL': '{:+.2%}'}), use_container_width=True, hide_index=True)
        else:
            st.warning("条件に合うトレードはありませんでした。サイドバーのエントリー条件をすべてオフにして再試行してください。")
