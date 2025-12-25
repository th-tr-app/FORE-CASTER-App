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

# --- 2. カスタムCSS (デザインの心臓部) ---
st.markdown("""
    <style>
    /* タイトルエリア */
    .title-container {
        margin-bottom: 20px;
    }
    .main-title {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 500;
        font-size: 38px;
        margin: 0;
        padding: 0;
        color: #ffffff;
        line-height: 1.2;
    }
    .sub-title {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 300;
        font-size: 16px;
        color: #888888;
        margin: 0;
        padding: 0;
        letter-spacing: 1px;
    }

    /* リアルタイム指標ヘッダー (テキストとボタンの横並び調整) */
    .header-row {
        display: flex;
        align-items: center;
        margin-bottom: 10px;
    }
    .section-icon { font-size: 24px; margin-right: 8px; vertical-align: middle; }
    .section-text { font-size: 20px; font-weight: 600; color: #eeeeee; vertical-align: middle; }

    /* 更新ボタンの右寄せ & スタイル調整 */
    div[data-testid="column"] button {
        float: right;
        font-size: 12px !important;
        padding: 4px 12px !important;
        height: auto !important;
        min-height: 0px !important;
        margin-top: 5px; /* テキストとの高さ合わせ */
    }

    /* 指標カード・グリッドシステム */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr); /* PC: 4列 */
        gap: 10px;
        width: 100%;
        margin-top: 5px;
    }

    /* スマホ (幅640px以下) -> 2列 */
    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
        .main-title { font-size: 28px; }
        .sub-title { font-size: 14px; }
    }

    /* カード個別のデザイン (sample01.jpg再現) */
    .metric-card {
        background-color: #16171b; /* 背景色を少し濃く */
        border: 1px solid #333333;
        border-radius: 6px;
        padding: 12px 10px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 90px;
    }
    .metric-label { font-size: 11px; color: #bbbbbb; margin-bottom: 4px; }
    .metric-value { font-size: 20px; font-weight: 600; color: #ffffff; letter-spacing: 0.5px; }
    
    /* 騰落率バッジ */
    .delta-badge {
        font-size: 11px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin-top: 4px;
        width: fit-content;
    }
    .delta-plus { background-color: #1e3a2a; color: #4caf50; border: 1px solid #2e5a3a; } /* 緑系 */
    .delta-minus { background-color: #3a1e1e; color: #ff5252; border: 1px solid #5a2e2e; } /* 赤系 */

    /* AI予測ボックス */
    .ai-box {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 15px;
        margin-top: 15px;
        font-size: 14px;
        color: #d1d5db;
        line-height: 1.6;
    }
    .ai-label { color: #60a5fa; font-weight: bold; margin-bottom: 5px; }

    </style>
    """, unsafe_allow_html=True)

# --- 3. 定数 & 設定 ---
TICKER_NAME_MAP = {
    "1605.T": "INPEX", "1802.T": "大林組", "1812.T": "鹿島建設", "3436.T": "SUMCO",
    "4403.T": "日油", "4506.T": "住友ファーマ", "4507.T": "塩野義製薬", "4568.T": "第一三共",
    "5020.T": "ENEOS", "6315.T": "TOWA", "6361.T": "荏原製作所", "6460.T": "セガサミー",
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
    "日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油先物(WTI)": "CL=F", "Gold(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

# --- 4. 関数定義 ---
@st.cache_data(ttl=300) # 更新頻度を少し早める
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

def render_metric_card(name, val, pct):
    """カードHTML生成"""
    if val is None:
        return f"""
        <div class="metric-card">
            <div class="metric-label">{name}</div>
            <div class="metric-value">---</div>
            <div class="delta-badge" style="background-color:#333; color:#888;">---</div>
        </div>
        """
    
    # フォーマット調整
    if name == "ドル/円": fmt_val = f"{val:.2f}"
    elif val > 100: fmt_val = f"{val:,.0f}" # 株価指数などは小数なし
    else: fmt_val = f"{val:,.2f}"

    cls = "delta-plus" if pct >= 0 else "delta-minus"
    sign = "+" if pct >= 0 else ""
    
    return f"""
    <div class="metric-card">
        <div class="metric-label">{name}</div>
        <div class="metric-value">{fmt_val}</div>
        <div class="delta-badge {cls}">{sign}{pct:.2f}%</div>
    </div>
    """

def run_single_backtest(ticker, days_back, params):
    """(堅牢版) バックテスト実行"""
    start_date = datetime.now() - timedelta(days=days_back)
    try:
        df = yf.download(ticker, start=start_date, interval="5m", progress=False, multi_level_index=False)
        if df.empty or len(df) < 10: return None
        
        df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
        pnls = []
        unique_dates = np.unique(df.index.date)
        
        for date in unique_dates:
            day = df[df.index.date == date].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            
            in_pos = False; entry_p = 0; trail_high = 0
            for ts, row in day.iterrows():
                cur_t = ts.time()
                if not in_pos and params['start'] <= cur_t <= params['end']:
                    c_vwap = (row['Close'] > row['VWAP']) if params['use_vwap'] else True
                    c_ema = (row['Close'] > row['EMA5']) if params['use_ema'] else True
                    if c_vwap and c_ema:
                        entry_p = row['Close'] * 1.0003; in_pos = True; trail_high = row['High']
                elif in_pos:
                    if row['High'] > trail_high: trail_high = row['High']
                    if row['Low'] <= entry_p * (1 + params['stop']) or cur_t >= time(14, 55):
                        exit_p = row['Close'] * 0.9997
                        pnls.append((exit_p - entry_p) / entry_p)
                        in_pos = False; break
        return np.mean(pnls) if pnls else None
    except: return None

# --- 5. サイドバー ---
st.sidebar.subheader("🛡️ 戦略プリセット")
col_p1, col_p2, col_p3 = st.sidebar.columns(3)
if col_p1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_p2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_p3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.subheader("⚙️ スキャン設定")
days_back_val = st.sidebar.slider("分析期間 (日)", 5, 30, 20)
stop_loss_val = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -1.0) / 100

# --- 6. メインレイアウト ---

# タイトルエリア
st.markdown("""
<div class="title-container">
    <h1 class="main-title">FORE CASTER</h1>
    <p class="sub-title">DAY TRADING MANAGER | ver 5.8</p>
</div>
""", unsafe_allow_html=True)

# 共通銘柄入力
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

# タブ（アイコン付き）
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

# --- タブ1: ワンタッチ ---
with tab_top:
    # ヘッダー + 更新ボタン (右寄せ)
    col_h1, col_h2 = st.columns([0.7, 0.3])
    with col_h1:
        st.markdown('<div><span style="font-size:24px;">🌍</span> <span style="font-size:18px; font-weight:bold; color:#ddd;">リアルタイム指標</span></div>', unsafe_allow_html=True)
    with col_h2:
        if st.button("🔄 更新"):
            st.cache_data.clear()
            st.rerun()

    with st.expander("詳細を表示 (タップで開閉)", expanded=True):
        market_data = fetch_market_info()
        
        # グリッドHTML生成
        cards_html = "".join([render_metric_card(k, v['val'], v['pct']) for k, v in market_data.items()])
        st.markdown(f'<div class="metric-grid">{cards_html}</div>', unsafe_allow_html=True)

        # AI予測 (デザインラフ風)
        vix = market_data.get("VIX指数", {}).get("val", 0)
        ai_msg = "指標は中立です。テクニカルに従ってトレードしてください。"
        if vix and vix > 20: ai_msg = "VIXが高まっています。ボラティリティに注意し、慎重なエントリーを心がけてください。"
        elif vix and vix < 15: ai_msg = "市場は極めて安定しています。トレンド追随（順張り）が機能しやすい環境です。強気のエントリーを検討できます。"

        st.markdown(f"""
        <div class="ai-box">
            <div class="ai-label">🤖 AI予測</div>
            {ai_msg}
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    
    # One-Touch スキャンボタン
    if st.button("Top5を自動抽出", type="primary", use_container_width=True):
        results = []
        p_bar = st.progress(0)
        status = st.empty()
        
        params = {'start': time(9,0), 'end': time(9,15), 'use_vwap': True, 'use_ema': True, 'stop': stop_loss_val}
        keys = list(TICKER_NAME_MAP.keys())
        
        for i, t in enumerate(keys):
            status.text(f"Scanning... {t}")
            p_bar.progress((i+1)/len(keys))
            ev = run_single_backtest(t, days_back_val, params)
            if ev is not None: results.append({"code": t, "ev": ev})
            
        p_bar.empty(); status.empty()
        
        if results:
            top5 = sorted(results, key=lambda x: x['ev'], reverse=True)[:5]
            st.session_state['target_tickers'] = ", ".join([d['code'] for d in top5])
            st.success(f"スキャン完了！ Top5: {st.session_state['target_tickers']}")
            st.rerun()
        else:
            st.error("条件に合う銘柄が見つかりませんでした。条件を緩和してください。")
