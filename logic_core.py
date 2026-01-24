import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
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
    indices = {"N225": "^N225", "VIX": "^VIX", "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F", "USDJPY": "JPY=X", "GOLD": "GC=F"}
    data_map = {}
    for k, ticker in indices.items():
        try:
            df = yf.download(ticker, period="40d", interval="1d", progress=False)
            if not df.empty and len(df) >= 2:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                data_map[k] = df.dropna(subset=['Close'])
        except: continue

    n225_close = 0; n225_ma25 = 0; cme_val = 0
    if "N225" in data_map:
        df_n = data_map["N225"]
        n225_close = float(df_n['Close'].values.ravel()[-1])
        n225_ma25 = float(df_n['Close'].rolling(25).mean().values.ravel()[-1])
    if "CME" in data_map: cme_val = float(data_map["CME"]['Close'].values.ravel()[-1])

    gap_pct = (cme_val - n225_close) / n225_close if n225_close > 0 else 0
    
    # 修正：140行目付近の引用符エラーを解消
    if gap_pct <= -0.0015:
        strategy_idx = 1
        base_forecast = "ギャップダウン" if gap_pct <= -0.01 else "下落"
    elif gap_pct >= 0.0015:
        strategy_idx = 0
        base_forecast = "ギャップアップ" if gap_pct >= 0.01 else "上昇"
    else:
        strategy_idx = 2
        base_forecast = "フラット"

    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).time()
    l_s, l_e = time(11, 30), time(12, 30)
    a_s, a_e = time(15, 0), time(19, 0)

    forecast_title = "寄付予測"
    vix_val = 15; sox_pct = 0; fx_pct = 0 # 初期化
    if "VIX" in data_map: vix_val = float(data_map["VIX"]['Close'].values.ravel()[-1])
    if "SOX" in data_map: sox_pct = (data_map["SOX"]['Close'].values.ravel()[-1] / data_map["SOX"]['Close'].values.ravel()[-2]) - 1
    if "USDJPY" in data_map: fx_pct = (data_map["USDJPY"]['Close'].values.ravel()[-1] / data_map["USDJPY"]['Close'].values.ravel()[-2]) - 1

    if l_s <= now <= l_e:
        forecast_title = "前場総括"
        forecast_txt = f"前場は {base_forecast} で推移。25日線乖離は {((n225_close - n225_ma25) / n225_ma25) * 100:.1f}% です。"
        phase_txt = "前場のトレンドを再確認。後場はVWAP付近の攻防や前場高値更新に注目してください。"
    elif a_s <= now <= a_e:
        forecast_title = "今日の結果"
        forecast_txt = f"本日は {base_forecast} で終了。現在の25日線乖離は {((n225_close - n225_ma25) / n225_ma25) * 100:.1f}% です。"
        phase_txt = "本日のトレードお疲れ様でした。明日に向け期待値の高い銘柄を精査しましょう。"
    else:
        bias_list = []
        if fx_pct <= -0.003: bias_list.append("円高バイアス")
        elif fx_pct >= 0.003: bias_list.append("円安バイアス")
        forecast_txt = f"{base_forecast}寄付 ({' / '.join(bias_list)})" if bias_list else f"{base_forecast}寄付"
        phase_txt = "市場は比較的落ち着いています。各銘柄のテクニカルを重視したトレードを。"

    dev_25 = ((n225_close - n225_ma25) / n225_ma25) * 100 if n225_ma25 > 0 else 0
    if dev_25 > 5: balance_txt = f"加熱 / +{dev_25:.1f}%"; alert_lvl = "▶︎▶︎高値警戒（過熱）"
    elif dev_25 < -5: balance_txt = f"過売 / {dev_25:.1f}%"; alert_lvl = "▶︎▶︎底打ち待ち（過売）"
    else: balance_txt = f"均衡 / {dev_25:.1f}%"; alert_lvl = "▶︎▶︎正常範囲（ニュートラル）"

    us_impact = "米国株の変動は限定的。"
    if vix_val >= 20 or sox_pct <= -0.015: us_impact = "半導体安。指数主導の下落に警戒。"
    elif sox_pct >= 0.005: us_impact = "ハイテク株への買い波及を期待。"

    tips = []
    if "WTI" in data_map and (data_map["WTI"]['Close'].values.ravel()[-1] / data_map["WTI"]['Close'].values.ravel()[-2]) - 1 >= 0.005: tips.append("1:鉱業 / 10:石油・石炭")
    if "GOLD" in data_map and (data_map["GOLD"]['Close'].values.ravel()[-1] / data_map["GOLD"]['Close'].values.ravel()[-2]) - 1 >= 0.005: tips.append("9:非鉄金属")
    if sox_pct >= 0.005: tips.append("17:電気機器 / 16:機械")
    if fx_pct >= 0.003: tips.append("19:輸送用機器 / 25:卸売業 / 27:銀行")
    
    # 修正：tips_strを定義
    tips_str = " / ".join(tips) if tips else "個別材料株（全業種対象）"

    return {
        "strategy": strategy_idx, "opening_forecast": forecast_txt, "forecast_title": forecast_title,
        "balance": balance_txt, "phase_comment": phase_txt, "us_impact": us_impact, "alert_level": alert_lvl, "tips": tips_str
    }

# --- 3. スクリーニング・シミュレーション ---

def evaluate_screening_conditions(df, params):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['Close', 'Volume'])
    p = float(df['Close'].values.ravel()[-1]); v = float(df['Volume'].values.ravel()[-1])
    prev_p = float(df['Close'].values.ravel()[-2]); day_gain = ((p - prev_p) / prev_p) * 100
    ma25 = df['Close'].rolling(25).mean(); ma25_dev = ((p - ma25.values.ravel()[-1]) / ma25.values.ravel()[-1]) * 100
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().values.ravel()[-1]
    rsi = RSIIndicator(df['Close'], 14).rsi().values.ravel()[-1]
    val_total = (p * v) / 100000000
    if params.get('c_gain') and not (params['gain_range'][0] <= day_gain <= params['gain_range'][1]): return None
    if params.get('c_v') and val_total < params.get('v_min', 0): return None
    return {"株価": int(p), "前日比": day_gain, "売買代金": val_total, "出来高": int(v), "RSI": round(rsi, 1), "25MA乖離": round(ma25_dev, 2), "ATR%": round((atr/p)*100, 2)}

@st.cache_data(ttl=3600)
def fetch_daily_stats_maps(ticker, start):
    p_map, o_map, a_map = {}, {}, {}
    try:
        df = yf.download(ticker, start=start-timedelta(days=60), progress=False, auto_adjust=False)
        if df.empty: return p_map, o_map, a_map
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_prev = tr.rolling(window=14).mean().shift(1)
        p_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}
        o_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        a_map = {d.strftime('%Y-%m-%d'): a for d, a in zip(df.index, atr_prev) if pd.notna(a)}
    except: pass
    return p_map, o_map, a_map

def run_ticker_simulation(ticker, df, pc_map, co_map, a_map, params):
    trades = []
    if df.empty: return trades
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
    df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
    
    for d in np.unique(df.index.date):
        day = df[df.index.date == d].copy().between_time('09:00', '15:00')
        if day.empty: continue
        day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum().replace(0, np.nan)
        date_str = d.strftime('%Y-%m-%d')
        pc = pc_map.get(date_str); do = co_map.get(date_str)
        if pc is None or do is None: continue
        gap_v = (do - pc) / pc
        in_pos = False; entry_p = 0; stop_p = 0; t_high = 0; t_active = False
        for ts, row in day.iterrows():
            if not in_pos:
                if params['start_t'] <= ts.time() <= params['end_t'] and params['g_min'] <= gap_v <= params['g_max']:
                    if (not params['u_vwap'] or row['Close'] > row['VWAP']) and (not params['u_ema'] or row['Close'] > row['EMA5']):
                        entry_p = row['Close'] * 1.0003; in_pos = True; entry_t = ts; entry_vwap = row['VWAP']
                        stop_p = entry_p * (1 - abs(params['sl_fix'])); t_high = row['High']
            else:
                t_high = max(t_high, row['High'])
                if not t_active and t_high >= entry_p * (1 + params['ts_start']): t_active = True
                ex_p = None
                if t_active and row['Low'] <= t_high * (1 - params['ts_width']): ex_p = t_high * (1 - params['ts_width']) * 0.9997; rsn = "トレーリング"
                elif row['Low'] <= stop_p: ex_p = stop_p * 0.9997; rsn = "損切り"
                elif ts.time() >= time(14, 55): ex_p = row['Close'] * 0.9997; rsn = "時間切れ"
                if ex_p:
                    # 修正点：PrevClose と DayOpen を辞書に追加
                    trades.append({'Ticker': ticker, 'Entry': entry_t, 'Exit': ts, 'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p, 'Reason': rsn, 'Pattern': get_trade_pattern(row, gap_v), 'Gap(%)': gap_v*100, 'EntryVWAP': entry_vwap, 'PrevClose': pc, 'DayOpen': do})
                    in_pos = False; break
    return trades

def get_one_touch_score(trades):
    if not trades: return None
    tdf = pd.DataFrame(trades)
    pnls = tdf['PnL'].values
    wins = pnls[pnls > 0]; losses = pnls[pnls <= 0]
    win_rate = len(wins) / len(pnls); pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else 9.99
    return {"win_rate": win_rate, "pf": pf, "ev": pnls.mean(), "score": pnls.mean() * win_rate * pf, "count": len(pnls), "avg_win": wins.mean() if len(wins)>0 else 0, "avg_loss": losses.mean() if len(losses)>0 else 0}
