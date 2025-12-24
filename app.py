import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# カスタムCSS
st.markdown("""
    <style>
    .main-title { font-weight: 500; font-size: 26px; margin-bottom: 5px; }
    .section-header { font-size: 16px !important; font-weight: 600; color: #dddddd; vertical-align: middle; }
    .market-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; border-bottom: 1px solid #3d414b; background-color: #1e2129; }
    .market-name { font-size: 14px; font-weight: 500; color: #ffffff; flex: 2; }
    .market-price { font-size: 16px; font-weight: 600; color: #ffffff; flex: 2; text-align: right; padding-right: 20px; }
    .market-delta { font-size: 14px; font-weight: 600; flex: 1.5; text-align: right; border-radius: 4px; padding: 2px 6px; }
    .up-bg { color: #00f0a8; } .down-bg { color: #ff4b4b; }
    div[data-testid="column"] button { padding: 2px 8px !important; font-size: 12px !important; height: 28px !important; margin-top: -5px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 & マッピング ---
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

MARKET_INDICES = {
    "日経平均": "^N225", "日経先物": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油(WTI)": "CL=F", "Gold": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

# --- 3. ロジック関数 ---

@st.cache_data(ttl=600)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
            else: data[name] = {"val": None, "pct": None}
        except: data[name] = {"val": None, "pct": None}
    return data

def run_single_backtest(ticker, days_back, params):
    """銘柄のバックテスト期待値を算出（条件緩和版）"""
    start_date = datetime.now() - timedelta(days=days_back)
    try:
        # スキャン速度向上のため、必要最小限の期間を取得
        df = yf.download(ticker, start=start_date, interval="5m", progress=False, multi_level_index=False)
        if df.empty or len(df) < 20: return None
        
        df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
        
        pnls = []
        unique_dates = np.unique(df.index.date)
        
        for date in unique_dates:
            day = df[df.index.date == date].copy().between_time('09:00', '15:00')
            if day.empty or len(day) < 5: continue
            
            # 簡易VWAP
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            
            in_pos = False
            for ts, row in day.iterrows():
                cur_t = ts.time()
                if not in_pos and params['start'] <= cur_t <= params['end']:
                    # 判定条件
                    c_vwap = (row['Close'] > row['VWAP']) if params['use_vwap'] else True
                    c_ema = (row['Close'] > row['EMA5']) if params['use_ema'] else True
                    
                    if c_vwap and c_ema:
                        entry_p = row['Close'] * 1.0003
                        in_pos = True; trail_high = row['High']
                elif in_pos:
                    if row['High'] > trail_high: trail_high = row['High']
                    # 決済ロジック
                    if row['Low'] <= entry_p * (1 + params['stop']) or cur_t >= time(14, 55):
                        exit_p = row['Close'] * 0.9997
                        pnls.append((exit_p - entry_p) / entry_p)
                        in_pos = False; break
        
        return np.mean(pnls) if pnls else None
    except:
        return None

# --- 4. サイドバー ---
st.sidebar.subheader("🛡️ 戦略プリセット")
col_p1, col_p2, col_p3 = st.sidebar.columns(3)
if col_p1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_p2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_p3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.subheader("⚙️ スキャン設定")
# 期間をデフォルト20日、スライダーを30日までにしてヒット率を上げる
days_back_val = st.sidebar.slider("分析期間 (日)", 5, 30, 20)
start_t = st.sidebar.time_input("エントリー開始", time(9, 0))
end_t = st.sidebar.time_input("エントリー終了", time(9, 20)) # 終了を少し伸ばしてヒット率向上
use_vwap_cfg = st.sidebar.checkbox("VWAP条件を使用", value=True)
use_ema_cfg = st.sidebar.checkbox("EMA5条件を使用", value=True)
stop_loss_val = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -1.0) / 100

# --- 5. メイン ---
st.markdown("<div class='main-title'>FORE CASTER</div>", unsafe_allow_html=True)

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["ワンタッチ", "スクリーニング", "バックテスト"])

with tab_top:
    h_col1, h_col2 = st.columns([0.25, 0.75])
    with h_col1: st.markdown("<span class='section-header'>🌍 リアルタイム指標</span>", unsafe_allow_html=True)
    with h_col2:
        if st.button("🔄更新"): st.cache_data.clear(); st.rerun()

    with st.expander("詳細を表示", expanded=True):
        market_data = fetch_market_info()
        for name, info in market_data.items():
            if info["val"]:
                st.markdown(f'<div class="market-row"><div class="market-name">{name}</div><div class="market-price">{info["val"]:,.1f}</div><div class="market-delta {"up-bg" if info["pct"]>=0 else "down-bg"}">{info["pct"]:+.2f}%</div></div>', unsafe_allow_html=True)
    
    st.divider()
    st.markdown("<div class='section-header'>🚀 One-Touch 期待値スキャン</div>", unsafe_allow_html=True)
    if st.button("全42銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        results = []
        p_bar = st.progress(0)
        status = st.empty()
        
        scan_params = {
            'start': start_t, 'end': end_t, 'use_vwap': use_vwap_cfg, 
            'use_ema': use_ema_cfg, 'stop': stop_loss_val
        }
        
        tickers_list = list(TICKER_NAME_MAP.keys())
        for i, t in enumerate(tickers_list):
            status.text(f"分析中: {t} ({TICKER_NAME_MAP[t]})")
            p_bar.progress((i + 1) / len(tickers_list))
            ev = run_single_backtest(t, days_back_val, scan_params)
            if ev is not None:
                results.append({"code": t, "name": TICKER_NAME_MAP[t], "ev": ev})
        
        p_bar.empty(); status.empty()
        
        if results:
            # 期待値が高い順にソート
            top5 = sorted(results, key=lambda x: x['ev'], reverse=True)[:5]
            st.session_state['target_tickers'] = ", ".join([d['code'] for d in top5])
            
            st.success(f"スキャン完了！直近 {days_back_val} 日間で期待値の高い5銘柄をロードしました。")
            
            # 結果をテーブルで表示
            res_display = pd.DataFrame(top5)
            res_display.columns = ["コード", "銘柄名", "期待値(Avg PnL)"]
            res_display["期待値(Avg PnL)"] = res_display["期待値(Avg PnL)"].apply(lambda x: f"{x:+.3%}")
            st.table(res_display)
            
            # ページをリロードして入力欄に反映
            st.rerun()
        else:
            st.error("指定された期間・条件でトレードが発生した銘柄がありませんでした。サイドバーで「分析期間」を長くするか、「条件」を緩めてみてください。")
