import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st  # キャッシュ機能のために追加

# --- 指標取得エンジン (Ver 2.01のロジックを3.1用に最適化) ---
@st.cache_data(ttl=300) # 5分間キャッシュ
def fetch_market_info(indices_dict):
    """
    市場指標の値を一括取得する
    """
    data = {}
    for name, ticker in indices_dict.items():
        try:
            # 5日分取得して最新と前日比を算出
            df = yf.download(ticker, period="5d", progress=False)
            if not df.empty:
                # マルチインデックス対策
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                
                latest = float(df['Close'].values.ravel()[-1])
                prev = float(df['Close'].values.ravel()[-2])
                data[name] = {"val": latest, "pct": ((latest - prev) / prev) * 100}
        except: 
            data[name] = {"val": None, "pct": None}
    return data

@st.cache_data(ttl=300)
    
def analyze_market_environment():
    """
    主要指数から今日の相場環境を診断する（為替先物・エラー回避・テキスト簡略化版）
    """
    # 為替先物（6J=F）を指標リストに追加
    indices = {
        "N225": "^N225", "VIX": "^VIX", "DJI": "^DJI",
        "SOX": "^SOX", "WTI": "CL=F", "CME": "NIY=F",
        "USDJPY": "JPY=X", "GOLD": "GC=F",
        "JPY_F": "6J=F"  # シカゴ円先物
    }
    
    data = {}
    for k, ticker in indices.items():
        try:
            # 余裕を持った取得期間設定
            df = yf.download(ticker, period="7d", interval="1d", progress=False)
            if not df.empty and len(df) >= 2:
                # マルチインデックス対策
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                data[k] = df
        except: continue

    # 初期値の設定（ユーザー指定の簡略化テキスト）
    res = {
        "alert_level": "日経25日線との乖離は正常範囲",
        "strategy": 0,
        "opening_forecast": "不明",
        "phase_comment": "本日の市場は比較的落ち着いています。",
        "us_impact": "大きな変動なし",
        "tips": []
    }
    n225_close = 0

    # 1. 警戒レベル (日経平均乖離判定)
    if "N225" in data:
        try:
            df_n = data["N225"]
            n225_close = float(df_n['Close'].values.ravel()[-1])
            n225_ma25 = float(df_n['Close'].rolling(25).mean().values.ravel()[-1])
            dev_rate = ((n225_close - n225_ma25) / n225_ma25) * 100
            if dev_rate > 5.0: res["alert_level"] = "買われ過ぎ。"
            elif dev_rate < -5.0: res["alert_level"] = "売られ過ぎ。"
        except: pass

    # 2. 寄付予測のベース (CME先物 vs 日経現物)
    if "CME" in data and n225_close > 0:
        try:
            cme_val = float(data["CME"]['Close'].values.ravel()[-1])
            diff = cme_val - n225_close
            if diff > 100: res["opening_forecast"] = "ギャップアップ"
            elif diff < -100: res["opening_forecast"] = "ギャップダウン"
        except: pass

    # 3. 戦略 & 相場展望 (VIX判定)
    if "VIX" in data:
        try:
            vix = float(data["VIX"]['Close'].values.ravel()[-1])
            if vix > 25.0:
                res["strategy"] = 1 # ディフェンシブ
                res["phase_comment"] = "VIXが高騰しており市場は不安定です。"
            elif 15.0 <= vix <= 25.0:
                res["strategy"] = 2 # 横ばい
                res["phase_comment"] = "市場にやや迷いが見られます。"
        except: pass

    # 4. 米国株の影響 (NYダウ判定)
    if "DJI" in data:
        try:
            dji_now = float(data["DJI"]['Close'].values.ravel()[-1])
            dji_prev = float(data["DJI"]['Close'].values.ravel()[-2])
            dji_pct = ((dji_now / dji_prev) - 1) * 100
            if dji_pct > 0.5: res["us_impact"] = "米国株の上昇が日本市場の支えとなっています。"
            elif dji_pct < -0.5: res["us_impact"] = "米国株の軟調さが重荷となる可能性があります。"
        except: pass

    # 5. 為替先物によるバイアス判定 (新規追加)
    if "JPY_F" in data:
        try:
            # 円先物の変動率を算出（上昇=円高 / 下落=円安）
            f_now = float(data["JPY_F"]['Close'].values.ravel()[-1])
            f_prev = float(data["JPY_F"]['Close'].values.ravel()[-2])
            f_pct = ((f_now / f_prev) - 1) * 100
            
            # 先物が 0.2% 以上動いている場合に寄付予測にバイアス情報を追記
            if f_pct > 0.2:
                res["opening_forecast"] += " (円高バイアス)"
                if "14:金融　" not in res["tips"]: res["tips"].append("14:金融　")
            elif f_pct < -0.2:
                res["opening_forecast"] += " (円安バイアス)"
                if "11:輸送　" not in res["tips"]: res["tips"].append("11:輸送　")
        except: pass

    # 6. 注目セクター判定 (Gold, 為替, SOX, WTI)
    if "GOLD" in data:
        try:
            g_pct = ((float(data["GOLD"]['Close'].values.ravel()[-1]) / float(data["GOLD"]['Close'].values.ravel()[-2])) - 1) * 100
            if g_pct > 1.0: res["tips"].append("8:金属　")
        except: pass
    
    if "USDJPY" in data:
        try:
            j_now = float(data["USDJPY"]['Close'].values.ravel()[-1])
            j_prev = float(data["USDJPY"]['Close'].values.ravel()[-2])
            j_pct = ((j_now / j_prev) - 1) * 100
            if j_pct > 0.3: 
                res["tips"].extend(["11:輸送　", "10:電機　"])
            elif j_pct < -0.3: 
                res["tips"].extend(["2:水産・食品　", "14:金融　"])
        except: pass

    if "SOX" in data:
        try:
            s_pct = ((float(data["SOX"]['Close'].values.ravel()[-1]) / float(data["SOX"]['Close'].values.ravel()[-2])) - 1) * 100
            if s_pct > 1.0: res["tips"].append("1:AI・半導体　")
        except: pass

    if "WTI" in data:
        try:
            w_pct = ((float(data["WTI"]['Close'].values.ravel()[-1]) / float(data["WTI"]['Close'].values.ravel()[-2])) - 1) * 100
            if w_pct > 1.5: res["tips"].append("6:石油　")
        except: pass

    # 重複セクターの削除と整理
    res["tips"] = list(dict.fromkeys(res["tips"]))
    
    return res
