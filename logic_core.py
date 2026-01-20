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

import yfinance as yf
import pandas as pd
import numpy as np

def fetch_market_info(indices_dict):
    """
    市場指標カード用のデータを取得（場中1分足/引け後日足 自動切り替え）
    """
    res = {}
    for name, ticker in indices_dict.items():
        try:
            # 1. 前日終値を確定させるために日足(1d)を取得
            df_d = yf.download(ticker, period="5d", interval="1d", progress=False)
            if df_d.empty or len(df_d) < 2: continue
            if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.get_level_values(0)

            # 常に「前日（最新の1日前）の終値」を基準にする
            prev_close = float(df_d['Close'].values.ravel()[-2])

            # 2. 最新価格を取得（1分足）
            df_m = yf.download(ticker, period="1d", interval="1m", progress=False)
            if isinstance(df_m.columns, pd.MultiIndex): df_m.columns = df_m.columns.get_level_values(0)

            if not df_m.empty:
                # 【場中】最新1分足の終値
                current_p = float(df_m['Close'].values.ravel()[-1])
            else:
                # 【引け後】日足の最新（今日）の終値
                current_p = float(df_d['Close'].values.ravel()[-1])

            # 前日比の算出
            pct = ((current_p / prev_close) - 1) * 100
            res[name] = {"val": current_p, "pct": pct}
        except:
            res[name] = {"val": 0, "pct": 0}
    return res
    
# --- 5. AI予測 ---

import yfinance as yf
import pandas as pd
import numpy as np

def analyze_market_environment():
    """
    今日の相場環境を診断（個別取得・安定重視版）
    ※場中/引け後自動切り替え・前日比固定ロジックを維持
    """
    indices = {
        "N225": "^N225", "VIX": "^VIX", "DJI": "^DJI", "SOX": "^SOX",
        "WTI": "CL=F", "CME": "NIY=F", "USDJPY": "JPY=X", "GOLD": "GC=F", "JPY_F": "6J=F"
    }
    
    # 内部計算用の結果格納
    data_res = {}
    
    for k, ticker in indices.items():
        try:
            # 1. 前日終値取得用の日足
            df_d = yf.download(ticker, period="5d", interval="1d", progress=False)
            if df_d.empty or len(df_d) < 2: continue
            if isinstance(df_d.columns, pd.MultiIndex): 
                df_d.columns = df_d.columns.get_level_values(0)
            
            # 安定的な数値抽出
            prev_val = float(df_d['Close'].values.ravel()[-2]) # 前日終値
            
            # 2. 最新値取得用の1分足
            df_m = yf.download(ticker, period="1d", interval="1m", progress=False)
            if isinstance(df_m.columns, pd.MultiIndex): 
                df_m.columns = df_m.columns.get_level_values(0)
            
            if not df_m.empty:
                now_val = float(df_m['Close'].values.ravel()[-1]) # 場中リアルタイム
            else:
                now_val = float(df_d['Close'].values.ravel()[-1]) # 引け後最新
            
            data_res[k] = {"now": now_val, "prev": prev_val, "pct": ((now_val/prev_val)-1)*100}
        except: continue

    # 診断初期値
    res = {
        "alert_level": "日経平均25日線との乖離は正常範囲", "strategy": 0, "opening_forecast": "不明",
        "phase_comment": "本日の市場は比較的落ち着いています。", "us_impact": "大きな変動なし", "tips": []
    }

    # 1. 警戒レベル (日経平均25日乖離)
    if "N225" in data_res:
        try:
            df_n = yf.download("^N225", period="30d", interval="1d", progress=False)
            if isinstance(df_n.columns, pd.MultiIndex): df_n.columns = df_n.columns.get_level_values(0)
            ma25 = float(df_n['Close'].rolling(25).mean().values.ravel()[-1])
            dev_rate = ((data_res["N225"]["now"] - ma25) / ma25) * 100
            if dev_rate > 5.0: res["alert_level"] = "買われ過ぎ。"
            elif dev_rate < -5.0: res["alert_level"] = "売られ過ぎ。"
        except: pass

    # 2. 寄付予測 (CME vs 日経前日終値)
    if "CME" in data_res and "N225" in data_res:
        diff = data_res["CME"]["now"] - data_res["N225"]["prev"]
        if diff > 100: res["opening_forecast"] = "ギャップアップ"
        elif diff < -100: res["opening_forecast"] = "ギャップダウン"

    # 3. 戦略 & 展望 (VIX判定：表示用のみ)
    if "VIX" in data_res:
        vix = data_res["VIX"]["now"]
        if vix > 25.0:
            res["strategy"] = 1 # ディフェンシブ
            res["phase_comment"] = "VIXが高騰しており市場は不安定です。"
        elif 15.0 <= vix <= 25.0:
            res["strategy"] = 2 # 横ばい相場
            res["phase_comment"] = "市場にやや迷いが見られます。"

    # 4. 米国株の影響 (DJI)
    if "DJI" in data_res:
        dji_pct = data_res["DJI"]["pct"]
        if dji_pct > 0.5: res["us_impact"] = "米国株の上昇が日本市場の支えとなっています。"
        elif dji_pct < -0.5: res["us_impact"] = "米国株の軟調さが重荷となる可能性があります。"

    # 5. 為替先物バイアス
    if "JPY_F" in data_res:
        f_pct = data_res["JPY_F"]["pct"]
        if f_pct > 0.2:
            res["opening_forecast"] += " (円高バイアス)"
            res["tips"].append("14:金融　")
        elif f_pct < -0.2:
            res["opening_forecast"] += " (円安バイアス)"
            res["tips"].append("11:輸送　")

    # 6. セクターヒント
    if "GOLD" in data_res and data_res["GOLD"]["pct"] > 1.0: res["tips"].append("8:金属　")
    if "USDJPY" in data_res:
        j_pct = data_res["USDJPY"]["pct"]
        if j_pct > 0.3: res["tips"].extend(["11:輸送　", "10:電機　"])
        elif j_pct < -0.3: res["tips"].extend(["2:水産・食品　", "14:金融　"])
    if "SOX" in data_res and data_res["SOX"]["pct"] > 1.0: res["tips"].append("1:AI・半導体　")
    if "WTI" in data_res and data_res["WTI"]["pct"] > 1.5: res["tips"].append("6:石油　")

    res["tips"] = list(dict.fromkeys(res["tips"]))
    return res

def get_one_touch_score(trades):
    """
    【独立仕様】AIのstrategyを引数に取らず、tradesのみで銘柄判定を行う
    """
    if not trades:
        return {"win_rate": 0, "pf": 0, "ev": 0, "score": 0}
    
    # 銘柄判定のスコアリングロジック (現状維持)
    # ... (既存の計算処理) ...
    return score_data
    
