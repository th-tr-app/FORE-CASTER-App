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

# --- 2. カスタムCSS (デザイン完全固定) ---
st.markdown("""
    <style>
    /* メインタイトル: font-weight 400 */
    .main-title { 
        font-family: 'Inter', sans-serif;
        font-weight: 400 !important; 
        font-size: 46px !important; 
        margin: 0 !important; 
        padding: 0 !important; 
    }
    /* サブタイトル: font-weight 300, size 20px */
    .sub-title { 
        font-family: 'Inter', sans-serif;
        font-weight: 300 !important; 
        font-size: 20px !important; 
        margin: 0 !important; 
        padding: 0 !important; 
        color: #aaaaaa !important; 
    }

    /* 指標カード (🏠タブ) */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 5px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { 
        background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; 
        padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; 
    }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; margin: -2px 0; }
    .delta-badge { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }

    /* バックテストサマリー (📈タブ 5.8再現) */
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

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8267.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"

# --- 4. サイドバー設定 ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    if st.sidebar.button(l + (" [ 選択中 ]" if st.session_state['preset']==p else ""), type="primary" if st.session_state['preset']==p else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
start_entry_input = st.sidebar.time_input("開始時間", time(9, 0))
end_entry_input = st.sidebar.time_input("終了時間", time(9, 15))
st.sidebar.markdown("<br>", unsafe_allow_html=True)

st.sidebar.subheader("📉 エントリー条件")
use_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
use_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
use_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
use_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)

st.sidebar.divider()
gap_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05)/100
gap_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05)/100

st.sidebar.subheader("💰 決済ルール")
t_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05)/100
t_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05)/100
s_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05)/100

# --- 5. ロジック関数 ---
def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

@st.cache_data(ttl=300)
def fetch_market_info():
    indices = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "VIX指数": "^VIX", "NYダウ30種": "^DJI", "SOX指数": "^SOX"}
    data = {}
    for name, ticker in indices.items():
        try:
            df = yf.download(ticker, period="2d", progress=False)
            if not df.empty:
                data[name] = {"val": float(df['Close'].iloc[-1]), "pct": ((float(df['Close'].iloc[-1]) - float(df['Close'].iloc[-2])) / float(df['Close'].iloc[-2])) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        df = yf.download(ticker, start=start-timedelta(days=30), interval="1d", progress=False)
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# --- 6. メインレイアウト ---
# タイトル・サブタイトルを厳密なCSSクラスで描画
st.markdown(f"""
    <div style='margin-bottom: 20px;'>
        <h1 class='main-title'>FORE CASTER</h1>
        <h3 class='sub-title'>SCREENING & BACKTEST | ver 1.63</h3>
    </div>
    """, unsafe_allow_html=True)

st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    if st.button("🔄 更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info(); cards = '<div class="metric-grid">'
        for n, i in m_data.items():
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"; cls = "plus" if i['pct'] >= 0 else "minus"
                cards += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards + '</div>', unsafe_allow_html=True)

with tab_bt:
    tickers_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        s_date = datetime.now() - timedelta(days=days_back); all_trades = []
        progress = st.progress(0)
        for i, ticker in enumerate(tickers_list):
            progress.progress((i + 1) / len(tickers_list))
            try:
                # auto_adjust=False, multi_level_index=False で5.8の取得形式に合わせる
                df = yf.download(ticker, start=s_date, interval="5m", progress=False, auto_adjust=False, multi_level_index=False)
                prev_m, open_m = fetch_daily_stats_maps(ticker, s_date)
                if df.empty: continue
                
                # インデックスの正規化
                if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
                else: df.index = df.index.tz_convert('Asia/Tokyo')
                
                # テクニカル指標の計算
                df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
                df['RSI14'] = RSIIndicator(close=df['Close'], window=14).rsi()
                df['RSI_P'] = df['RSI14'].shift(1)
                macd_obj = MACD(close=df['Close'])
                df['MH'] = macd_obj.macd_diff()
                df['MHP'] = df['MH'].shift(1)
                
                for date in np.unique(df.index.date):
                    day_df = df[df.index.date == date].copy().between_time('09:00', '15:00')
                    if day_df.empty: continue
                    # VWAP計算
                    tp = (day_df['High'] + day_df['Low'] + day_df['Close']) / 3
                    day_df['VWAP'] = (tp * day_df['Volume']).cumsum() / day_df['Volume'].cumsum()
                    
                    pc = prev_m.get(date.strftime('%Y-%m-%d'))
                    do = open_m.get(date.strftime('%Y-%m-%d'))
                    if pc is None or do is None: continue
                    gap_val = (do - pc) / pc
                    
                    in_pos = False; t_high = 0; t_active = False; entry_p = 0; stop_p = 0; entry_t = None
                    
                    for ts, row in day_df.iterrows():
                        cur_t = ts.time()
                        if not in_pos:
                            # 判定ロジック：サイドバー条件との連動を修正
                            if start_entry_input <= cur_t <= end_entry_input and gap_min <= gap_val <= gap_max:
                                cond_v = (row['Close'] > row['VWAP']) if use_vwap else True
                                cond_e = (row['Close'] > row['EMA5']) if use_ema else True
                                cond_r = (row['RSI14'] > 45 and row['RSI14'] > row['RSI_P']) if use_rsi else True
                                cond_m = (row['MH'] > row['MHP']) if use_macd else True
                                
                                if cond_v and cond_e and cond_r and cond_m:
                                    entry_p = row['Close'] * 1.0003
                                    in_pos = True
                                    entry_t = ts
                                    stop_p = entry_p * (1 + s_loss)
                                    t_high = row['High']
                                    pat_type = get_trade_pattern(row, gap_val)
                                    entry_vwap_val = row['VWAP']
                        else:
                            # 決済ロジック
                            t_high = max(t_high, row['High'])
                            if not t_active and t_high >= entry_p * (1 + t_start): t_active = True
                            
                            exit_p = None; rsn_msg = ""
                            if t_active and row['Low'] <= t_high * (1 - t_pct):
                                exit_p = t_high * (1 - t_pct) * 0.9997; rsn_msg = "トレーリング"
                            elif row['Low'] <= stop_p:
                                exit_p = stop_p * 0.9997; rsn_msg = "損切り"
                            elif cur_t >= time(14, 55):
                                exit_p = row['Close'] * 0.9997; rsn_msg = "時間切れ"
                                
                            if exit_p:
                                all_trades.append({
                                    'Ticker': ticker, 'Entry': entry_t, 'PnL': (exit_p - entry_p)/entry_p, 
                                    'In': entry_p, 'Out': exit_p, 'Pattern': pat_type, 'Gap': gap_val, 
                                    'Reason': rsn_msg, 'EntryVWAP': entry_vwap_val, 'PrevClose': pc, 'DayOpen': do
                                })
                                in_pos = False; break
            except Exception as e:
                st.error(f"Error processing {ticker}: {e}")
                continue
                
        progress.empty()
        if all_trades:
            res_df = pd.DataFrame(all_trades)
            bt1, bt2, bt3, bt4, bt5 = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "📝 詳細ログ"])
            with bt1:
                wins_s = res_df[res_df['PnL']>0]['PnL']; losses_s = res_df[res_df['PnL']<=0]['PnL']
                pf_val = wins_s.sum()/abs(losses_s.sum()) if not losses_s.empty and losses_s.sum() != 0 else 0
                st.markdown(f"""
                <div class='summary-container'>
                    <div class='summary-box'><div class='summary-label'>総トレード数</div><div class='summary-value'>{len(res_df)}回</div></div>
                    <div class='summary-box'><div class='summary-label'>勝率</div><div class='summary-value'>{(res_df['PnL']>0).mean():.1%}</div></div>
                    <div class='summary-box'><div class='summary-label'>PF</div><div class='summary-value'>{pf_val:.2f}</div></div>
                    <div class='summary-box'><div class='summary-label'>期待値</div><div class='summary-value'>{res_df['PnL'].mean():.2%}</div></div>
                </div>
                """, unsafe_allow_html=True)
                
                # レポート出力
                report_lines = ["=================\n BACKTEST REPORT \n================="]
                for tk in tickers_list:
                    tdf_single = res_df[res_df['Ticker'] == tk]
                    if tdf_single.empty: continue
                    nm = TICKER_NAME_MAP.get(tk, tk)
                    w_s = tdf_single[tdf_single['PnL']>0]['PnL']; l_s = tdf_single[tdf_single['PnL']<=0]['PnL']
                    t_pf_val = w_s.sum()/abs(l_s.sum()) if not l_s.empty and l_s.sum() != 0 else 0
                    report_lines.append(f">>> TICKER: {tk} | {nm}")
                    report_lines.append(f"トレード数: {len(tdf_single)} | 勝率: {(tdf_single['PnL']>0).mean():.1%} | 利益平均: {w_s.mean() if not w_s.empty else 0:+.2%} | 損失平均: {l_s.mean() if not l_s.empty else 0:+.2%} | PF: {t_pf_val:.2f} | 期待値: {tdf_single['PnL'].mean():+.2%}\n")
                st.code("\n".join(report_lines), language="text")
            with bt2:
                # パターン別成績
                pat_summary = res_df.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                pat_summary.columns = ['パターン', '回数', '勝率', '平均損益']
                st.dataframe(pat_summary.style.format({'勝率': '{:.1%}', '平均損益': '{:+.2%}'}), use_container_width=True, hide_index=True)
            with bt3:
                # ギャップ分析
                res_df['GapDir'] = res_df['Gap'].apply(lambda x: 'GU' if x > 0 else 'GD')
                st.dataframe(res_df.groupby('GapDir')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).style.format({'<lambda_0>': '{:.1%}', 'mean': '{:+.2%}'}), use_container_width=True)
            with bt4:
                # VWAP乖離分析
                res_df['VWAP乖離'] = ((res_df['In'] - res_df['EntryVWAP']) / res_df['EntryVWAP']) * 100
                st.dataframe(res_df.groupby(pd.cut(res_df['VWAP乖離'], bins=5))['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).style.format({'<lambda_0>': '{:.1%}', 'mean': '{:+.2%}'}), use_container_width=True)
            with bt5:
                # 詳細ログ
                log_disp = res_df[['Ticker', 'Entry', 'Pattern', 'PnL', 'Reason', 'In', 'Out']].copy()
                log_disp['Entry'] = log_disp['Entry'].dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(log_disp.style.format({'PnL': '{:+.2%}'}), use_container_width=True, hide_index=True)
        else:
            st.warning("条件に合うトレードはありませんでした。サイドバーのエントリー条件（VWAP/EMA等）を外して再試行してください。")
