import streamlit as st
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

# --- 2. スクリーニング・エンジン (日次データ用：14項目対応版) ---
def evaluate_screening_conditions(df, params):
    """
    1銘柄の日次データに対して、業種・値上がり率を含む全条件に合致するか判定する
    """
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    # 基礎数値
    p = float(df['Close'].iloc[-1])
    v = float(df['Volume'].iloc[-1])
    prev_p = float(df['Close'].iloc[-2])
    
    # 【新規】前日値上がり率の算出
    day_gain = ((p - prev_p) / prev_p) * 100
    
    # 指標算出
    ma5 = df['Close'].rolling(5).mean(); ma10 = df['Close'].rolling(10).mean(); ma25 = df['Close'].rolling(25).mean()
    ema9 = EMAIndicator(df['Close'], 9).ema_indicator(); ema21 = EMAIndicator(df['Close'], 21).ema_indicator()
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().iloc[-1]
    atrp = (atr / p) * 100
    adx = ADXIndicator(df['High'], df['Low'], df['Close'], 14).adx().iloc[-1]
    rsi = RSIIndicator(df['Close'], 14).rsi().iloc[-1]
    rci = calculate_rci(df['Close'], 9).iloc[-1]
    ma25_dev = ((p - ma25.iloc[-1]) / ma25.iloc[-1]) * 100
    val_total = (p * v) / 100000000 # 億円
    vup_rate = v / df['Volume'].rolling(5).mean().iloc[-2] if df['Volume'].rolling(5).mean().iloc[-2] > 0 else 1.0
    
    # ボリンジャーバンド (25日, 2σ)
    std = df['Close'].rolling(25).std().iloc[-1]
    bb_sigma = (p - ma25.iloc[-1]) / std if std > 0 else 0

    # 条件判定フラグ
    match = True

    # --- A. 基本・前日比判定 ---
    if params.get('c_gain') and not (params['gain_range'][0] <= day_gain <= params['gain_range'][1]): match = False
    if params.get('c_p') and not (params['p_range'][0] <= p <= params['p_range'][1]): match = False
    if params.get('c_v') and val_total < params['v_min']: match = False
    if params.get('c_atrp') and not (params['atrp_range'][0] <= atrp <= params['atrp_range'][1]): match = False

    # --- B. 移動平均・EMAオプション判定 ---
    if params.get('c_ma'):
        opt = params['ma_opt']
        if opt == "最強：上昇トレンド":
            if not (ma5.iloc[-1] > ma10.iloc[-1] > ma25.iloc[-1]): match = False
        elif opt == "転換：GC直後":
            if not (ma5.iloc[-1] > ma25.iloc[-1] and ma5.iloc[-2] <= ma25.iloc[-2]): match = False
        elif opt == "収束：嵐の前の静けさ":
            spread = max(ma5.iloc[-1], ma10.iloc[-1], ma25.iloc[-1]) / min(ma5.iloc[-1], ma10.iloc[-1], ma25.iloc[-1]) - 1
            if spread > 0.02: match = False
        elif opt == "リバウンド：短期MA上抜け":
            if not (p > ma5.iloc[-1] and prev_p <= ma5.iloc[-2]): match = False

    if params.get('c_ema'):
        opt = params['ema_opt']
        if opt == "強気：EMAの上で価格維持":
            if not (p > ema9.iloc[-1] > ema21.iloc[-1]): match = False
        elif opt == "安定：EMA付近での推移":
            if not (abs(p / ema9.iloc[-1] - 1) < 0.01): match = False
        elif opt == "レンジ：EMAを上下にまたぐ":
            if not (min(p, prev_p) < ema9.iloc[-1] < max(p, prev_p)): match = False

    # --- C. トレンド・オシレーター判定 ---
    if params.get('c_adx') and not (params['adx_range'][0] <= adx <= params['adx_range'][1]): match = False
    if params.get('c_rci') and not (params['rci_range'][0] <= rci <= params['rci_range'][1]): match = False
    if params.get('c_rsi') and not (params['rsi_range'][0] <= rsi <= params['rsi_range'][1]): match = False

    # --- D. 出来高・乖離・BB判定 ---
    if params.get('c_vol') and (v / 10000) < params['vol_min']: match = False
    if params.get('c_vup') and vup_rate < params['vup_min']: match = False
    if params.get('c_ma25') and not (params['ma25_range'][0] <= ma25_dev <= params['ma25_range'][1]): match = False
    if params.get('c_bb') and not (params['bb_range'][0] <= bb_sigma <= params['bb_range'][1]): match = False

    if match:
        return {
            "株価": int(p),
            "前日比": day_gain,
            "売買代金": val_total,
            "出来高": int(v),
            "RSI": round(rsi, 1),           # 追加
            "25MA乖離": round(ma25_dev, 2),  # 追加
            "ATR%": round(atrp, 2)          # 追加
        }
    return None
    
# --- 3. バックテスト・エンジン (5分足データ用) ---
# (fetch_daily_stats_maps 以降のコードは変更不要のため、そのまま維持してください)

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
    
    df['EMA5'] = EMAIndicator(close=df['Close'], window=5).ema_indicator()
    df['RSI14'] = RSIIndicator(close=df['Close'], window=14).rsi()
    df['RSI14_P'] = df['RSI14'].shift(1)
    macd = MACD(close=df['Close'])
    df['MH'] = macd.macd_diff(); df['MH_P'] = df['MH'].shift(1)
    
    unique_dates = np.unique(df.index.date)
    for d in unique_dates:
        day = df[df.index.date == d].copy().between_time('09:00', '15:00')
        if day.empty: continue
        
        day['VWAP'] = (day['Close'] * day['Volume']).cumsum() / day['Volume'].cumsum().replace(0, np.nan)
        date_str = d.strftime('%Y-%m-%d')
        pc = pc_map.get(date_str); do = co_map.get(date_str)
        if pc is None or do is None: continue
        gap_v = (do - pc) / pc
        
        in_pos = False; entry_p = 0; stop_p = 0; t_high = 0; t_active = False; sl_rec = 0
        
        for ts, row in day.iterrows():
            if not in_pos:
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
    if not trades: return None
    tdf = pd.DataFrame(trades)
    wins = tdf[tdf['PnL'] > 0]; losses = tdf[tdf['PnL'] <= 0]
    win_rate = len(wins) / len(tdf)
    pf = wins['PnL'].sum() / abs(losses['PnL'].sum()) if not losses.empty and losses['PnL'].sum() != 0 else 9.99
    ev = tdf['PnL'].mean()
    score = ev * win_rate * pf
    return {"win_rate": win_rate, "pf": pf, "ev": ev, "score": score}

@st.cache_data(ttl=300)
def fetch_market_info(market_indices):
    data = {}
    for name, ticker in market_indices.items():
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty:
                latest = float(df['Close'].iloc[-1]); prev = float(df['Close'].iloc[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: data[name] = {"val": None, "pct": None}
    return data

# --- 5. AI予測 ---

def analyze_market_environment():
    """
    主要指数から今日の相場環境を診断し、戦略を提案する
    """
    indices = {
        "N225": "^N225", "VIX": "^VIX", "DJI": "^DJI",
        "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F",
        "USDJPY": "JPY=X" # 為替（ドル円）を追加
    }
    
    data = {}
    for k, ticker in indices.items():
        try:
            # interval="1d"で取得。MultiIndex対策も実施
            df = yf.download(ticker, period="5d", interval="1d", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[k] = df
        except:
            continue

    res = {"comment": "", "strategy": 0, "alert_level": "正常", "tips": []}
    n225_close = 0 

    # 1. 日経平均の乖離率 (既存)
    if "N225" in data:
        df_n = data["N225"]
        n225_close = float(df_n['Close'].values[-1])
        n225_ma25 = float(df_n['Close'].rolling(25).mean().values[-1])
        dev_rate = ((n225_close - n225_ma25) / n225_ma25) * 100
        
        if dev_rate > 5.0:
            res["alert_level"] = "⚠️ 高値警戒（過熱）"
            res["comment"] += f"日経平均が25日線から{dev_rate:.1f}%乖離しており過熱気味です。 "
        elif dev_rate < -5.0:
            res["alert_level"] = "📢 底打ち警戒（売られすぎ）"
            res["comment"] += f"25日線から{dev_rate:.1f}%乖離し売られすぎています。 "

    # 2. VIXによる戦略決定 (既存)
    if "VIX" in data:
        vix = float(data["VIX"]['Close'].values[-1])
        if vix > 25.0:
            res["strategy"] = 1 # ディフェンシブ
            res["comment"] += "VIXが高騰しており市場は不安定です。守備重視の『ディフェンシブ』を推奨します。 "
        elif 15.0 <= vix <= 25.0:
            res["strategy"] = 2 # 横ばい
        else:
            res["strategy"] = 0 # 通常

    # 3. 為替（ドル円）による輸出銘柄診断 (新規追加)
    if "USDJPY" in data:
        df_jpy = data["USDJPY"]
        jpy_now = float(df_jpy['Close'].values[-1])
        jpy_prev = float(df_jpy['Close'].values[-2])
        jpy_change = ((jpy_now / jpy_prev) - 1) * 100
        
        # 0.4%以上の変動を検知
        if jpy_change > 0.4:
            res["comment"] += f"ドル円が{jpy_now:.2f}円（円安）に振れています。輸出株に追い風です。 "
            res["tips"].append(f"💴 円安進行中({jpy_change:+.2f}%)。業種『11:輸送（自動車）』や『10:電機』などの輸出セクターをチェックしてください。")
        elif jpy_change < -0.4:
            res["comment"] += f"ドル円が{jpy_now:.2f}円（円高）へ推移しています。内需株や低ベータ株が選好されやすい地合いです。 "
            res["tips"].append(f"💴 円高進行中({jpy_change:+.2f}%)。為替感応度の低い『2:水産・食品』や『14:金融』セクターに注目です。")

    # 4. 特定セクターヒント (SOX/WTI)
    if "SOX" in data:
        df_s = data["SOX"]
        sox_gain = ((float(df_s['Close'].values[-1]) / float(df_s['Close'].values[-2])) - 1) * 100
        if sox_gain > 1.5: 
            res["tips"].append("🚀 SOX指数が大幅上昇。業種『1:AI・半導体』セクターの強い買いが期待できます。")
    
    if "WTI" in data:
        df_w = data["WTI"]
        wti_gain = ((float(df_w['Close'].values[-1]) / float(df_w['Close'].values[-2])) - 1) * 100
        if wti_gain > 2.0: 
            res["tips"].append("🛢️ 原油価格が上昇。業種『6:石油』や金属関連セクターにポジティブな影響が予想されます。")

    return res
