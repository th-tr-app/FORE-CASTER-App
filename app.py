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

# --- 2. カスタムCSS (Ver 1.81 デザイン完全継承) ---
# ... (以前のCSSをそのまま維持してください)
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

# --- 3. マッピング & セッション管理 (短縮版) ---
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

# --- 4. 関数定義 (戻り値強化版) ---

# 【修正】勝率・PFも算出するようにエンジンを拡張
def run_scan_engine(ticker, days_back, entry_start, entry_end, use_vwap):
    try:
        df = yf.download(ticker, period="1mo", interval="5m", progress=False, auto_adjust=False)
        if df.empty: return None
        df.index = df.index.tz_convert('Asia/Tokyo'); pnls = []
        for d in np.unique(df.index.date)[-days_back:]:
            day = df[df.index.date == d].copy().between_time('09:00', '15:00')
            if day.empty: continue
            day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum()
            in_pos = False
            for ts, row in day.iterrows():
                if not in_pos and entry_start <= ts.time() <= entry_end:
                    if not use_vwap or (row['Close'] > row['VWAP']): entry_p = row['Close'] * 1.0003; in_pos = True
                elif in_pos:
                    if row['Low'] <= entry_p * 0.992 or ts.time() >= time(14, 55):
                        exit_p = row['Close'] * 0.9997; pnls.append((exit_p - entry_p) / entry_p); in_pos = False; break
        
        if not pnls: return None
        # 詳細統計の計算
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls)
        pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else (9.99 if wins else 0.0)
        return {"ev": np.mean(pnls), "win_rate": win_rate, "pf": pf}
    except: return None

# ... (fetch_market_info, fetch_daily_stats_maps, calculate_rci, run_full_scan_engine は維持)

# --- 6. メインレイアウト ---
st.markdown(f"<div style='margin-bottom: 20px;'><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>SCREENING & BACKTEST | ver 1.98</h3></div>", unsafe_allow_html=True)
ticker_input = st.text_input("🎯 監視銘柄コード", st.session_state['target_tickers'])
st.session_state['target_tickers'] = ticker_input
tab_top, tab_screen, tab_bt = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト"])

# --- タブ1: ワンタッチ (勝率・PF表示対応版) ---
with tab_top:
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    m_data = fetch_market_info()
    with st.expander(f"🕒 指標ウォッチ ▶︎ ({now_jst})", expanded=True):
        if st.button("🔄 リアルタイム更新"): st.cache_data.clear(); st.rerun()
        # ... (指標表示カードのHTML)

    if st.button("ワンタッチで銘柄スキャン", type="primary", use_container_width=True):
        res_list = []; prg = st.progress(0); status_text = st.empty()
        tks = list(TICKER_NAME_MAP.keys())
        for idx, t in enumerate(tks):
            status_text.text(f"🔍 解析中 ({idx+1}/{len(tks)}): {t}")
            prg.progress((idx + 1) / len(tks))
            stats = run_scan_engine(t, 20, time(9,0), time(9,30), True) # 戻り値が辞書になった
            if stats and stats['ev'] > 0:
                res_list.append({
                    "コード": t, "銘柄名": TICKER_NAME_MAP[t], 
                    "期待値": stats['ev'], "勝率": stats['win_rate'], "PF": stats['pf']
                })
        status_text.empty(); prg.empty()
        if res_list:
            top5 = sorted(res_list, key=lambda x: x['期待値'], reverse=True)[:5]
            display_data = []
            for d in top5:
                display_data.append({
                    "コード": d["コード"], "銘柄名": d["銘柄名"],
                    "勝率": f"{d['勝率']:.1%}", "PF": f"{d['PF']:.2f}", "期待値": f"{d['期待値']:+.2%}"
                })
            st.session_state['scan_display_df'] = pd.DataFrame(display_data)
            st.session_state['target_tickers'] = ", ".join([d['コード'] for d in top5])
            st.rerun()
        else: st.warning("推奨銘柄は見つかりませんでした。")

    if 'scan_display_df' in st.session_state:
        st.success(f"🎯 本日のポテンシャル上位銘柄を選出しました。")
        st.dataframe(st.session_state['scan_display_df'], hide_index=True, use_container_width=True)
        st.info("上位銘柄を「監視銘柄コード」に自動セットしました。詳細分析は「バックテスト」タブで実行してください。")
        if st.button("スキャン結果をクリア"):
            del st.session_state['scan_display_df']; st.rerun()

# --- タブ2: スクリーニング ---
# ... (前回のスクリーニング設定を維持してください)

# --- タブ3: バックテスト (指示通りの位置で停止) ---
with tab_bt:
    t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
    if st.button("バックテスト実行", type="primary", use_container_width=True):
        st.info("バックテストを実行します...")
