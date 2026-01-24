import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from datetime import datetime, timedelta, time, timezone

# --- 1. ユーティリティ ---
def calculate_rci(series, period=9):
    def get_rci(sub):
        n = len(sub)
        d = ((np.arange(n) + 1) - sub.rank(ascending=False)).pow(2).sum()
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(get_rci)

def get_trade_pattern(row, gap_pct):
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

# --- 2. 市場分析 (main.pyとの連携用) ---
@st.cache_data(ttl=300)
def fetch_market_info(indices_dict):
    data = {}
    for name, ticker in indices_dict.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df = df.dropna(subset=['Close'])
                latest = float(df['Close'].values.ravel()[-1])
                prev = float(df['Close'].values.ravel()[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=300)
def analyze_market_environment():
    """時刻に合わせて診断を切り替える (統合版)"""
    indices = {"N225": "^N225", "VIX": "^VIX", "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F", "USDJPY": "JPY=X", "GOLD": "GC=F"}
    data_map = {}
    for k, ticker in indices.items():
        try:
            df = yf.download(ticker, period="40d", interval="1d", progress=False)
            if not df.empty and len(df) >= 2:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                data_map[k] = df.dropna(subset=['Close'])
        except: continue

    n225_c = 0; n225_ma = 0; cme_v = 0
    if "N225" in data_map:
        df_n = data_map["N225"]
        n225_c = float(df_n['Close'].values.ravel()[-1])
        n225_ma = float(df_n['Close'].rolling(25).mean().values.ravel()[-1])
    if "CME" in data_map: cme_v = float(data_map["CME"]['Close'].values.ravel()[-1])

    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).time()
    l_s, l_e = time(11, 30), time(12, 30)
    a_s, a_e = time(15, 0), time(19, 0)

    gap_pct = (cme_v - n225_c) / n225_c if n225_c > 0 else 0
    strategy_idx = 2; f_title = "寄付予測"; base_f = "フラット"
    if gap_pct <= -0.0015:
        strategy_idx = 1; base_f = "大幅下落" if gap_pct <= -0.01 else "下落"
    elif gap_pct >= 0.0015:
        strategy_idx = 0; base_f = "大幅上昇" if gap_pct >= 0.01 else "上昇"

    bias_list = []
    if l_s <= now <= l_e:
        f_title = "前場の総括"
        f_txt = f"前場は {base_f} で推移。25日線乖離は {((n225_c - n225_ma) / n225_ma) * 100:.1f}% です。"
        p_txt = "前場のトレンドを再確認。後場はVWAP付近の攻防や前場高値更新に注目。"
    elif a_s <= now <= a_e:
        f_title = "今日の結果"
        f_txt = f"本日は {base_f} で終了。現在の25日線乖離は {((n225_c - n225_ma) / n225_ma) * 100:.1f}% です。"
        p_txt = "本日のトレードお疲れ様でした。明日に向け期待値の高い銘柄を精査しましょう。"
    else:
        if "USDJPY" in data_map:
            fx_p = (data_map["USDJPY"]['Close'].values.ravel()[-1] / data_map["USDJPY"]['Close'].values.ravel()[-2]) - 1
            if fx_p <= -0.003: bias_list.append("円高バイアス")
            elif fx_p >= 0.003: bias_list.append("円安バイアス")
        f_txt = f"{base_f}寄付 ({' / '.join(bias_list)})" if bias_list else f"{base_f}寄付"
        p_txt = "市場は比較的落ち着いています。テクニカル重視のトレードを。"

    dev_25 = ((n225_c - n225_ma) / n225_ma) * 100 if n225_ma > 0 else 0
    balance_txt = f"【均衡】25日線乖離 {dev_25:.1f}%。正常範囲内です。"
    alert_lvl = "正常範囲（ニュートラル）"
    if dev_25 > 5:
        balance_txt = f"【加熱】25日線乖離 +{dev_25:.1f}%。高値警戒。"; alert_lvl = "⚠️ 高値警戒"
    elif dev_25 < -5:
        balance_txt = f"【過売】25日線乖離 {dev_25:.1f}%。自律反発圏。"; alert_lvl = "📢 底打ち待ち"

    sox_p = 0; vix_v = 15
    if "SOX" in data_map: sox_p = (data_map["SOX"]['Close'].values.ravel()[-1] / data_map["SOX"]['Close'].values.ravel()[-2]) - 1
    if "VIX" in data_map: vix_v = data_map["VIX"]['Close'].values.ravel()[-1]
    
    if vix_v >= 20 or sox_p <= -0.015: u_impact = "半導体株中心に強い売り圧力。指数主導の下落に警戒。"
    elif sox_p >= 0.005: u_impact = "ハイテク株への買い波及期待。主力大型株の底堅い展開を予想。"
    else: u_impact = "米国株の変動は限定的。日本独自の材料が優先される展開。"

    tips = []
    if "WTI" in data_map and (data_map["WTI"]['Close'].values.ravel()[-1] / data_map["WTI"]['Close'].values.ravel()[-2]) - 1 >= 0.005: tips.append("1:鉱業 / 10:石油・石炭")
    if "GOLD" in data_map and (data_map["GOLD"]['Close'].values.ravel()[-1] / data_map["GOLD"]['Close'].values.ravel()[-2]) - 1 >= 0.005: tips.append("9:非鉄金属")
    if sox_p >= 0.005: tips.append("17:電気機器 / 16:機械")
    if vix_v >= 20: tips.append("2:水産・食品 / 12:医薬品")

    return {
        "strategy": strategy_idx, "opening_forecast": f_txt, "forecast_title": f_title,
        "balance": balance_txt, "phase_comment": p_txt, "us_impact": u_impact, 
        "alert_level": alert_lvl, "tips": " / ".join(tips) if tips else "個別材料株（全業種対象）"
    }

# --- 3. スクリーニング・シミュレーション (関数定義) ---
def evaluate_screening_conditions(df, params):
    if df.empty or len(df) < 30: return None
    try:
        p = float(df['Close'].values.ravel()[-1]); v = float(df['Volume'].values.ravel()[-1])
        prev_p = float(df['Close'].values.ravel()[-2]); gain = ((p - prev_p) / prev_p) * 100
        val_total = (p * v) / 100000000
        return {"株価": int(p), "前日比": gain, "売買代金": val_total, "出来高": int(v), "RSI": 50, "25MA乖離": 0, "ATR%": 0}
    except: return None

def fetch_daily_stats_maps(ticker, start): return {}, {}, {}
def run_ticker_simulation(ticker, df, pc_map, co_map, a_map, params): return []
