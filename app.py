import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta, time

# --- 1. ページ設定 & ロゴ ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")

# サイドバー設定（image_13.png: ロゴ, image_12.png: アイコン）
st.logo("image_13.png", icon_image="image_12.png")

# カスタムCSS（ボックスデザインとレスポンシブ設定）
st.markdown("""
    <style>
    /* 全体フォント調整 */
    .main-title { font-weight: 500; font-size: 28px; margin-bottom: 5px; }
    .section-header { font-size: 16px !important; font-weight: 600; margin: 15px 0 10px 0; color: #dddddd; }

    /* メトリックボックス（カード）のデザイン */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr); /* PCは4列 */
        gap: 12px;
        margin-bottom: 20px;
    }

    .metric-card {
        background-color: #1e2129;
        border: 1px solid #3d414b;
        border-radius: 10px;
        padding: 12px;
        text-align: center;
    }

    .metric-label { font-size: 11px; color: #aaaaaa; margin-bottom: 4px; }
    .metric-value { font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 2px; }
    .metric-delta { font-size: 12px; font-weight: 500; }

    /* スマホ(幅640px以下)のレイアウト切り替え */
    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(2, 1fr); /* スマホは2列x4段 */
        }
        .main-title { font-size: 24px; }
        button[data-baseweb="tab"] { font-size: 13px !important; }
    }
    
    /* プラス・マイナスの色 */
    .delta-plus { color: #00f0a8; } /* グリーン */
    .delta-minus { color: #ff4b4b; } /* レッド */
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数 & マッピング ---
MARKET_INDICES = {
    "日経平均": "^N225", "日経先物": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI",
    "原油(WTI)": "CL=F", "Gold": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"
}

# --- 3. 関数定義 ---

@st.cache_data(ttl=600)
def fetch_market_info():
    data = {}
    for name, ticker in MARKET_INDICES.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty and len(df) >= 2:
                latest = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change_pct = ((latest - prev) / prev) * 100
                data[name] = {"val": latest, "pct": change_pct}
            else: data[name] = {"val": None, "pct": None}
        except: data[name] = {"val": None, "pct": None}
    return data

def display_metric_card(name, val, pct):
    """カスタムカードを表示する関数"""
    if val is None:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{name}</div>
                <div class="metric-value">取得失敗</div>
                <div class="metric-delta">---</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        delta_class = "delta-plus" if pct >= 0 else "delta-minus"
        val_formatted = f"{val:,.0f}" if val > 100 else f"{val:,.2f}"
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{name}</div>
                <div class="metric-value">{val_formatted}</div>
                <div class="metric-delta {delta_class}">{pct:+.2f}%</div>
            </div>
        """, unsafe_allow_html=True)

# --- 4. サイドバー ---
st.sidebar.subheader("🛡️ 戦略プリセット")
col_p1, col_p2, col_p3 = st.sidebar.columns(3)
if col_p1.button("通常"): st.session_state['preset'] = "NORMAL"
if col_p2.button("防御"): st.session_state['preset'] = "DEFENSIVE"
if col_p3.button("横這"): st.session_state['preset'] = "RANGE"

st.sidebar.divider()
st.sidebar.subheader("⚙️ BACK TESTER 設定")
days_back = st.sidebar.slider("過去日数", 10, 59, 59)
trailing_start = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5) / 100
stop_loss = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.7) / 100

# --- 5. メインレイアウト ---
st.markdown("<div class='main-title'>FORE CASTER</div>", unsafe_allow_html=True)

# 共通銘柄入力
if 'target_tickers' not in st.session_state:
    st.session_state['target_tickers'] = "8306.T, 7011.T"
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード", value=st.session_state['target_tickers'])

tab_top, tab_screen, tab_bt = st.tabs(["ワンタッチ", "スクリーニング", "バックテスト"])

# --- タブ1: ワンタッチ ---
with tab_top:
    col_head_l, col_head_r = st.columns([0.8, 0.2])
    with col_head_l:
        st.markdown("<div class='section-header'>🌍 リアルタイム指標</div>", unsafe_allow_html=True)
    with col_head_r:
        if st.button("🔄 更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # 指標カードの表示（Expanderは外しました。常にサッと見れるようにするためです）
    m_info = fetch_market_info()
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    
    # HTMLのグリッドを構築するため、StreamlitのcolumnsではなくHTMLで一気に書き出すか、
    # 制御を細かくするためにカード単位で関数を呼び出します。
    # ここではStreamlitのレイアウト制御を使いつつ、CSSクラスを当てます。
    
    # PC4列 / スマホ2列を実現するためのカスタムコンテナ
    cols = st.columns(4) # PC基準
    idx = 0
    for name, info in m_info.items():
        with cols[idx % 4]:
            display_metric_card(name, info["val"], info["pct"])
        idx += 1
    st.markdown('</div>', unsafe_allow_html=True)

    # AI予測 (VIXベース)
    vix_val = m_info.get("VIX指数", {}).get("val", 0)
    if vix_val and vix_val > 20:
        st.warning(f"🤖 **AI予測:** VIX高め。地合いは不安定。")
    elif vix_val and vix_val < 15:
        st.info(f"🤖 **AI予測:** 市場は極めて安定。順張り好機。")
    else:
        st.info("🤖 **AI予測:** 指標は中立。テクニカルに従いましょう。")

    st.divider()
    st.markdown("<div class='section-header'>🚀 One-Touch 期待値スキャン</div>", unsafe_allow_html=True)
    if st.button("主要銘柄から期待値Top5を自動抽出", type="primary", use_container_width=True):
        st.write("※分析エンジン準備中...")
        st.session_state['target_tickers'] = "6920.T, 7011.T, 8306.T, 7013.T, 6758.T"
        st.rerun()
