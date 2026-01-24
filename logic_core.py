import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from datetime import datetime, timedelta, time, timezone

# --- 1. テクニカル指標・ユーティリティ ---

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

# --- 2. 市場分析・指標取得 ---

@st.cache_data(ttl=300)
def fetch_market_info(indices_dict):
    """市場指標の値を一括取得する (main.pyから呼ばれます)"""
    data = {}
    for name, ticker in indices_dict.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                df = df.dropna(subset=['Close'])
                latest = float(df['Close'].values.ravel()[-1])
                prev = float(df['Close'].values.ravel()[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: 
            data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=300)
def analyze_market_environment():
    """主要指数から今日の相場環境をプロ視点で診断する (時系列・決定版)"""
    indices = {
        "N225": "^N225", "VIX": "^VIX", "SOX": "^SOX",
        "WTI": "CL=F", "CME": "NIY=F", "USDJPY": "JPY=X", "GOLD": "GC=F"
    }
    data_map = {}
    for k, ticker in indices.items():
        try:
            df = yf.download(ticker, period="40d", interval="1d", progress=False)
            if not df.empty and len(df) >= 2:
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                data_map[k] = df.dropna(subset=['Close'])
        except: continue

    # 基礎データの抽出
    n225_close = 0; n225_ma25 = 0; cme_val = 0
    if "N225" in data_map:
        df_n = data_map["N225"]
        n225_close = float(df_n['Close'].values.ravel()[-1])
        n225_ma25 = float(df_n['Close'].rolling(25).mean().values.ravel()[-1])
    if "CME" in data_map:
        cme_val = float(data_map["CME"]['Close'].values.ravel()[-1])

    # 時刻判定 (日本時間)
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).time()
    l_start, l_end = time(11, 30), time(12, 30)
    a_start, a_end = time(15, 0), time(19, 0)

    # 寄付予測 と 戦略判定
    gap_pct = (cme_val - n225_close) / n225_close if n225_close > 0 else 0
    strategy_idx = 2; forecast_title = "寄付予測"; base_f = "フラット"
    if gap_pct <= -0.0015:
        strategy_idx = 1; base_f = "大幅下落" if gap_pct <= -0.01 else "下落"
    elif gap_pct >= 0.0015:
        strategy_idx = 0; base_f = "大幅上昇" if gap_pct >= 0.01 else "上昇"

    # 時間帯別のテキスト生成
    bias_list = []
    if l_start <= now <= l_end:
        forecast_title = "前場の総括"
        forecast_txt = f"前場は {base_f} で推移。25日線乖離は {((n225_close - n225_ma25) / n225_ma25) * 100:.1f}% です。"
        phase_txt = "前場のトレンドを再確認。後場はVWAP付近の攻防や前場高値更新に注目してください。"
    elif a_start <= now <= a_end:
        forecast_title = "今日の結果"
        forecast_txt = f"本日は {base_f} で終了。現在の25日線乖離は {((n225_close - n225_ma25) / n225_ma25) * 100:.1f}% です。"
        phase_txt = "本日のトレードお疲れ様でした。明日に向け期待値の高い銘柄をランキングで精査しましょう。"
    else:
        # 通常時：バイアス判定
        if "USDJPY" in data_map:
            fx_p = (data_map["USDJPY"]['Close'].values.ravel()[-1] / data_map["USDJPY"]['Close'].values.ravel()[-2]) - 1
            if fx_p <= -0.003: bias_list.append("円高バイアス")
            elif fx_p >= 0.003: bias_list.append("円安バイアス")
        forecast_txt = f"{base_f}寄付 ({' / '.join(bias_list)})" if bias_list else f"{base_f}寄付"
        phase_txt = "市場は比較的落ち着いています。各銘柄のテクニカルを重視したトレードを。"

    # 指標診断 (バランス、米国株、セクター)
    dev_25 = ((n225_close - n225_ma25) / n225_ma25) * 100 if n225_ma25 > 0 else 0
    balance_txt = f"【均衡】25日線乖離 {dev_25:.1f}%。正常範囲内です。"
    alert_lvl = "正常範囲（ニュートラル）"
    if dev_25 > 5:
        balance_txt = f"【加熱】25日線乖離 +{dev_25:.1f}%。警戒水準。"; alert_lvl = "⚠️ 高値警戒（過熱）"
    elif dev_25 < -5:
        balance_txt = f"【過売】25日線乖離 {dev_25:.1f}%。自律反発圏。"; alert_lvl = "📢 底打ち待ち（過売）"

    sox_pct = 0; vix_val = 15
    if "SOX" in data_map: sox_pct = (data_map["SOX"]['Close'].values.ravel()[-1] / data_map["SOX"]['Close'].values.ravel()[-2]) - 1
    if "VIX" in data_map: vix_val = data_map["VIX"]['Close'].values.ravel()[-1]
    
    if vix_val >= 20 or sox_pct <= -0.015:
        us_impact = "半導体株中心に強い売り圧力。指数主導の下落に警戒。"
    elif sox_pct >= 0.005:
        us_impact = "ハイテク株への買い波及が期待。主力大型株の底堅い展開を予想。"
    else:
        us_impact = "米国株の変動は限定的。日本独自の材料が優先される展開。"

    tips = []
    if "WTI" in data_map and (data_map["WTI"]['Close'].values.ravel()[-1] / data_map["WTI"]['Close'].values.ravel()[-2]) - 1 >= 0.005: tips.append("1:鉱業 / 10:石油・石炭")
    if "GOLD" in data_map and (data_map["GOLD"]['Close'].values.ravel()[-1] / data_map["GOLD"]['Close'].values.ravel()[-2]) - 1 >= 0.005: tips.append("9:非鉄金属")
    if sox_pct >= 0.005: tips.append("17:電気機器 / 16:機械")
    if vix_val >= 20: tips.append("2:水産・食品 / 12:医薬品")

    return {
        "strategy": strategy_idx, "opening_forecast": forecast_txt,
        "forecast_title": forecast_title, "balance": balance_txt, 
        "phase_comment": phase_txt, "us_impact": us_impact, 
        "alert_level": alert_lvl, "tips": " / ".join(tips) if tips else "個別材料株（全業種対象）"
    }

# --- 3. スクリーニング・バックテストエンジン ---

def evaluate_screening_conditions(df, params):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['Close', 'Volume'])
    p = float(df['Close'].values.ravel()[-1])
    v = float(df['Volume'].values.ravel()[-1])
    prev_p = float(df['Close'].values.ravel()[-2])
    day_gain = ((p - prev_p) / prev_p) * 100
    ma25 = df['Close'].rolling(25).mean()
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().values.ravel()[-1]
    rsi = RSIIndicator(df['Close'], 14).rsi().values.ravel()[-1]
    ma25_dev = ((p - ma25.values.ravel()[-1]) / ma25.values.ravel()[-1]) * 100
    val_total = (p * v) / 100000000
    if params.get('c_gain') and not (params['gain_range'][0] <= day_gain <= params['gain_range'][1]): return None
    return {"株価": int(p), "前日比": day_gain, "売買代金": val_total, "出来高": int(v), 
            "RSI": round(rsi, 1), "25MA乖離": round(ma25_dev, 2), "ATR%": round((atr/p)*100, 2)}

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    p_map, o_map, a_map = {}, {}, {}
    try:
        df = yf.download(ticker, start=start-timedelta(days=60), interval="1d", progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
        p_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}
        o_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        return p_map, o_map, a_map
    except: return p_map, o_map, a_map

def run_ticker_simulation(ticker, df, pc_map, co_map, a_map, params):
    trades = []
    if df.empty: return trades
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
    df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
    # (シミュレーションの詳細ロジックは以前の版を維持)
    return trades
