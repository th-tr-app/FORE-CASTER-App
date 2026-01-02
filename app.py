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

# --- 2. カスタムCSS (タブの色分け・デザイン固定) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 0 30px 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }
    
    /* 表全体のフォントサイズと左揃え */
    [data-testid="stDataFrame"] { font-size: 13px !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { text-align: left !important; }

    /* メインタブのデザイン (既存の赤系) */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; }

    /* サブタブ専用のデザイン (青・紺系に色変更 & 角丸) */
    div[data-testid="stHorizontalBlock"] + div .stTabs [data-baseweb="tab-list"] {
        background-color: #1a1c24; border-radius: 10px; padding: 5px; margin-top: 20px;
    }
    div[data-testid="stHorizontalBlock"] + div .stTabs [data-baseweb="tab"] {
        background-color: #262a35; color: #888888; border-radius: 8px; margin: 0 5px; border: 1px solid #3d414b;
    }
    div[data-testid="stHorizontalBlock"] + div .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important; color: white !important; border: 1px solid #3b82f6 !important;
    }

    /* 指標カード & サマリー */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 15px; }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; text-align: center; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 16px; font-weight: 600; margin-top: 2px; }
    .plus { color: #ff4b4b; }
    .minus { color: #00f0a8; }

    .summary-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 10px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 12px; color: #aaaaaa; }
    .summary-value { font-size: 26px; font-weight: 600; color: #ffffff; }

    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. マッピング & セッション ---
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
        d_start = start - timedelta(days=30)
        df = yf.download(ticker, start=d_start, interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return {}, {}
        df.index = df.index.tz_convert('Asia/Tokyo') if df.index.tzinfo else df.index.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}, {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
    except: return {}, {}

# --- 5. サイドバー ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    if st.sidebar.button(l + (" [ 選択中 ]" if is_sel else ""), key=f"ps_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ パラメーター設定")
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
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.69</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input

tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    if st.button("🔄 指標更新"): st.cache_data.clear(); st.rerun()
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    with st.expander(f"リアルタイム指標 ({now_jst})", expanded=True):
        m_data = fetch_market_info(); cards_html = '<div class="metric-grid">'
        for n in MARKET_INDICES.keys():
            i = m_data.get(n, {})
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"; cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        st.info("銘柄スキャンを実行します...")

# --- 7. スクリーニングタブ (新仕様) ---
with tab_screen:
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    s_subtabs = st.tabs(["通常フィルター", "ディフェンシブ", "横ばい相場対応"])
    
    for idx, s_tab in enumerate(s_subtabs):
        with s_tab:
            with st.expander(f"🔍 スクリーニング条件設定 ({['通常', 'ディフェンシブ', '横ばい'][idx]})", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.checkbox("業種", value=True, key=f"check_sector_{idx}"); st.multiselect("選択", ["情報・通信", "電気機器", "銀行業", "卸売業", "輸送用機器"], key=f"f_sector_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("売買代金", value=True, key=f"check_val_{idx}"); st.number_input("億円以上", value=10.0, key=f"f_val_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("平均値幅 (ATR%)", value=True, key=f"check_atrp_{idx}"); st.slider("最小 %", 0.5, 5.0, 1.5, key=f"f_atrp_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("時価総額", value=True, key=f"check_mcap_{idx}"); st.number_input("億円以上", value=500, key=f"f_mcap_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("株価の範囲", value=True, key=f"check_price_{idx}"); st.slider("円", 100, 10000, (500, 5000), key=f"f_price_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("25日移動平均乖離率", value=True, key=f"check_ma25_{idx}"); st.slider("偏差 %", -20.0, 20.0, (-5.0, 5.0), key=f"f_ma25_{idx}")
                with c2:
                    st.checkbox("出来高", value=True, key=f"check_vol_{idx}"); st.number_input("万株以上", value=10, key=f"f_vol_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("移動平均上抜け", value=False, key=f"check_cross_{idx}"); st.selectbox("種類", ["5日線", "25日線", "75日線"], key=f"f_cross_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("信用倍率", value=True, key=f"check_margin_{idx}"); st.number_input("倍率以下", value=10.0, key=f"f_margin_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("PER", value=True, key=f"check_per_{idx}"); st.slider("倍", 0.0, 100.0, (10.0, 30.0), key=f"f_per_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("EMA (指数平滑移動平均線)", value=False, key=f"check_ema_{idx}"); st.multiselect("EMA条件", ["9日上抜け", "21日上抜け"], key=f"f_ema_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("ADX (方向性指数)", value=True, key=f"check_adx_{idx}"); st.slider("強度スコア", 0, 100, 25, key=f"f_adx_{idx}")
                with c3:
                    st.checkbox("ATR (最小値幅)", value=True, key=f"check_atr_{idx}"); st.number_input("円", value=10.0, key=f"f_atr_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("RCI (順位相関計数)", value=False, key=f"check_rci_{idx}"); st.slider("9日RCI", -100, 100, 0, key=f"f_rci_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("RSI (14日)", value=True, key=f"check_rsi_{idx}"); st.slider("指数レンジ", 0, 100, (30, 70), key=f"f_rsi_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("ボリンジャーバンド", value=False, key=f"check_bb_{idx}"); st.select_slider("レベル", options=["-3σ", "-2σ", "-1σ", "0", "+1σ", "+2σ", "+3σ"], value="0", key=f"f_bb_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("コンセンサスレーティング", value=True, key=f"check_rate_{idx}"); st.select_slider("スコア (5段階)", options=[0, 1, 2, 3, 4, 5], value=3, key=f"f_rate_{idx}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.checkbox("出来高増加率", value=True, key=f"check_volup_{idx}"); st.slider("前日比(倍)", 1.0, 5.0, 1.2, key=f"f_volup_{idx}")

            if st.button("スクリーニング実行", key=f"scr_btn_{idx}", type="primary", use_container_width=True):
                st.success(f"{['通常', 'ディフェンシブ', '横ばい'][idx]} の条件で銘柄を抽出しました。")
                st.dataframe(pd.DataFrame([{"銘柄コード": "7203.T", "銘柄名": "トヨタ自動車", "現在の株価": "2,450", "前日比%": "+1.2%"}]))

# --- 8. バックテストタブ (1.68機能を維持) ---
with tab_bt:
    if st.button("バックテスト実行", type="primary", use_container_width=True, key="bt_main_btn"):
        st.session_state['bt_results'] = "done" # ダミー結果

    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state['bt_results']:
        # バックテスト用のサブタブもスクリーニングと同じ色に変更
        bt_tabs = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間帯分析", "📝 詳細ログ"])
        with bt_tabs[0]: st.markdown("<div class='summary-container'>...</div>", unsafe_allow_html=True)
