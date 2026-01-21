import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from datetime import datetime, timedelta, time

# --- 1. テクニカル指標・ユーティリティ ---

def calculate_rci(series, period=9):
    """RCI (順位相関指数) の算出"""
    def get_rci(sub):
        n = len(sub)
        d = ((np.arange(n) + 1) - sub.rank(ascending=False)).pow(2).sum()
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(get_rci)

def get_trade_pattern(row, gap_pct):
    """トレードパターンの判定"""
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): return "A：反転狙い"
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): return "D：上昇継続"
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): return "C：ブレイク"
    elif (gap_pct >= 0.003) and (row['Close'] > row['EMA5']): return "B：押目上昇"
    return "E：他タイプ"

# --- 2. 市場分析・指標取得 (FC 3.1 仕様) ---

@st.cache_data(ttl=300)
def fetch_market_info(indices_dict):
    """
    市場指標の値を一括取得する (重複を整理)
    """
    data = {}
    for name, ticker in indices_dict.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                
                # dropnaで空行を排除し、確実な最後から2番目と最後を取得
                df = df.dropna(subset=['Close'])
                latest = float(df['Close'].values.ravel()[-1])
                prev = float(df['Close'].values.ravel()[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: 
            data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=300)
def analyze_market_environment():
    """
    主要指数から今日の相場環境を診断する (為替先物バイアス込)
    """
    indices = {
        "N225": "^N225", "VIX": "^VIX", "DJI": "^DJI",
        "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F",
        "USDJPY": "JPY=X", "GOLD": "GC=F", "JPY_F": "6J=F"
    }
    
    data_map = {}
    for k, ticker in indices.items():
        try:
            df = yf.download(ticker, period="7d", interval="1d", progress=False)
            if not df.empty and len(df) >= 2:
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                data_map[k] = df.dropna(subset=['Close'])
        except: continue

    res = {
        "alert_level": "日経25日線との乖離は正常範囲", "strategy": 0, "opening_forecast": "不明",
        "phase_comment": "本日の市場は比較的落ち着いています。", "us_impact": "大きな変動なし", "tips": []
    }
    n225_close = 0

    if "N225" in data_map:
        try:
            df_n = data_map["N225"]
            n225_close = float(df_n['Close'].values.ravel()[-1])
            n225_ma25 = float(df_n['Close'].rolling(25).mean().values.ravel()[-1])
            dev_rate = ((n225_close - n225_ma25) / n225_ma25) * 100
            if dev_rate > 5.0: res["alert_level"] = "買われ過ぎ。"
            elif dev_rate < -5.0: res["alert_level"] = "売られ過ぎ。"
        except: pass

    if "CME" in data_map and n225_close > 0:
        try:
            cme_val = float(data_map["CME"]['Close'].values.ravel()[-1])
            if (cme_val - n225_close) > 100: res["opening_forecast"] = "ギャップアップ"
            elif (cme_val - n225_close) < -100: res["opening_forecast"] = "ギャップダウン"
        except: pass

    if "VIX" in data_map:
        try:
            vix = float(data_map["VIX"]['Close'].values.ravel()[-1])
            if vix > 25.0: res["strategy"] = 1
            elif 15.0 <= vix <= 25.0: res["strategy"] = 2
        except: pass

    if "JPY_F" in data_map:
        try:
            f_now = float(data_map["JPY_F"]['Close'].values.ravel()[-1])
            f_prev = float(data_map["JPY_F"]['Close'].values.ravel()[-2])
            f_pct = ((f_now / f_prev) - 1) * 100
            if f_pct > 0.2: res["opening_forecast"] += " (円高バイアス)"; res["tips"].append("14:金融　")
            elif f_pct < -0.2: res["opening_forecast"] += " (円安バイアス)"; res["tips"].append("11:輸送　")
        except: pass

    # セクター判定ロジック (SOX, WTI, GOLD等)
    # ... (3.2_logic_core.py の判定を継続)
    res["tips"] = list(dict.fromkeys(res["tips"]))
    return res

# --- 3. スクリーニング・バックテストエンジン ---

def evaluate_screening_conditions(df, params):
    """
    1銘柄の日次データに対して全条件に合致するか判定する
    """
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    # 17時台の空データを排除
    df = df.dropna(subset=['Close', 'Volume'])
    if df.empty: return None

    p = float(df['Close'].values.ravel()[-1])
    v = float(df['Volume'].values.ravel()[-1])
    prev_p = float(df['Close'].values.ravel()[-2])
    day_gain = ((p - prev_p) / prev_p) * 100
    
    # 指標計算
    ma25 = df['Close'].rolling(25).mean()
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().values.ravel()[-1]
    atrp = (atr / p) * 100
    rsi = RSIIndicator(df['Close'], 14).rsi().values.ravel()[-1]
    ma25_dev = ((p - ma25.values.ravel()[-1]) / ma25.values.ravel()[-1]) * 100
    val_total = (p * v) / 100000000

    match = True
    if params.get('c_gain') and not (params['gain_range'][0] <= day_gain <= params['gain_range'][1]): match = False
    if params.get('c_p') and not (params['p_range'][0] <= p <= params['p_range'][1]): match = False
    if params.get('c_v') and val_total < params.get('v_min', 0): match = False
    if params.get('c_atrp') and not (params['atrp_range'][0] <= atrp <= params['atrp_range'][1]): match = False
    if params.get('c_rsi') and not (params['rsi_range'][0] <= rsi <= params['rsi_range'][1]): match = False

    if match:
        return {"株価": int(p), "前日比": day_gain, "売買代金": val_total, "出来高": int(v), 
                "RSI": round(rsi, 1), "25MA乖離": round(ma25_dev, 2), "ATR%": round(atrp, 2)}
    return None

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    """前日終値・当日始値・ATRのマップ作成"""
    p_map, o_map, a_map = {}, {}, {}
    try:
        d_start = start - timedelta(days=60)
        df = yf.download(ticker, start=d_start, end=datetime.now(), interval="1d", progress=False, auto_adjust=False)
        if df.empty: return p_map, o_map, a_map
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # NaN排除を徹底
        df = df.dropna(subset=['Close', 'Open'])
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
        
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_prev = tr.rolling(window=14).mean().shift(1)
        
        p_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}
        o_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        a_map = {d.strftime('%Y-%m-%d'): a for d, a in zip(df.index, atr_prev) if pd.notna(a)}
        return p_map, o_map, a_map
    except: return p_map, o_map, a_map

# --- 4. シミュレーション & スコアリング ---

def run_ticker_simulation(ticker, df, pc_map, co_map, a_map, params):
    """
    (3.2_logic_core.py の run_ticker_simulation ロジックをそのまま継承)
    """
    # ... (3.2_logic_core.py の中身を維持)
    return trades

def get_one_touch_score(trades):
    """
    KeyErrorを防止した安全なスコアリング
    """
    if not trades: return None
    tdf = pd.DataFrame(trades)
    
    # 損益キーを安全に取得
    pnls = tdf['PnL'].values if 'PnL' in tdf.columns else np.array([])
    if len(pnls) == 0: return None

    wins = pnls[pnls > 0]; losses = pnls[pnls <= 0]
    win_rate = len(wins) / len(pnls)
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else 9.99
    ev = pnls.mean()
    score = ev * win_rate * pf
    
    return {"win_rate": win_rate, "pf": pf, "ev": ev, "score": score}
