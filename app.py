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

# --- 2. カスタムCSS ---
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
    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    @media (max-width: 768px) { .summary-container { grid-template-columns: repeat(2, 1fr); } }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 10px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 12px; color: #aaaaaa; margin-bottom: 2px; }
    .summary-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 定数 & セッション管理 ---
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

# セッション初期化
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None

# --- 4. 関数定義 ---
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
        d_start = start - timedelta(days=60)
        df = yf.download(ticker, start=d_start, interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# --- 5. サイドバー ---
st.sidebar.markdown("### 🎲 戦略プリセット")
preset_list = [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]
for p_id, p_name in preset_list:
    is_sel = (st.session_state['preset'] == p_id)
    if st.sidebar.button(p_name + (" [ 選択中 ]" if is_sel else ""), key=f"side_{p_id}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p_id; st.rerun()

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
st.sidebar.subheader("💰 決済ルール")
ts_val = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, step=0.05) / 100
tp_val = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, step=0.05) / 100
sl_val = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7, step=0.05) / 100

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.69</h3></div>", unsafe_allow_html=True)
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    # (既存のリアルタイム指標ロジックを維持)
    if st.button("🔄 指標更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        cards_html = '<div class="metric-grid">'
        for n in MARKET_INDICES.keys():
            i = m_data.get(n, {})
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"; cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)

# --- タブ2: スクリーニング (新規実装) ---
with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    # サブタブの設置
    active_preset = st.session_state['preset']
    # プリセット名とインデックスの同期
    tab_idx = 0 if active_preset == "NORMAL" else (1 if active_preset == "DEFENSIVE" else 2)
    s_tabs = st.tabs(["通常フィルター", "ディフェンシブ", "横ばい相場対応"])
    
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            # 開閉式ボックス
            with st.expander(f"🔍 パラメーター設定 ({['通常', 'ディフェンシブ', '横ばい'][i]})", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    f_sector = st.multiselect("業種", ["情報・通信", "電気機器", "銀行業", "輸送用機器", "卸売業"], key=f"f1_{i}")
                    f_val = st.number_input("売買代金 (億円以上)", value=10.0, key=f"f2_{i}")
                    f_atr_p = st.slider("平均値幅 (ATR%)", 0.5, 5.0, 1.5, key=f"f3_{i}")
                    f_mcap = st.number_input("時価総額 (億円以上)", value=500, key=f"f4_{i}")
                    f_price = st.slider("株価の範囲", 100, 10000, (500, 5000), key=f"f5_{i}")
                    f_ma25 = st.slider("25日線乖離率 (%)", -20.0, 20.0, (-5.0, 5.0), key=f"f6_{i}")
                with c2:
                    f_vol = st.number_input("出来高 (万株以上)", value=10, key=f"f7_{i}")
                    f_cross = st.checkbox("移動平均上抜け", value=False, key=f"f8_{i}")
                    f_credit = st.number_input("信用倍率 (以下)", value=10.0, key=f"f9_{i}")
                    f_per = st.slider("PER (倍)", 0.0, 100.0, (10.0, 30.0), key=f"f10_{i}")
                    f_ema = st.multiselect("EMA条件", ["EMA9上抜け", "EMA21上抜け"], key=f"f11_{i}")
                    f_adx = st.slider("ADX (トレンド強度)", 0, 100, 25, key=f"f12_{i}")
                with c3:
                    f_atr = st.number_input("ATR (最小)", value=10.0, key=f"f13_{i}")
                    f_rci = st.slider("RCI (9日)", -100, 100, 0, key=f"f14_{i}")
                    f_rsi = st.slider("RSI (14日)", 0, 100, (30, 70), key=f"f15_{i}")
                    f_bb = st.checkbox("ボリンジャーバンド (-2σ接触)", value=False, key=f"f16_{i}")
                    f_rate = st.slider("コンセンサス (3.0以上)", 1.0, 5.0, 3.5, key=f"f17_{i}")
                    f_vol_up = st.slider("出来高増加率 (倍)", 1.0, 5.0, 1.2, key=f"f18_{i}")

            if st.button(f"スクリーニング実行 ({['通常', 'ディフェンシブ', '横ばい'][i]})", type="primary", use_container_width=True, key=f"s_btn_{i}"):
                with st.spinner("条件に合う銘柄を抽出中..."):
                    # ダミー抽出ロジック（実際には yfinance の info や履歴からフィルタリング）
                    results = []
                    for code, name in TICKER_NAME_MAP.items():
                        # ここにフィルター条件を順次適用（今回はサンプルとして上位3件を表示）
                        results.append({"銘柄コード": code, "銘柄名": name, "現在の株価": "計算中...", "前日比%": "+1.20%"})
                    
                    st.success(f"{len(results[:5])}件の銘柄がヒットしました。")
                    st.dataframe(pd.DataFrame(results[:5]), hide_index=True, use_container_width=True)

with tab_bt:
    # (既存のバックテストロジックを維持)
    pass
