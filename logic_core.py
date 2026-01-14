# logic_core.py
import pandas as pd
import numpy as np
import yfinance as yf
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

# --- 2. スクリーニング・エンジン (日次データ用) ---

def evaluate_screening_conditions(df, params):
    """
    1銘柄の日次データに対して、スクリーニング条件に合致するか判定する
    """
    if df.empty or len(df) < 25: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    # 判定に必要な指標を準備
    p = df['Close'].iloc[-1]
    v = df['Volume'].iloc[-1]
    prev_p = df['Close'].iloc[-2]
    ma25 = df['Close'].rolling(25).mean().iloc[-1]
    atrp = (AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().iloc[-1] / p) * 100
    adx = ADXIndicator(df['High'], df['Low'], df['Close']).adx().iloc[-1]
    rsi = RSIIndicator(df['Close'], 14).rsi().iloc[-1]
    rci = calculate_rci(df['Close'], 9).iloc[-1]
    ma25_dev = ((p - ma25) / ma25) * 100
    val_total = (p * v) / 100000000 # 売買代金(億円)
    v_avg_5 = df['Volume'].rolling(5).mean().iloc[-2]
    vup_rate = v / v_avg_5 if v_avg_5 > 0 else 1.0
    price_change_pct = ((p - prev_p) / prev_p) * 100

    # 条件判定の連鎖
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

    if match:
        return {
            "コード": df.index.name, # 呼び出し側で付与
            "株価": int(p),
            "出来高": int(v),
            "前日比": price_change_pct,
            "売買代金": val_total,
            "ATR%": atrp
        }
    return None

# --- 3. バックテスト・エンジン (5分足データ用) ---

def fetch_daily_stats_maps(ticker, start):
    """前日終値・当日始値・ATRのマップ作成"""
    p_map, o_map, a_map = {}, {}, {}
    try:
        d_start = start - timedelta(days=60)
        df = yf.download(ticker, start=d_start, end=datetime.now(), interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
        if df.empty: return p_map, o_map, a_map
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
        
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_prev = tr.rolling(window=14).mean().shift(1)
        p_map = {d.strftime('%Y-%m-%d'): c for d, c in zip(df.index, df['Close'].shift(1)) if pd.notna(c)}
        o_map = {d.strftime('%Y-%m-%d'): o for d, o in zip(df.index, df['Open']) if pd.notna(o)}
        a_map = {d.strftime('%Y-%m-%d'): a for d, a in zip(df.index, atr_prev) if pd.notna(a)}
        return p_map, o_map, a_map
    except: return p_map, o_map, a_map

def run_ticker_simulation(ticker, df, pc_map, co_map, a_map, params):
    """詳細シミュレーションの実行ロジック"""
    trades = []
    if df.empty: return trades
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.index = df.index.tz_localize('UTC').tz_convert('Asia/Tokyo') if df.index.tzinfo is None else df.index.tz_convert('Asia/Tokyo')
    
    # 指標の計算
    df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
    df['RSI14'] = RSIIndicator(close=df['Close'], window=14).rsi()
    df['RSI14_P'] = df['RSI14'].shift(1)
    macd = MACD(close=df['Close'])
    df['MH'] = macd.macd_diff(); df['MH_P'] = df['MH'].shift(1)
    
    unique_dates = np.unique(df.index.date)
    for d in unique_dates:
        day = df[df.index.date == d].copy().between_time('09:00', '15:00')
        if day.empty: continue
        
        # VWAPの算出
        day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum().replace(0, np.nan)
        date_str = d.strftime('%Y-%m-%d')
        pc = pc_map.get(date_str); do = co_map.get(date_str)
        if pc is None or do is None: continue
        gap_v = (do - pc) / pc
        
        in_pos = False; entry_p = 0; stop_p = 0; t_high = 0; t_active = False; sl_rec = 0
        
        for ts, row in day.iterrows():
            if not in_pos:
                # エントリー判定 (params を参照)
                if params['start_t'] <= ts.time() <= params['end_t'] and params['g_min'] <= gap_v <= params['g_max']:
                    c_vwap = (row['Close'] > row['VWAP']) if params['u_vwap'] else True
                    c_ema = (row['Close'] > row['EMA5']) if params['u_ema'] else True
                    c_rsi = (row['RSI14'] > 45 and row['RSI14'] > row['RSI14_P']) if params['u_rsi'] else True
                    c_macd = (row['MH'] > row['MH_P']) if params['u_macd'] else True
                    
                    if c_vwap and c_ema and c_rsi and c_macd:
                        entry_p = row['Close'] * 1.0003
                        in_pos = True; entry_t = ts; entry_vwap = row['VWAP']
                        
                        if params['u_atr']:
                            av = a_map.get(date_str)
                            sl_rec = max(params['atr_min'], (av/entry_p)*params['atr_mul']) if av and entry_p>0 else abs(params['sl_fix'])
                        else:
                            sl_rec = abs(params['sl_fix'])
                            
                        stop_p = entry_p * (1 - sl_rec)
                        t_high = row['High']
                        t_active = False
            else:
                t_high = max(t_high, row['High'])
                if not t_active and t_high >= entry_p * (1 + params['ts_start']):
                    t_active = True
                
                ex_p = None; rsn = ""
                if t_active and row['Low'] <= t_high * (1 - params['ts_width']):
                    ex_p = t_high * (1 - params['ts_width']) * 0.9997; rsn = "トレーリング"
                elif row['Low'] <= stop_p:
                    ex_p = stop_p * 0.9997; rsn = "損切り"
                elif ts.time() >= time(14, 55):
                    ex_p = row['Close'] * 0.9997; rsn = "時間切れ"
                
                if ex_p:
                    trades.append({
                        'Ticker': ticker, 'Entry': entry_t, 'Exit': ts, 
                        'PnL': (ex_p - entry_p)/entry_p, 'In': entry_p, 'Out': ex_p, 
                        'Reason': rsn, 'Pattern': get_trade_pattern(row, gap_v), 
                        'Gap(%)': gap_v*100, 'EntryVWAP': entry_vwap, 
                        'PrevClose': pc, 'DayOpen': do, 'SL設定(%)': sl_rec*100
                    })
                    in_pos = False; break
    return trades

# --- 4. ワンタッチ機能：スコアリング・ランキング ---

def get_one_touch_score(trades):
    """
    バックテスト結果から安定度スコアを算出する
    期待値 * 勝率 * PF
    """
    if not trades: return None
    tdf = pd.DataFrame(trades)
    wins = tdf[tdf['PnL'] > 0]; losses = tdf[tdf['PnL'] <= 0]
    
    win_rate = len(wins) / len(tdf)
    pf = wins['PnL'].sum() / abs(losses['PnL'].sum()) if not losses.empty and losses['PnL'].sum() != 0 else 9.99
    ev = tdf['PnL'].mean()
    
    # スコア計算: 期待値 * 勝率 * PF
    score = ev * win_rate * pf
    
    return {
        "win_rate": win_rate,
        "pf": pf,
        "ev": ev,
        "score": score
    }
