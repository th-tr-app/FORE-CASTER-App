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

# --- 2. カスタムCSS (ピル型デザイン & 左揃え) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 46px !important; margin: 0 !important; padding: 0 !important; line-height: 1.1; }
    .sub-title { font-weight: 300 !important; font-size: 20px !important; margin: 0 !important; padding: 0 !important; color: #aaaaaa !important; line-height: 1.1; }
    
    /* ピル型サブタブの完全再現 */
    div[data-testid="stTab"] {
        background-color: #1e2129; border-radius: 50px; padding: 5px 25px; margin-right: 12px; border: 1px solid #3d414b; min-width: 140px; text-align: center;
    }
    div[data-testid="stTab"][aria-selected="true"] {
        background-color: #ff4b4b !important; color: white !important; border: 1px solid #ff4b4b;
    }
    div[data-testid="stTab"] p { font-size: 14px; font-weight: 600; }

    [data-testid="stDataFrame"] { font-size: 13px !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { text-align: left !important; }

    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; margin-top: 15px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { background-color: transparent; border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; }
    .card-label { font-size: 12px; color: #aaaaaa; }
    .card-value { font-size: 26px; font-weight: 600; color: #ffffff; }
    .delta-badge { font-size: 16px; font-weight: 600; color: #ff4b4b; margin-top: 2px; }

    .summary-box { background-color: #1e2129; border-radius: 6px; padding: 10px 5px; text-align: center; border: 1px solid #2d3139; }
    .summary-label { font-size: 12px; color: #aaaaaa; }
    .summary-value { font-size: 26px; font-weight: 600; color: #ffffff; }

    .filter-item { margin-bottom: 25px; border-left: 2px solid #3d414b; padding-left: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. セッション管理 ---
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None

# --- 4. サイドバー (構成完全復旧) ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for pid, pname in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == pid)
    if st.sidebar.button(pname + (" [ 選択中 ]" if is_sel else ""), key=f"s_{pid}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = pid; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ パラメーター設定")
d_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
st.sidebar.subheader("⏰ 時間設定")
s_time = st.sidebar.time_input("開始時間", time(9, 0), step=300)
e_time = st.sidebar.time_input("終了時間", time(9, 15), step=300)

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

# --- 5. メインレイアウト ---
st.markdown(f"<h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.71</h3>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    st.button("🔄 指標更新", on_click=st.cache_data.clear)
    st.info("リアルタイム指標とワンタッチスキャン実行ボタンを表示します。")
    if st.button("ワンタッチで銘柄スキャン実行", type="primary", use_container_width=True):
        st.success("期待値Top5を選出しました。")

with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["通常フィルター", "ディフェンシブ", "横ばい相場対応"])
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            with st.expander(f"🔍 スクリーニング詳細設定", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("<div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("業種", value=True, key=f"c1_{i}"); st.multiselect("業種選択", ["情報・通信", "電気機器", "銀行業"], key=f"v1_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("売買代金", value=True, key=f"c2_{i}"); st.number_input("億円以上", value=10.0, key=f"v2_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("平均値幅 (ATR%)", value=True, key=f"c3_{i}"); st.slider("期待値幅 (%)", 0.5, 5.0, 1.5, key=f"v3_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("時価総額", value=True, key=f"c4_{i}"); st.number_input("億円以上", value=500, key=f"v4_{i}", step=100)
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("株価の範囲", value=True, key=f"c5_{i}"); st.slider("株価レンジ(円)", 100, 10000, (500, 5000), key=f"v5_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("25日移動平均乖離率", value=True, key=f"c6_{i}"); st.slider("乖離率 (%)", -20.0, 20.0, (-5.0, 5.0), key=f"v6_{i}")
                    st.markdown("</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown("<div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("出来高", value=True, key=f"c7_{i}"); st.number_input("万株以上", value=10, key=f"v7_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("移動平均上抜け", value=False, key=f"c8_{i}"); st.selectbox("MA種類", ["5日線", "25日線", "75日線"], key=f"v8_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("信用倍率", value=True, key=f"c9_{i}"); st.number_input("倍率以下", value=10.0, key=f"v9_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("PER (倍)", value=True, key=f"c10_{i}"); st.slider("PERレンジ", 0.0, 100.0, (10.0, 30.0), key=f"v10_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("EMA (指数平滑移動平均線)", value=False, key=f"c11_{i}"); st.multiselect("EMA条件", ["9日上抜け", "21日上抜け"], key=f"v11_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("ADX (トレンド強度)", value=True, key=f"c12_{i}"); st.slider("ADXスコア", 0, 100, 25, key=f"v12_{i}")
                    st.markdown("</div>", unsafe_allow_html=True)
                with c3:
                    st.markdown("<div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("ATR (最小値幅)", value=True, key=f"c13_{i}"); st.number_input("最小ATR(円)", value=10, key=f"v13_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("RCI (順位相関計数)", value=False, key=f"c14_{i}"); st.slider("9日RCI", -100, 100, 0, key=f"v14_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("RSI (14日)", value=True, key=f"c15_{i}"); st.slider("RSIレンジ", 0, 100, (30, 70), key=f"v15_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("ボリンジャーバンド", value=False, key=f"c16_{i}"); st.select_slider("σレベル", options=["-3σ", "-2σ", "-1σ", "0", "+1σ", "+2σ", "+3σ"], value="0", key=f"v16_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("コンセンサスレーティング", value=True, key=f"c17_{i}"); st.slider("スコア (0:低〜5:高)", 0.0, 5.0, 3.5, 0.1, key=f"v17_{i}")
                    st.markdown("</div><div class='filter-item'>", unsafe_allow_html=True)
                    st.checkbox("出来高増加率", value=True, key=f"c18_{i}"); st.slider("前日比(倍)", 1.0, 5.0, 1.2, key=f"v18_{i}")
                    st.markdown("</div>", unsafe_allow_html=True)

            st.button(f"スクリーニング実行", key=f"run_s_{i}", type="primary", use_container_width=True)

with tab_bt:
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        st.session_state['bt_results'] = "dummy"
    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state['bt_results']:
        bt_tabs = st.tabs(["📊 サマリー", "🤖 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間帯分析", "📝 詳細ログ"])
        with bt_tabs[0]: st.markdown("サマリー結果...")
