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

def calculate_rsi(series, period=14):
    """RSIを計算する (taライブラリを使用)"""
    if series.empty or len(series) < period:
        return pd.Series()
    return RSIIndicator(close=series, window=period).rsi()

def get_trade_pattern(row, gap_pct):
    # チェック用の基準値（VWAPがない場合はCloseで代用）
    check_vwap = row['VWAP'] if pd.notna(row['VWAP']) else row['Close']
    
    # 【A：反転狙い】 大幅GDからの買い戻し
    if (gap_pct <= -0.004) and (row['Close'] > check_vwap): 
        return "A：反転狙い"
    
    # 【B：押目上昇】(反発確認版)
    # 条件1：+0.3%以上のGUで始まっている
    # 条件2：その足の安値(Low)がVWAP付近（0.3%以内）まで押し戻されている（＝押し目を作った）
    # 条件3：その足の終値(Close)がVWAPより上で引けている（＝反発を確認した）
    elif (gap_pct >= 0.003) and (row['Low'] <= check_vwap * 1.003) and (row['Close'] > check_vwap):
        return "B：押目上昇"

    # 【C：ブレイク】 窓開けから一度も垂れずに突き抜ける強い動き
    elif (gap_pct >= 0.005) and (row.get('RSI14', 50) >= 65): 
        return "C：ブレイク"
    
    # 【D：上昇継続】 ほぼフラットからEMA5を背にじり高
    elif (-0.003 <= gap_pct < 0.003) and (row['Close'] > row['EMA5']): 
        return "D：上昇継続"
    
    return "E：他タイプ"
    
def calculate_recovery_stats(df):
    """
    9:00始値からの反発力と回復率を計算 (Ver 5.0 最終防衛版)
    """
    if df is None or df.empty:
        return 0.0, 0.0
    
    temp_df = df.copy()
    
    # 【最重要】階層構造（MultiIndex）を確実に解除する
    if isinstance(temp_df.columns, pd.MultiIndex):
        # レベル0が 'Open' などの項目名ならそのまま、銘柄コードならレベル1を採用
        if 'Open' in temp_df.columns.get_level_values(0):
            temp_df.columns = temp_df.columns.get_level_values(0)
        else:
            temp_df.columns = temp_df.columns.get_level_values(1)
    
    if 'High' not in temp_df.columns:
        return 0.0, 0.0

    temp_df['ret_from_open'] = (temp_df['High'] - temp_df['Open']) / temp_df['Open'].replace(0, np.nan) * 100
    avg_ret = temp_df['ret_from_open'].dropna().mean() if not temp_df['ret_from_open'].dropna().empty else 0.0

    dip_and_recover = temp_df[(temp_df['Low'] <= temp_df['Open']) & (temp_df['High'] > temp_df['Open'])]
    recovery_rate = (len(dip_and_recover) / len(temp_df)) * 100 if len(temp_df) > 0 else 0.0

    return float(avg_ret), float(recovery_rate)
    
def execute_plan_b_scan(ticker_list, market_gap_pct):
    """
    プランB：即時スキャン実行 (Ver 5.0 緩和版)
    """
    results = []
    m_gap_pct_safe = float(market_gap_pct) if market_gap_pct is not None else 0.0
    m_gap_abs = abs(m_gap_pct_safe)
    dynamic_limit = max(1.0, m_gap_abs + 0.5)

    for ticker in ticker_list:
        try:
            t = yf.Ticker(ticker)
            f_info = t.fast_info
            curr_p = f_info.get('last_price')
            prev_c = f_info.get('previous_close')
            if not curr_p or not prev_c: continue

            # MAG適正判定
            act_gap_pct = ((curr_p - prev_c) / prev_c) * 100
            # 修正前：if abs(act_gap_pct) > dynamic_limit: continue
            # 修正後（テスト用）：上限・下限を一時的に5%まで広げる
            if abs(act_gap_pct) > 5.0: continue
    
            df_m = t.history(period="1d", interval="1m")
            if df_m.empty: continue
            
            # ここでも階層インデックスを解除
            if isinstance(df_m.columns, pd.MultiIndex):
                df_m.columns = df_m.columns.get_level_values(0)
            
            vwap = (df_m['Close'] * df_m['Volume']).sum() / df_m['Volume'].sum()
            rsi_series = calculate_rsi(df_m['Close'])
            rsi = rsi_series.iloc[-1] if not rsi_series.empty else 0
            
            if curr_p > vwap and rsi >= 45:
                results.append({
                    "ticker": ticker, "price": curr_p, "gap": act_gap_pct,
                    "rsi": rsi, "vwap_dist": ((curr_p - vwap) / vwap) * 100
                })
        except: continue
    return results

# --- 2. 市場分析・指標取得 ---
@st.cache_data(ttl=60)
def fetch_market_info(indices_dict):
    data = {}
    for name, ticker in indices_dict.items():
        try:
            t = yf.Ticker(ticker)
            # .info は制限を受けやすいため、軽量な .fast_info を主軸にする
            f_info = t.fast_info
            
            # fast_info から取得を試みる
            latest = f_info.get('last_price')
            prev = f_info.get('previous_close')

            # fast_info で取れない場合は、従来の .info や yf.download で補完
            if latest is None or prev is None:
                info = t.info
                latest = info.get('regularMarketPrice')
                prev = info.get('previousClose')

            if latest is not None and prev is not None:
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
            else:
                # 最終バックアップロジック
                df = yf.download(ticker, period="5d", progress=False)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    latest = float(df['Close'].iloc[-1])
                    prev = float(df['Close'].iloc[-2])
                    data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
                else:
                    data[name] = {"val": None, "pct": None}
        except:
            data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=60) # TTLを短縮して最新情報を反映
def analyze_market_environment():
    """主要指数から今日の相場環境を診断する (Ver 4.99：Ticker.info 優先版)"""
    indices = {"N225": "^N225", "VIX": "^VIX", "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F", "USDJPY": "JPY=X", "GOLD": "GC=F"}
    data_map = {}
    
    jst = timezone(timedelta(hours=9))
    now_dt = datetime.now(jst)
    
    # 指標ごとの最新値と前日終値を保持する辞書
    stats_map = {}

    for k, ticker in indices.items():
        try:
            # 1. Ticker.info から最新値(Price)と前日終値(Close)を優先取得
            t_obj = yf.Ticker(ticker)
            info = t_obj.info
            latest = info.get('regularMarketPrice')
            prev = info.get('previousClose')

            # 2. 25日移動平均線(MA25)算出のために履歴データも取得
            df = yf.download(ticker, period="60d", interval="1d", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=['Close'])

            # infoが取れない場合のフォールバック
            if latest is None and not df.empty: latest = float(df['Close'].iloc[-1])
            if prev is None and len(df) >= 2: prev = float(df['Close'].iloc[-2])
            
            stats_map[k] = {"latest": latest, "prev": prev}
            data_map[k] = df
        except: continue

    # --- 1. 基礎データの抽出 (None の場合に 0 を代入するよう修正) ---
    # stats_map.get(...).get(...) or 0 と書くことで、None の場合に 0 が入ります
    n225_close = stats_map.get("N225", {}).get("latest") or 0
    n225_prev_close = stats_map.get("N225", {}).get("prev") or 0
    
    # 25日移動平均線
    n225_ma25 = 0
    if "N225" in data_map:
        df_n = data_map["N225"]
        if len(df_n) >= 25:
            # 最後に or 0 を追加
            n225_ma25 = float(df_n['Close'].rolling(25).mean().iloc[-1]) or 0

    # CMEデータの取得 (or 0 を追加)
    cme_val = stats_map.get("CME", {}).get("latest") or n225_close or 0

    # 各指数の計算
    market_pct = (n225_close - n225_prev_close) / n225_prev_close if n225_prev_close and n225_prev_close > 0 else 0
    dev_25 = ((n225_close - n225_ma25) / n225_ma25) * 100 if n225_ma25 and n225_ma25 > 0 else 0
    gap_pct = (cme_val - n225_close) / n225_close if n225_close and n225_close > 0 else 0

    # 地合い判定の文字化
    if dev_25 > 3:
        balance_txt = f"買われ過ぎ / 25日線乖離 +{dev_25:.1f}%"; alert_lvl = "▶︎▶︎高値警戒（過熱）"
    elif dev_25 < -3:
        balance_txt = f"売られ過ぎ / 25日線乖離 {dev_25:.1f}%"; alert_lvl = "▶︎▶︎底打ち待ち（過売）"
    else:
        balance_txt = f"均衡しています / 25日線乖離 {dev_25:.1f}%"; alert_lvl = "▶︎▶︎正常範囲（ニュートラル）"

    # 変数の初期化 (UnboundLocalError 回避用)
    forecast_title = "寄付予測"; forecast_txt = "分析中..."; phase_txt = "分析中..."
    strategy_idx = 2
    
    # 1. ギャップに応じた基本方向の決定（判定を簡潔に統合）
    if gap_pct <= -0.0015:
        strategy_idx = 1
        base_forecast = "ギャップダウン" if gap_pct <= -0.01 else "下落"
    elif gap_pct >= 0.0015:
        strategy_idx = 0
        base_forecast = "ギャップアップ" if gap_pct >= 0.01 else "上昇"
    else:
        base_forecast = "フラット"

    # 2. 指標データの取得（.emptyチェックと .iloc による安全なアクセス）
    vix_val = 15; sox_pct = 0; fx_pct = 0
    
    if "VIX" in data_map and not data_map["VIX"].empty:
        vix_val = float(data_map["VIX"]['Close'].iloc[-1])
        
    if "SOX" in data_map and len(data_map["SOX"]) >= 2: 
        s_df = data_map["SOX"]
        sox_pct = (s_df['Close'].iloc[-1] / s_df['Close'].iloc[-2]) - 1
        
    if "USDJPY" in data_map and len(data_map["USDJPY"]) >= 2:
        f_df = data_map["USDJPY"]
        fx_pct = (f_df['Close'].iloc[-1] / f_df['Close'].iloc[-2]) - 1

    # 3. 時間帯の定義とリスト初期化
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
        # 朝・夜・市場稼働中
        if fx_pct <= -0.003: bias_list.append("円高バイアス")
        elif fx_pct >= 0.003: bias_list.append("円安バイアス")
        forecast_txt = f"{base_forecast} ({' / '.join(bias_list)})" if bias_list else f"{base_forecast}"

        if "高値警戒" in alert_lvl:
            phase_txt = "加熱圏のギャップアップ。利確をこなしつつ、ボリンジャー+2σ付近の攻防に警戒。" if "上昇" in base_forecast else "高値警戒感から上値が重い展開。"
        elif "底打ち待ち" in alert_lvl:
            phase_txt = "売られすぎ圏での寄り付き。パニック売り後の反発に妙味。" if "下落" in base_forecast else "底堅い動き。リバウンドを想定。"
        else:
            phase_txt = "堅調なスタート。VWAPを支持線にできるか注視。" if "上昇" in base_forecast else "売り先行。主要な節目での下げ止まりを確認。"

    # --- 米国株・チップス等の処理 ---
    us_impact = "米国株の変動は限定的。"
    if vix_val >= 20 or sox_pct <= -0.015: us_impact = "半導体安。指数主導の下落に警戒。"
    elif sox_pct >= 0.005: us_impact = "ハイテク株への買い波及を期待。"

    tips = []
    if "WTI" in data_map and len(data_map["WTI"]) >= 2:
        if (data_map["WTI"]['Close'].iloc[-1] / data_map["WTI"]['Close'].iloc[-2]) - 1 >= 0.005: tips.append("1:鉱業 / 10:石油・石炭")
    if sox_pct >= 0.005: tips.append("17:電気機器 / 16:機械")
    
    # --- 【新設】寄り付き許容範囲の推奨計算 ---
    # 地合い(gap_pct)に対して、プラスマイナス 0.5% 〜 1.0% の余裕を持たせる
    m_gap_abs = abs(gap_pct * 100)
    
    # 推奨上限：地合いがプラスなら「地合い + 0.5%」、マイナスなら「1.0% (標準)」
    rec_max = max(1.0, m_gap_abs + 0.5) if gap_pct > 0 else 1.0
    # 推奨下限：地合いがマイナスなら「地合い - 0.5%」、プラスなら「-3.0% (標準)」
    rec_min = min(-3.0, -(m_gap_abs + 0.5)) if gap_pct < 0 else -3.0

    return {
        "strategy": strategy_idx, "opening_forecast": forecast_txt, "forecast_title": forecast_title,
        "balance": balance_txt, "phase_comment": phase_txt, "us_impact": us_impact, "alert_level": alert_lvl, 
        "tips": " / ".join(tips) if tips else "個別材料株（全業種対象）",
        "gap_pct": gap_pct, "market_pct": market_pct,
        "rec_g_max": rec_max, "rec_g_min": rec_min # 推奨値を辞書に追加
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

# --- 4. 指値戦略用ガードロジック ---
def check_opening_deviation(actual, expected, last_close, market_gap_pct=0.0):
    """
    市場の地合いを考慮した動的ガードロジック (Ver 5.10)
    """
    if actual is None or expected is None or last_close is None:
        return False, 0.0
    
    # 乖離率(予想と実際の始値のズレ)
    dev_pct = abs(actual - expected) / expected * 100
    
    # 【新理論】地合いが強い時は上限を自動で拡大 (1.0%固定から、地合い+0.5%へ)
    # market_gap_pct は %単位(例: 1.5) で渡されることを想定
    m_gap_abs = abs(market_gap_pct)
    dynamic_upper_limit = max(1.0, m_gap_abs + 0.5)
    
    # 実際の騰落率 (始値 vs 前日終値)
    act_gap_pct = ((actual - last_close) / last_close) * 100
    
    # 動的上限を超えているか、または予想との乖離が 1.0% 以上なら警告
    is_large = (act_gap_pct > dynamic_upper_limit) or (dev_pct >= 1.0)
    
    return is_large, dev_pct

# --- 5. 始値の自動取得ロジック (Ver 4.6.8：高精度・後場安定版) ---
def get_realtime_opening_price(ticker_symbol):
    try:
        jst = timezone(timedelta(hours=9))
        now_dt = datetime.now(jst)
        today = now_dt.date()
        
        if now_dt.time() < time(9, 0) or now_dt.time() > time(15, 30):
            return None
            
        t = yf.Ticker(ticker_symbol)
        is_afternoon = now_dt.time() >= time(12, 30)

        # 前場(9:00-12:29)は info から速報取得
        if not is_afternoon:
            todays_open = t.info.get('open')
            if todays_open and todays_open > 0:
                return int(todays_open)

        # 後場、または info が空の場合：より確実に 2d 分の履歴を取りに行く
        df = t.history(period="2d", interval="1m")
        if df.empty: return None
        
        df.index = df.index.tz_convert('Asia/Tokyo')
        # 厳密に「今日」のデータだけに絞る
        df_today = df[df.index.date == today]
        
        if df_today.empty: return None

        if is_afternoon:
            # 12:30以降の最初の足を探す。もし12:30ちょうどがなければ、その直後の足を拾う
            df_pm = df_today.between_time('12:30', '15:00')
            if not df_pm.empty:
                return int(df_pm['Open'].iloc[0])
        else:
            df_am = df_today.between_time('09:00', '11:30')
            if not df_am.empty:
                return int(df_am['Open'].iloc[0])
                
    except Exception:
        pass
    return None
