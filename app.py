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

# --- 2. カスタムCSS (デザイン完全継承) ---
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
    .ai-box { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; margin: 15px 0; }
    div[data-testid="stCheckbox"] label p { font-size: 14px !important; }
    .stSidebar [data-testid="stVerticalBlock"] button { width: 100%; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. マッピング & セッション管理 (230銘柄・短縮版) ---
TICKER_NAME_MAP = {
    # 水産・食品
    "1332.T": "ニッスイ", "2002.T": "日清粉G", "2269.T": "明治HD", "2282.T": "日本ハム", "2501.T": "サッポロHD",
    "2502.T": "アサヒG", "2503.T": "キリンHD", "2801.T": "キッコーマン", "2802.T": "味の素", "2871.T": "ニチレイ", "2914.T": "JT",
    # 繊維・化学
    "3101.T": "東洋紡", "3103.T": "ユニチカ", "3401.T": "帝人", "3402.T": "東レ", "3861.T": "王子HD", "3863.T": "日本製紙",
    "4004.T": "レゾナック", "4005.T": "住友化学", "4021.T": "日産化学", "4042.T": "東ソー", "4043.T": "トクヤマ",
    "4061.T": "デンカ", "4063.T": "信越化学", "4151.T": "協和キリン", "4183.T": "三井化学", "4188.T": "三菱ケミＧ",
    "4208.T": "ＵＢＥ", "4452.T": "花王", "4901.T": "富士フイルム", "4911.T": "資生堂",
    "4502.T": "武田薬品", "4503.T": "アステラス製薬", "4506.T": "住友ファーマ", "4507.T": "塩野義製薬", "4519.T": "中外製薬",
    "4523.T": "エーザイ", "4543.T": "テルモ", "4568.T": "第一三共", "4578.T": "大塚ＨＤ",
    # 石油・ゴム・金属
    "5019.T": "出光興産", "5020.T": "ＥＮＥＯＳ", "5101.T": "横浜ゴム", "5108.T": "ブリヂストン",
    "5201.T": "ＡＧＣ", "5202.T": "日本板硝子", "5232.T": "住友大阪セメント", "5233.T": "太平洋セメント", "5301.T": "東海カーボン",
    "5332.T": "ＴＯＴＯ", "5333.T": "日本碍子", "5401.T": "日本製鉄", "5406.T": "神戸製鋼所", "5411.T": "ＪＦＥ",
    "5541.T": "大平洋金属", "5631.T": "日本製鋼所", "5706.T": "三井金属", "5711.T": "三菱マテリアル", "5713.T": "住友金属鉱山",
    "5714.T": "ＤＯＷＡ", "5801.T": "古河電気工業", "5802.T": "住友電気工業", "5803.T": "フジクラ",
    # 機械・電機
    "6098.T": "リクルート", "6103.T": "オークマ", "6113.T": "アマダ", "6146.T": "ディスコ", "6273.T": "ＳＭＣ",
    "6301.T": "小松製作所", "6302.T": "住友重機械", "6305.T": "日立建機", "6326.T": "クボタ", "6361.T": "荏原製作所",
    "6367.T": "ダイキン工業", "6471.T": "日本精工", "6472.T": "ＮＴＮ", "6473.T": "ジェイテクト", "6479.T": "ミネベアミツミ",
    "6501.T": "日立", "6503.T": "三菱電機", "6504.T": "富士電機", "6506.T": "安川電機", "6594.T": "ニデック",
    "6645.T": "オムロン", "6701.T": "日本電気", "6702.T": "富士通", "6723.T": "ルネサス", "6724.T": "セイコーエプソン",
    "6752.T": "パナソニック", "6753.T": "シャープ", "6758.T": "ソニーグループ", "6762.T": "ＴＤＫ", "6770.T": "アルプスアルパイン",
    "6841.T": "横河電機", "6857.T": "アドバンテスト", "6902.T": "デンソー", "6920.T": "レーザーテック", "6952.T": "カシオ",
    "6954.T": "ファナック", "6971.T": "京セラ", "6976.T": "太陽誘電", "6981.T": "村田製作所", "6988.T": "日東電工", "7735.T": "SCREEN",
    # 輸送・精密
    "7011.T": "三菱重工業", "7012.T": "川崎重工業", "7013.T": "ＩＨＩ", "7186.T": "横浜ＦＧ", "7201.T": "日産自動車",
    "7202.T": "いすゞ自動車", "7203.T": "トヨタ自動車", "7205.T": "日野自動車", "7211.T": "三菱自動車工業", "7261.T": "マツダ",
    "7267.T": "本田技研工業", "7269.T": "スズキ", "7270.T": "ＳＵＢＡＲＵ", "7272.T": "ヤマハ発動機",
    "7731.T": "ニコン", "7733.T": "オリンパス", "7741.T": "ＨＯＹＡ", "7751.T": "キヤノン", "7752.T": "リコー", "7762.T": "シチズン時計",
    # 商社・金融・不動産・サービス・通信
    "1721.T": "コムシスHD", "1801.T": "大成建設", "1802.T": "大林組", "1803.T": "清水建設", "1808.T": "長谷工", "1812.T": "鹿島建設",
    "1925.T": "大和ハウス", "1928.T": "積水ハウス", "1963.T": "日揮HD", "8001.T": "伊藤忠", "8002.T": "丸紅", "8015.T": "豊田通商",
    "8031.T": "三井物産", "8035.T": "東京エレクトロン", "8053.T": "住友商事", "8058.T": "三菱商事", "8233.T": "高島屋", "8252.T": "丸井グループ",
    "8253.T": "クレディセゾン", "8267.T": "イオン", "8304.T": "あおぞら銀行", "8306.T": "三菱ＵＦＪ", "8308.T": "りそなＨＤ",
    "8309.T": "三井住友トラスト", "8316.T": "三井住友ＦＧ", "8331.T": "千葉銀行", "8354.T": "ふくおかＦＧ", "8411.T": "みずほＦＧ",
    "8591.T": "オリックス", "8601.T": "大和証券Ｇ", "8604.T": "野村ＨＤ", "8630.T": "ＳＯＭＰＯ", "8725.T": "ＭＳ＆ＡＤ",
    "8750.T": "第一生命ＨＤ", "8766.T": "東京海上", "8795.T": "Ｔ＆Ｄ", "8801.T": "三井不動産", "8802.T": "三菱地所", "8804.T": "東京建物",
    "8830.T": "住友不動産", "2413.T": "エムスリー", "2432.T": "ディーエヌエー", "4307.T": "野村総研", "4324.T": "電通グループ",
    "4661.T": "ＯＬＣ", "4689.T": "ラインヤフー", "4704.T": "トレンド", "4751.T": "サイバーエージェント", "4755.T": "楽天グループ",
    "9001.T": "東武鉄道", "9005.T": "東急", "9007.T": "小田急電鉄", "9008.T": "京王電鉄", "9009.T": "京成電鉄", "9020.T": "ＪＲ東日本",
    "9021.T": "ＪＲ西日本", "9022.T": "ＪＲ東海", "9101.T": "日本郵船", "9104.T": "商船三井", "9107.T": "川崎汽船", "9201.T": "日本航空",
    "9202.T": "ＡＮＡ", "9301.T": "三菱倉庫", "9432.T": "ＮＴＴ", "9433.T": "ＫＤＤＩ", "9434.T": "ソフトバンク", "9501.T": "東電ＨＤ",
    "9502.T": "中部電力", "9503.T": "関西電力", "9531.T": "東京瓦斯", "9532.T": "大阪瓦斯", "9602.T": "東宝", "9735.T": "セコム",
    "9766.T": "コナミＧ", "9843.T": "ニトリＨＤ", "9983.T": "ファーストリテイリング", "9984.T": "ソフトバンクグループ", "4062.T": "イビデン",
    "3697.T": "ＳＨＩＦＴ", "6532.T": "ベイカレント", "9613.T": "ＮＴＴデータ", "6963.T": "ローム", "2768.T": "双日", "5831.T": "しずおかＦＧ",
    # 追加銘柄
    "4403.T": "日油", "6315.T": "TOWA", "3436.T": "SUMCO", "7003.T": "三井E&S", "1570.T": "日経レバ"
}

MARKET_INDICES = {"日経平均": "^N225", "日経先物(CME)": "NIY=F", "ドル/円": "JPY=X", "NYダウ30種": "^DJI", "原油先物(WTI)": "CL=F", "Gold先物(COMEX)": "GC=F", "VIX指数": "^VIX", "SOX指数": "^SOX"}

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'bt_results' not in st.session_state: st.session_state['bt_results'] = None

# --- 4. 関数定義 (計算エンジン ＋ スクリーニングエンジン) ---
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

def calculate_rci(series, period=9):
    def get_rci(sub):
        n = len(sub); d = ((np.arange(n) + 1) - sub.rank(ascending=False)).pow(2).sum()
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(get_rci)

def run_full_scan_engine(params):
    results = []; all_tickers = list(TICKER_NAME_MAP.keys())
    prg = st.progress(0); status_text = st.empty()
    for idx, t in enumerate(all_tickers):
        name = TICKER_NAME_MAP.get(t, t)
        status_text.text(f"🔍 スキャン中 ({idx+1}/{len(all_tickers)}): [{t}] {name}")
        prg.progress((idx + 1) / len(all_tickers))
        try:
            df = yf.download(t, period="3mo", interval="1d", progress=False)
            if df.empty or len(df) < 25: continue
            if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)
            p = df['Close'].iloc[-1]; v = df['Volume'].iloc[-1]; ma25 = df['Close'].rolling(25).mean().iloc[-1]
            atrp = (AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().iloc[-1] / p) * 100
            adx = ADXIndicator(df['High'], df['Low'], df['Close']).adx().iloc[-1]
            rsi = RSIIndicator(df['Close'], 14).rsi().iloc[-1]
            rci = calculate_rci(df['Close'], 9).iloc[-1]
            ma25_dev = ((p - ma25) / ma25) * 100; val_total = (p * v) / 100000000; vup_rate = v / df['Volume'].rolling(5).mean().iloc[-2]
            match = True
            if params['c_p'] and not (params['p_range'][0] <= p <= params['p_range'][1]): match = False
            if params['c_v'] and val_total < params['v_min']: match = False
            if params['c_atrp'] and not (params['atrp_range'][0] <= atrp <= params['atrp_range'][1]): match = False
            if params['c_adx'] and not (params['adx_range'][0] <= adx <= params['adx_range'][1]): match = False
            if params['c_rsi'] and not (params['rsi_range'][0] <= rsi <= params['rsi_range'][1]): match = False
            if params['c_rci'] and not (params['rci_range'][0] <= rci <= params['rci_range'][1]): match = False
            if params['c_vol'] and (v / 10000) < params['vol_min']: match = False
            if params['c_vup'] and vup_rate < params['vup_min']: match = False
            if params['c_ma25'] and not (params['ma25_range'][0] <= ma25_dev <= params['ma25_range'][1]): match = False
            if match: results.append({"コード": t, "銘柄名": name, "株価": f"{int(p)}", "売買代金": f"{val_total:.1f}億", "前日比倍": f"{vup_rate:.2f}", "RSI": f"{rsi:.1f}"})
        except: continue
    prg.empty(); status_text.empty()
    return pd.DataFrame(results)

# --- 5. サイドバー ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    if st.sidebar.button(l + (" [ 選択中 ]" if is_sel else ""), key=f"ps_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p; st.rerun()

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.94</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

with tab_top:
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    with st.expander(f"🕒 指標チェック ▶︎ ({now_jst})", expanded=True):
        if st.button("🔄 リアルタイム更新"): st.cache_data.clear(); st.rerun()
        # ... (指標表示HTML)
    if st.button("ワンタッチで銘柄スキャン", type="primary", use_container_width=True):
        st.info("スキャン機能を準備中...")

# --- タブ2: スクリーニング (精密調整版) ---
with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["🔍通常フィルタ", "🔍ディフェンシブ", "🔍横ばい相場"])
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            # タブごとのデフォルト値表示用テキスト
            v_val = "50" if i==0 else "300" if i==1 else "200"
            atrp_v = "2.0~4.0" if i==0 else "1.0~2.5" if i==1 else "1.2~2.5"
            adx_v = "25~40" if i==0 else "10~20" if i==1 else "10~20"
            rci_v = "20~80" if i==0 else "-20~30" if i==1 else "-30~30"
            rsi_v = "55~70" if i==0 else "40~55" if i==1 else "45~55"
            vol_v = "10" if i==0 else "20" if i==1 else "10"
            vup_v = "1.3" if i==0 else "1.1" if i==1 else "1.2"
            ma25_v = "0.0~7.0" if i==0 else "-3.0~2.0" if i==1 else "-2.0~3.0"
            bb_v = "1.0~2.0" if i==0 else "-1.0~0.0" if i==1 else "1.0~2.0"

            exp_t = f"🔍 スクリーニング設定 ({['通常', 'ディフェンシブ', '横ばい'][i]})"
            with st.expander(exp_t, expanded=False): # 初期状態を閉じる
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.checkbox("**株価の範囲 (500~5000円)**", True, key=f"c_p_{i}")
                    st.caption("予算に合わせたフィルタリング")
                    p_range = st.slider("価格(円)", 100, 10000, (500, 5000), step=100, key=f"v_p_{i}") # 単位: 100
                    st.checkbox(f"**売買代金 ({v_val}億円以上)**", True, key=f"c_v_{i}")
                    st.caption("株価 × 出来高")
                    v_min = st.number_input("億円以上", value=float(v_val), step=10.0, key=f"v_v_{i}") # 単位: 10
                    st.checkbox(f"**平均値幅 (ATR% {atrp_v}%)**", True, key=f"c_atrp_{i}")
                    st.caption("ボラティリティの強さ")
                    atrp_range = st.slider("期待範囲%", 0.5, 5.0, (2.0, 4.0) if i==0 else (1.0, 2.5) if i==1 else (1.2, 2.5), step=0.5, key=f"v_atrp_{i}") # 単位: 0.5
                    st.checkbox("**移動平均上抜け/並び**", False, key=f"c_ma_{i}")
                    st.caption("5MA/10MA/25MAの相関")
                    ma_opt = st.selectbox("条件選択", ["最強：上昇トレンド", "転換：GC直後", "収束：嵐の前の静けさ", "リバウンド：短期MA上抜け"], index=0 if i==0 else 2 if i==1 else 3, key=f"v_ma_{i}")
                with c2:
                    st.checkbox("**EMA (9日・21日)**", False, key=f"c_ema_{i}")
                    st.caption("直近の価格トレンド")
                    ema_opt = st.selectbox("EMA基準", ["強気：EMAの上で価格維持", "安定：EMA付近での推移", "レンジ：EMAを上下にまたぐ"], index=0 if i==0 else 1 if i==1 else 2, key=f"v_ema_{i}")
                    st.checkbox(f"**ADX (強度 {adx_v})**", True, key=f"c_adx_{i}")
                    st.caption("トレンドの強弱")
                    adx_range = st.slider("強度スコア", 0, 100, (25, 40) if i==0 else (10, 20), step=5, key=f"v_adx_{i}") # 単位: 5
                    st.checkbox(f"**RCI (過熱感 {rci_v})**", True, key=f"c_rci_{i}")
                    st.caption("価格の過熱感：カスタム計算")
                    rci_range = st.slider("RCI範囲", -100, 100, (20, 80) if i==0 else (-20, 30) if i==1 else (-30, 30), step=5, key=f"v_rci_{i}") # 単位: 5
                    st.checkbox(f"**RSI (レンジ {rsi_v})**", True, key=f"c_rsi_{i}")
                    st.caption("相対的な買われすぎ・売られすぎ")
                    rsi_range = st.slider("RSIレンジ", 0, 100, (55, 70) if i==0 else (40, 55) if i==1 else (45, 55), step=5, key=f"v_rsi_{i}") # 単位: 5
                with c3:
                    st.checkbox(f"**出来高 ({vol_v}万株以上)**", True, key=f"c_vol_{i}")
                    st.caption("最低限の流動性確保")
                    vol_min = st.number_input("万株以上", value=float(vol_v), step=10.0, key=f"v_vol_{i}") # 単位: 10
                    st.checkbox(f"**出来高増加率 ({vup_v}倍以上)**", True, key=f"c_vup_{i}")
                    st.caption("前日比での注目度アップ")
                    vup_min = st.slider("増加倍率", 1.0, 5.0, float(vup_v), step=0.1, key=f"v_vup_{i}") # 単位: 0.1
                    st.checkbox(f"**25日移動平均乖離率 ({ma25_v}%)**", True, key=f"c_ma25_{i}")
                    st.caption("中長期トレンドからの乖離")
                    ma25_range = st.slider("偏差%", -20.0, 20.0, (0.0, 7.0) if i==0 else (-3.0, 2.0) if i==1 else (-2.0, 3.0), step=1.0, key=f"v_ma25_{i}") # 単位: 1
                    st.checkbox(f"**ボリンジャーバンド ({bb_v}σ)**", False, key=f"c_bb_{i}")
                    st.caption("α範囲による逆張り・順張り目安")
                    bb_range = st.slider("σ範囲", -3.0, 3.0, (1.0, 2.0) if i==0 else (-1.0, 0.0) if i==1 else (1.0, 2.0), step=1.0, key=f"v_bb_{i}") # 単位: 1
            
            if st.button("スクリーニング実行", key=f"run_s_{i}", type="primary", use_container_width=True):
                p_dict = {'c_p': c_p, 'p_range': p_range, 'c_v': c_v, 'v_min': v_min, 'c_atrp': c_atrp, 'atrp_range': atrp_range, 'c_adx': c_adx, 'adx_range': adx_range, 'c_rsi': c_rsi, 'rsi_range': rsi_range, 'c_rci': c_rci, 'rci_range': rci_range, 'c_vol': c_vol, 'vol_min': vol_min, 'c_vup': c_vup, 'vup_min': vup_min, 'c_ma25': c_ma25, 'ma25_range': ma25_range}
                res_df = run_full_scan_engine(p_dict)
                if not res_df.empty: st.success(f"合致銘柄: {len(res_df)}件"); st.dataframe(res_df, hide_index=True, use_container_width=True)
                else: st.warning("合致なし")

# --- タブ3: バックテスト (省略) ---
with tab_bt: st.info("バックテストを実行します...")
