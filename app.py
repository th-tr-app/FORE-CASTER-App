import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# --- 2. カスタムCSS (左揃え・デザイン固定) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }

    /* 表全体の左揃えを強制 */
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
        text-align: left !important;
    }
    /* データフレームのフォントサイズ調整 */
    [data-testid="stDataFrame"] { font-size: 13px !important; }

    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 15px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { 
        background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; 
        padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0px; 
    }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 4px; margin-top: 2px; }
    .plus { background-color: #3a1e1e; color: #ff4b4b; }
    .minus { background-color: #1e3a2a; color: #00f0a8; }

    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 18px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 11px; color: #888888; margin-bottom: 5px; }
    .summary-value { font-size: 28px; font-weight: bold; color: #ffffff; }

    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# (銘柄名マッピング・セッション管理・関数定義は変更なしのため統合)
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

def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row['RSI14'] >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

@st.cache_data(ttl=600)
def fetch_intraday(ticker, start):
    try: return yf.download(ticker, start=start, end=datetime.now(), interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    try:
        d_start = start - timedelta(days=30)
        df = yf.download(ticker, start=d_start, interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# UI
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
st.sidebar.markdown("### 🎲 戦略プリセット")
# (プリセットボタンなどのロジック)
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
start_entry_time = st.sidebar.time_input("開始時間", time(9, 0), step=300)
end_entry_time = st.sidebar.time_input("終了時間", time(9, 15), step=300)
use_vwap = st.sidebar.checkbox("**VWAP** より上でエントリー", value=True)
use_ema = st.sidebar.checkbox("**EMA5** より上でエントリー", value=True)
use_rsi = st.sidebar.checkbox("**RSI** が45以上or上向き", value=True)
use_macd = st.sidebar.checkbox("**MACD** が上向き", value=True)
gap_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
gap_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
trailing_pct = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, 0.05) / 100

st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.66</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_bt:
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        all_trades = []; ticker_names = {}
        progress_bar = st.progress(0)
        end_date = datetime.now(); start_date = end_date - timedelta(days=days_back)
        
        for idx, ticker in enumerate(tickers):
            progress_bar.progress((idx + 1) / len(tickers))
            t_name = TICKER_NAME_MAP.get(ticker, ticker)
            ticker_names[ticker] = t_name
            df = fetch_intraday(ticker, start_date)
            pc_map, co_map = fetch_daily_stats_maps(ticker, start_date)
            if df.empty: continue
            df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
            df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
            macd = MACD(close=df['Close']); df['MACD_H'] = macd.macd_diff(); df['MACD_H_Prev'] = df['MACD_H'].shift(1)
            rsi = RSIIndicator(close=df['Close'], window=14); df['RSI14'] = rsi.rsi(); df['RSI14_Prev'] = df['RSI14'].shift(1)
            
            for d in np.unique(df.index.date):
                day = df[df.index.date == d].copy().between_time('09:00', '15:00')
                if day.empty: continue
                day['VWAP'] = ( ( (day['High']+day['Low']+day['Close'])/3 ) * day['Volume'] ).cumsum() / day['Volume'].cumsum()
                pc = pc_map.get(d.strftime('%Y-%m-%d')); do = co_map.get(d.strftime('%Y-%m-%d'))
                if pc is None or do is None: continue
                gap_val = (do - pc) / pc
                in_pos = False; trail_active = False; trail_high = 0
                for ts, row in day.iterrows():
                    if not in_pos:
                        if start_entry_time <= ts.time() <= end_entry_time and gap_min <= gap_val <= gap_max:
                            c_v = (row['Close'] > row['VWAP']) if use_vwap else True
                            c_e = (row['Close'] > row['EMA5']) if use_ema else True
                            c_r = (row['RSI14'] > 45 and row['RSI14'] > row['RSI14_Prev']) if use_rsi else True
                            c_m = (row['MACD_H'] > row['MACD_H_Prev']) if use_macd else True
                            if c_v and c_e and c_r and c_m:
                                entry_p = row['Close'] * 1.0003; in_pos = True; entry_t = ts; entry_vwap = row['VWAP']
                                stop_p = entry_p * (1 + stop_loss); trail_high = row['High']; pat = get_trade_pattern(row, gap_val)
                    else:
                        trail_high = max(trail_high, row['High'])
                        if not trail_active and trail_high >= entry_p * (1 + trailing_start): trail_active = True
                        ex_p = None
                        if trail_active and row['Low'] <= trail_high * (1 - trailing_pct): ex_p = trail_high * (1 - trailing_pct) * 0.9997; rsn = "トレーリング"
                        elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997; rsn = "損切り"
                        elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997; rsn = "時間切れ"
                        if ex_p:
                            all_trades.append({'Ticker': ticker, 'Entry': entry_t, 'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p, 'Pattern': pat, 'Gap(%)': gap_val*100, 'Reason': rsn, 'EntryVWAP': entry_vwap, 'PrevClose': pc, 'DayOpen': do})
                            in_pos = False; break
        
        progress_bar.empty()
        if not all_trades: st.warning("条件に合うトレードはありませんでした。")
        else:
            res_df = pd.DataFrame(all_trades)
            tabs = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ"])
            
            with tabs[1]: # 🤖 勝ちパターン分析
                st.markdown("### 🤖 勝ちパターン分析")
                st.caption("チャートパターン別の成績分析と、ベストなエントリー条件の言語化をします。自身の「得意な形」が一目で分かります。")
                st.divider()
                for t in tickers:
                    tdf = res_df[res_df['Ticker'] == t].copy()
                    if tdf.empty: continue
                    st.markdown(f"#### [{t}] {ticker_names[t]}")
                    p_sum = tdf.groupby('Pattern')['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                    p_sum.columns = ['パターン', 'トレード数', '勝率', '平均損益']
                    p_sum['勝率'] = p_sum['勝率'].apply(lambda x: f"{x:.1%}")
                    p_sum['平均損益'] = p_sum['平均損益'].apply(lambda x: f"{x:+.2%}")
                    st.dataframe(p_sum.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                    
                    # 言語化ロジックのKeyError対策
                    tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                    g_stats = tdf.groupby(pd.cut(tdf['Gap(%)'], bins=np.arange(-3.0, 3.5, 0.5)), observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()])
                    v_stats = tdf.groupby(pd.cut(tdf['VWAP乖離(%)'], bins=np.arange(-1.0, 1.2, 0.2)), observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()])
                    t_stats = tdf.groupby(tdf['Entry'].dt.strftime('%H:%M'))['PnL'].agg(['count', lambda x: (x>0).mean()])
                    
                    if not g_stats.empty and not v_stats.empty and not t_stats.empty:
                        best_g_idx = g_stats['<lambda_0>'].idxmax(); best_v_idx = v_stats['<lambda_0>'].idxmax(); best_t_idx = t_stats['<lambda_0>'].idxmax()
                        gap_txt = "ギャップアップ" if best_g_idx.left >= 0 else "ギャップダウン"
                        st.info(f"**🏆 最高勝率パターン**\n\n最も勝率が高かったのは、**{gap_txt} ({best_g_idx.left:.1f}% ～ {best_g_idx.right:.1f}%)** スタートで、VWAPから **{best_v_idx.left:.1f}% ～ {best_v_idx.right:.1f}%** の位置にある時、**{best_t_idx}** にエントリーするパターンです。")
                    st.divider()

            with tabs[2]: # 📉 ギャップ分析
                st.markdown("### 📉 始値ギャップ分析")
                st.caption("寄り付きの窓開け（ギャップ）の方向や幅が、その後の勝率にどう影響しているかを分析します。")
                st.divider()
                for t in tickers:
                    tdf = res_df[res_df['Ticker'] == t].copy()
                    if tdf.empty: continue
                    st.markdown(f"#### [{t}] {ticker_names[t]}")
                    
                    # 1. ギャップ方向別の成績
                    st.markdown("##### 始値ギャップ方向と成績")
                    tdf['方向'] = tdf['Gap(%)'].apply(lambda x: 'ギャップアップ' if x > 0 else ('ギャップダウン' if x < 0 else 'フラット'))
                    dir_stats = tdf.groupby('方向').agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x > 0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                    dir_stats['勝率'] = dir_stats['勝率'].apply(lambda x: f"{x:.1%}")
                    dir_stats['平均損益'] = dir_stats['平均損益'].apply(lambda x: f"{x:+.2%}")
                    st.dataframe(dir_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                    
                    # 2. ギャップ幅ごとの勝率
                    st.markdown("##### ギャップ幅ごとの勝率")
                    tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=np.arange(-3.0, 3.5, 0.5))
                    range_stats = tdf.groupby('GapRange', observed=True).agg(トレード数=('PnL', 'count'), 勝率=('PnL', lambda x: (x > 0).mean()), 平均損益=('PnL', 'mean')).reset_index()
                    range_stats['ギャップ幅'] = range_stats['GapRange'].apply(lambda i: f"{i.left:.1f}% ～ {i.right:.1f}%")
                    disp_range = range_stats[['ギャップ幅', 'トレード数', '勝率', '平均損益']]
                    disp_range['勝率'] = disp_range['勝率'].apply(lambda x: f"{x:.1%}")
                    disp_range['平均損益'] = disp_range['平均損益'].apply(lambda x: f"{x:+.2%}")
                    st.dataframe(disp_range.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                    st.divider()
