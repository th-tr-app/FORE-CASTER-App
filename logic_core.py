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
    """主要指数から今日の相場環境をプロ視点で診断する (Ver 4.7.2：エラー解消版)"""
    indices = {"N225": "^N225", "VIX": "^VIX", "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F", "USDJPY": "JPY=X", "GOLD": "GC=F"}
    data_map = {}
    
    jst = timezone(timedelta(hours=9))
    now_dt = datetime.now(jst)
    today = now_dt.date()

    for k, ticker in indices.items():
        try:
            df = yf.download(ticker, period="40d", interval="1d", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

            if df.index[-1].date() != today:
                t_obj = yf.Ticker(ticker)
                current_p = t_obj.info.get('regularMarketPrice') or t_obj.info.get('previousClose')
                if current_p:
                    new_row = pd.DataFrame([[current_p] * 4 + [0, 0, 0]], columns=df.columns, index=[pd.Timestamp(today)])
                    df = pd.concat([df, new_row])
            
            data_map[k] = df.dropna(subset=['Close'])
        except: continue

    # --- 1. 基礎データの抽出 (時間帯別基準値制御) ---
    n225_close = 0; n225_prev_close = 0; n225_ma25 = 0; cme_val = 0
    
    # 現在が前場引け(11:30)以降かどうかを判定
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    is_after_zenba = now_jst.time() >= time(11, 30)

    if "N225" in data_map:
        df_n = data_map["N225"]
        today_date = now_jst.date()
        
        # 確実に「昨日以前」のデータのみを抽出（ザラ場中の未確定行を排除）
        past_df = df_n[df_n.index.date < today_date].dropna(subset=['Close'])
        
        if not past_df.empty:
            n225_prev_close = float(past_df['Close'].iloc[-1]) # 前日終値
            n225_ma25 = float(past_df['Close'].rolling(25).mean().iloc[-1])

        # 条件に合わせた基準終値の決定
        if not is_after_zenba:
            # 【条件1】11:30まで：前日終値を使用
            n225_close = n225_prev_close
        else:
            # 【条件2】11:30以降：前場の終値(11:30)を自動取得
            # yfinanceで今日の前場データを取得
            t_n225 = yf.Ticker("^N225")
            df_today = t_n225.history(period="1d", interval="30m")
            zenba_df = df_today.between_time('09:00', '11:40') # 11:30の足を狙う
            if not zenba_df.empty:
                n225_close = float(zenba_df['Close'].iloc[-1])
            else:
                n225_close = n225_prev_close # 取得失敗時は前日終値
    
    # 日経平均が0なら昨日の値を代入してエラーを防ぐ
    if n225_close == 0: n225_close = n225_prev_close if n225_prev_close > 0 else 39000

    # CMEデータの取得 (0円・NaNの時は現物を代入して乖離0%にする)
    if "CME" in data_map: 
        cme_val = float(data_map["CME"]['Close'].values.ravel()[-1])
        if cme_val == 0 or pd.isna(cme_val): cme_val = n225_close
    else:
        cme_val = n225_close

    market_pct = (n225_close - n225_prev_close) / n225_prev_close if n225_prev_close > 0 else 0
    dev_25 = ((n225_close - n225_ma25) / n225_ma25) * 100 if n225_ma25 > 0 else 0
    gap_pct = (cme_val - n225_close) / n225_close if n225_close > 0 else 0

    # 地合い判定の文字化
    if dev_25 > 3:
        balance_txt = f"買われ過ぎ / 25日線乖離 +{dev_25:.1f}%"; alert_lvl = "▶︎▶︎高値警戒（過熱）"
    elif dev_25 < -3:
        balance_txt = f"売られ過ぎ / 25日線乖離 {dev_25:.1f}%"; alert_lvl = "▶︎▶︎底打ち待ち（過売）"
    else:
        balance_txt = f"均衡しています / 25日線乖離 {dev_25:.1f}%"; alert_lvl = "▶︎▶︎正常範囲（ニュートラル）"

    # 変数の初期化 (UnboundLocalError 回避用)
    forecast_title = "寄付予測"; forecast_txt = "分析中..."; phase_txt = "分析中..."
    strategy_idx = 2; base_forecast = "フラット"

    if gap_pct <= -0.0015:
        strategy_idx = 1; base_forecast = "ギャップダウン" if gap_pct <= -0.01 else "下落"
    elif gap_pct >= 0.0015:
        strategy_idx = 0; base_forecast = "ギャップアップ" if gap_pct >= 0.01 else "上昇"

    vix_val = 15; sox_pct = 0; fx_pct = 0
    if "VIX" in data_map: vix_val = float(data_map["VIX"]['Close'].values.ravel()[-1])
    if "SOX" in data_map: sox_pct = (data_map["SOX"]['Close'].values.ravel()[-1] / data_map["SOX"]['Close'].values.ravel()[-2]) - 1
    if "USDJPY" in data_map: fx_pct = (data_map["USDJPY"]['Close'].values.ravel()[-1] / data_map["USDJPY"]['Close'].values.ravel()[-2]) - 1

    now = now_dt.time()
    l_s, l_e = time(11, 30), time(12, 30); a_s, a_e = time(15, 0), time(19, 0)
    bias_list = []

    # --- 時間帯別の展望生成 ---
    if l_s <= now <= l_e:
        forecast_title = "前場総括"
        forecast_txt = f"前場は {base_forecast} で推移。現在の乖離率は {dev_25:.1f}% です。"
        phase_txt = "前場が終了しました。後場の寄り付きまで待機、または前場の振り返りを行いましょう。"
        
    elif a_s <= now <= a_e:
        forecast_title = "今日の結果"
        actual_result = "上昇" if market_pct > 0 else "下落" if market_pct < 0 else "変わらず"
        forecast_txt = f"本日は {actual_result} で終了。大引け時点の乖離率は {dev_25:.1f}% です。"
        phase_txt = "お疲れ様でした。明日に向け期待値の高い銘柄をランキングで精査しましょう。"
    else:
        if fx_pct <= -0.003: bias_list.append("円高バイアス")
        elif fx_pct >= 0.003: bias_list.append("円安バイアス")
        forecast_txt = f"{base_forecast} ({' / '.join(bias_list)})" if bias_list else f"{base_forecast}"

        if "高値警戒" in alert_lvl:
            phase_txt = "加熱圏のギャップアップ。利確をこなしつつ、ボリンジャー+2σ付近の攻防に警戒。" if "上昇" in base_forecast else "高値警戒感から上値が重い展開。"
        elif "底打ち待ち" in alert_lvl:
            phase_txt = "売られすぎ圏での寄り付き。パニック売り後の反発に妙味。" if "下落" in base_forecast else "底堅い動き。リバウンドを想定。"
        else:
            phase_txt = "堅調なスタート。VWAPを支持線にできるか注視。" if "上昇" in base_forecast else "売り先行。主要な節目での下げ止まりを確認。"

    us_impact = "米国株の変動は限定的。"
    if vix_val >= 20 or sox_pct <= -0.015: us_impact = "半導体安。指数主導の下落に警戒。"
    elif sox_pct >= 0.005: us_impact = "ハイテク株への買い波及を期待。"

    tips = []
    if "WTI" in data_map and (data_map["WTI"]['Close'].iloc[-1] / data_map["WTI"]['Close'].iloc[-2]) - 1 >= 0.005: tips.append("1:鉱業 / 10:石油・石炭")
    if sox_pct >= 0.005: tips.append("17:電気機器 / 16:機械")
    
    return {
        "strategy": strategy_idx, "opening_forecast": forecast_txt, "forecast_title": forecast_title,
        "balance": balance_txt, "phase_comment": phase_txt, "us_impact": us_impact, "alert_level": alert_lvl, 
        "tips": " / ".join(tips) if tips else "個別材料株（全業種対象）",
        "gap_pct": gap_pct, "market_pct": market_pct
    }
    
# --- 3. スクリーニング・シミュレーション ---
# logic_core.py の判定ロジック（修正版）

def evaluate_screening_conditions(df, params):
    """銘柄の日次データに対して全項目の条件に合致するか判定する"""
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['Close', 'Volume'])
    if df.empty: return None

    # 基本情報の取得
    p = float(df['Close'].values.ravel()[-1])
    v = float(df['Volume'].values.ravel()[-1])
    prev_p = float(df['Close'].values.ravel()[-2])
    day_gain = ((p - prev_p) / prev_p) * 100
    
    # 指標の算出
    ma25_series = df['Close'].rolling(25).mean()
    ma25 = ma25_series.values.ravel()[-1]
    ma25_dev = ((p - ma25) / ma25) * 100 if ma25 > 0 else 0
    
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], 14).average_true_range().values.ravel()[-1]
    rsi = RSIIndicator(df['Close'], 14).rsi().values.ravel()[-1]
    rci = calculate_rci(df['Close'], 9).values.ravel()[-1]
    
    adx = ADXIndicator(df['High'], df['Low'], df['Close'], 14).adx().values.ravel()[-1]
    
    # 【修正箇所】ボリンジャーバンドの計算ロジック
    bb = BollingerBands(df['Close'], 20, 2)
    mavg = bb.bollinger_mavg().values.ravel()[-1]
    hband = bb.bollinger_hband().values.ravel()[-1]
    
    # シグマの幅（Hband - Mavg）が0でないことを確認して算出
    diff = hband - mavg
    bb_val = (p - mavg) * 2 / diff if diff != 0 else 0
    
    val_total = (p * v) / 100000000 # 億円
    v_prev_avg = df['Volume'].shift(1).rolling(5).mean().values.ravel()[-1]
    v_ratio = v / v_prev_avg if v_prev_avg > 0 else 1.0

    # 判定フラグのチェック
    match = True
    if params.get('c_gain') and not (params['gain_range'][0] <= day_gain <= params['gain_range'][1]): match = False
    if params.get('c_p') and not (params['p_range'][0] <= p <= params['p_range'][1]): match = False
    if params.get('c_v') and val_total < params.get('v_min', 0): match = False
    if params.get('c_atrp') and not (params['atrp_range'][0] <= (atr/p)*100 <= params['atrp_range'][1]): match = False
    if params.get('c_rsi') and not (params['rsi_range'][0] <= rsi <= params['rsi_range'][1]): match = False
    if params.get('c_rci') and not (params['rci_range'][0] <= rci <= params['rci_range'][1]): match = False
    if params.get('c_adx') and not (params['adx_range'][0] <= adx <= params['adx_range'][1]): match = False
    if params.get('c_ma25') and not (params['ma25_range'][0] <= ma25_dev <= params['ma25_range'][1]): match = False
    if params.get('c_vup') and v_ratio < params.get('vup_min', 1.0): match = False
    if params.get('c_bb') and not (params['bb_range'][0] <= bb_val <= params['bb_range'][1]): match = False

    if match:
        return {
            "株価": int(p), "前日比": day_gain, "売買代金": val_total, "出来高": int(v), 
            "RSI": round(rsi, 1), "25MA乖離": round(ma25_dev, 2), "ATR%": round((atr/p)*100, 2)
        }
    return None

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

# RSIとEMA判定
def calculate_rsi(series, period=14):
    """
    RSI (相対力指数) を計算する
    """
    delta = series.diff()
    # 上昇幅と下落幅を分離
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))

    # 指数移動平均(EMA)を用いて平滑化
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# --- 4. 指値戦略用ガードロジック ---

def check_opening_deviation(actual, expected, last_close):
    """
    予想寄付きと実際の始値の乖離をチェックするガードロジック
    """
    if actual is None or expected is None or last_close is None:
        return False, 0.0
    
    # 1. 乖離率の計算: abs(Actual - Expected) / Expected * 100
    dev_pct = abs(actual - expected) / expected * 100
    
    # 2. ギャップ幅の比較 (予想ギャップの2倍判定用)
    exp_gap_abs = abs(expected - last_close) / last_close * 100
    act_gap_abs = abs(actual - last_close) / last_close * 100
    
    # 判定条件:
    # A. 乖離率が 0.5% 以上
    # B. 実際のギャップが予想の 2倍以上 (予想が 0.1% 以上の有意な時のみ)
    is_large = (dev_pct >= 0.5) or (exp_gap_abs >= 0.1 and act_gap_abs >= 2 * exp_gap_abs)
    
    return is_large, dev_pct

# --- 5. 始値の自動取得ロジック　始値取得の高速化（Fast Mode) ---
def get_realtime_opening_price(ticker_symbol):
    """始値を最速で取得する (Fast Mode)"""
    try:
        jst = timezone(timedelta(hours=9))
        now_dt = datetime.now(jst)
        today = now_dt.date()
        
        # 9:00前や15:30以降は判定不要
        if now_dt.time() < time(9, 0) or now_dt.time() > time(15, 30):
            return None
            
        is_afternoon = now_dt.time() >= time(12, 30)

        # yfinanceのdownload(1m)が最も反映が早いため優先
        df = yf.download(ticker_symbol, period="1d", interval="1m", progress=False, auto_adjust=False)
        
        if df.empty:
            # downloadが空ならTicker.info(Fast Info)をフォールバックとして使用
            t_obj = yf.Ticker(ticker_symbol)
            fast_open = t_obj.info.get('open')
            if fast_open and fast_open > 0:
                return int(fast_open)
            return None
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)

        # 12:30以降（後場モード）
        if is_afternoon:
            df_pm = df.between_time('12:30', '15:00')
            if not df_pm.empty:
                return int(df_pm['Open'].iloc[0])
        # 9:00〜11:30（前場モード）
        else:
            df_am = df.between_time('09:00', '11:30')
            if not df_am.empty:
                return int(df_am['Open'].iloc[0])
                
    except Exception:
        pass
    return None

# --- 6. セカンドプラン（B/C/D）用スキャンロジック ---
def scan_candidates_with_tier(ticker_list, params, ticker_details_map, min_win, rsi_slope_min):
    """【セカンドプラン】指定されたティア基準で期待値TOP5を選出する"""
    results = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=params['days'])
    
    # タイムゾーン設定
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    today_jst = now_jst.date()
    
    # 朝イチ判定 ＆ 後場寄り判定 (判定を緩和する時間帯を定義)
    current_time = now_jst.time()
    is_early_session = (current_time < time(9, 15)) or (time(12, 30) <= current_time < time(12, 45))

    for t in ticker_list:
        try:
            # 1. 始値の取得 (Fast Mode)
            opening_p = get_realtime_opening_price(t)
            if not opening_p: continue
                
            # 2. 勢いチェック (9:15以降のみ厳格に判定)
            if not is_early_session: # is_early_morning から変更
                t_obj = yf.Ticker(t)
                df_m = t_obj.history(interval="1m", period="1d")
                if not df_m.empty:
                    curr_p = df_m['Close'].iloc[-1]
                    ema5 = df_m['Close'].ewm(span=5, adjust=False).mean().iloc[-1]
                    if curr_p <= ema5: continue 

                    rsi_series = calculate_rsi(df_m['Close'])
                    if len(rsi_series) >= 6:
                        rsi_slope = rsi_series.tail(3).mean() - rsi_series.iloc[-6:-3].mean()
                        if rsi_slope < rsi_slope_min: continue

            # 3. ギャップ判定
            t_obj = yf.Ticker(t)
            hist_d = t_obj.history(period="5d")
            past_hist = hist_d[hist_d.index.date < today_jst]
            if past_hist.empty: continue
            last_close = past_hist['Close'].iloc[-1]
            
            today_gap = (opening_p - last_close) / last_close
            if not (params['g_min'] <= today_gap <= params['g_max']): continue

            # 4. 過去統計の計算
            df_5m = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
            if df_5m.empty: continue
            if isinstance(df_5m.columns, pd.MultiIndex): 
                df_5m.columns = df_5m.columns.get_level_values(0)
            
            p_map, o_map, a_map = fetch_daily_stats_maps(t, start_date)
            trades = run_ticker_simulation(t, df_5m, p_map, o_map, a_map, params)
            score = get_one_touch_score(trades)
            
            # 【重要】閾値(min_win)を厳格に守る
            if score and score['win_rate'] >= min_win:
                results.append({
                    'code': t,
                    'score': score['score'],
                    'open': opening_p,
                    'win_rate': score['win_rate']
                })
        except:
            continue
            
    # スコア上位5銘柄
    return sorted(results, key=lambda x: x['score'], reverse=True)[:5]
    
