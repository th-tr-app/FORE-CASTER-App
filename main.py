import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone, time

# 外部モジュールのインポート
from const import TICKER_NAME_MAP, MARKET_INDICES
import logic_core as core

# --- 1. ページ設定 & セッション管理 ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = "7203.T"
if 'res_df' not in st.session_state: st.session_state['res_df'] = pd.DataFrame()
if 't_names' not in st.session_state: st.session_state['t_names'] = {}

# --- 2. デザインCSS (全画面共通) ---
st.markdown("""
    <style>
    .main-title { font-weight: 400 !important; font-size: 38px !important; margin: 0 !important; }
    .sub-title { font-weight: 300 !important; font-size: 16px !important; color: #aaaaaa !important; }
    div[data-testid="stTextInput"] { margin-top: -10px; margin-bottom: 10px; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: repeat(2, 1fr) !important; } }
    .metric-card { border: 1px solid #3d414b; border-radius: 6px; padding: 8px 5px; text-align: center; }
    .card-label { font-size: 11px; color: #aaaaaa; }
    .card-value { font-size: 22px; font-weight: 600; }
    .delta-badge { font-size: 14px; font-weight: 600; }
    .plus { color: #ff4b4b; } .minus { color: #00f0a8; }
    .summary-box { background-color: #262730; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #3d414b; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. サイドバー設定 (戦略プリセット + パラメーター) ---
st.sidebar.markdown("### 🎲 戦略プリセット")
for p, l in [("NORMAL","通常フィルタ"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場")]:
    if st.sidebar.button(l + (" [ 選択中 ]" if st.session_state.get('preset') == p else ""), key=f"ps_{p}"):
        st.session_state['preset'] = p; st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
s_t = st.sidebar.time_input("開始時間", time(9, 0), step=300); e_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)

with st.sidebar.expander("📉 詳細パラメーター"):
    u_vwap = st.sidebar.checkbox("VWAPより上でエントリー", value=True)
    u_ema = st.sidebar.checkbox("EMA5より上でエントリー", value=True)
    u_rsi = st.sidebar.checkbox("RSIが45以上or上向き", value=True)
    u_macd = st.sidebar.checkbox("MACDが上向き", value=True)
    g_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
    g_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100
    ts_s = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
    ts_w = st.sidebar.number_input("下がったら成行注文 (%)", 0.1, 5.0, 0.2, 0.05) / 100
    sl_f = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.5, 0.05) / 100
    u_atr = st.sidebar.checkbox("ATR損切りを使用", value=True)
    a_mul = st.sidebar.number_input("ATR倍率", 0.5, 5.0, 1.5, 0.1)
    a_min = st.sidebar.number_input("最低損切り (%)", 0.1, 5.0, 0.5, 0.1) / 100

params = {
    'days': days_back, 'start_t': s_t, 'end_t': e_t, 'u_vwap': u_vwap, 'u_ema': u_ema, 'u_rsi': u_rsi, 'u_macd': u_macd,
    'g_min': g_min, 'g_max': g_max, 'ts_start': ts_s, 'ts_width': ts_w, 'sl_fix': sl_f, 'u_atr': u_atr, 'atr_mul': a_mul, 'atr_min': a_min
}

# --- 4. メインヘッダー & 【全タブ共通】銘柄入力欄 ---
st.markdown(f"<div><h1 class='main-title'>FORE CASTER</h1><h3 class='sub-title'>ver 3.0 | AI Screening & Backtest</h3></div>", unsafe_allow_html=True)
st.session_state['target_tickers'] = st.text_input("🎯 監視銘柄コード (カンマ区切り)", st.session_state['target_tickers'])

# --- 5. メインタブ構成 ---
tab_top, tab_screen, tab_bt, tab_rank = st.tabs(["🏠 ワンタッチ", "🔍 スクリーニング", "📈 バックテスト", "🏆 ランキング"])

# --- タブ1: ワンタッチ (指標ウォッチ内包) ---
with tab_top:
    m_data = core.fetch_market_info(MARKET_INDICES) # ★修正：引数を渡して呼び出し
    with st.expander(f"🕒 市場指標ウォッチ", expanded=True):
        cards_html = '<div class="metric-grid">'
        for n, t in MARKET_INDICES.items():
            i = m_data.get(n, {})
            if i.get("val"):
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
    
    vix = m_data.get("VIX指数", {}).get("val", 0)
    st.info(f"🤖 **AI予測:** VIX指数は {vix:.1f} です。地合いに合わせた戦略を提案します。")
    if st.button("🚀 ワンタッチ判定：銘柄スキャン実行", type="primary", use_container_width=True):
        st.write("ワンタッチ統合ロジックをここに実装...")

# --- タブ2: スクリーニング ---
with tab_screen:
    st.markdown("### 🔍 スクリーニング詳細設定")
    
    # サイドバーのプリセット選択に合わせて初期表示を切り替える
    preset_names = ["通常フィルタ", "ディフェンシブ", "横ばい相場"]
    preset_idx = 0 if st.session_state['preset'] == "NORMAL" else 1 if st.session_state['preset'] == "DEFENSIVE" else 2
    
    s_tabs = st.tabs(preset_names)
    
    # 各プリセット（タブ）ごとの設定項目をループで生成
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            exp_label = f"⚙️ {preset_names[i]} の抽出条件"
            # 選択中のプリセットの場合は最初から展開しておく
            with st.expander(exp_label, expanded=(i == preset_idx)):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**【基本属性】**")
                    c_p = st.checkbox("株価範囲", True, key=f"sc_p_{i}")
                    p_rng = st.slider("株価(円)", 100, 10000, (500, 5000), 100, key=f"sv_p_{i}")
                    
                    c_v = st.checkbox("売買代金(億円)", True, key=f"sc_v_{i}")
                    v_min = st.number_input("億円以上", value=50.0 if i==0 else 300.0 if i==1 else 200.0, key=f"sv_v_{i}")
                    
                    c_atrp = st.checkbox("平均値幅(ATR%)", i!=0, key=f"sc_atrp_{i}")
                    atrp_rng = st.slider("ATR%範囲", 0.5, 5.0, (2.0, 4.0) if i==0 else (1.0, 2.5), 0.1, key=f"sv_atrp_{i}")

                with c2:
                    st.markdown("**【トレンド・勢い】**")
                    c_rsi = st.checkbox("RSI(14日)", True, key=f"sc_rsi_{i}")
                    rsi_rng = st.slider("RSI範囲", 0, 100, (55, 70) if i==0 else (40, 55), 5, key=f"sv_rsi_{i}")
                    
                    c_adx = st.checkbox("ADX(トレンド強度)", i!=0, key=f"sc_adx_{i}")
                    adx_rng = st.slider("ADX強度", 0, 100, (25, 40) if i==0 else (10, 20), 5, key=f"sv_adx_{i}")
                    
                    c_rci = st.checkbox("RCI(9日/過熱感)", i!=0, key=f"sc_rci_{i}")
                    rci_rng = st.slider("RCI範囲", -100, 100, (20, 80) if i==0 else (-30, 30), 5, key=f"sv_rci_{i}")

                with c3:
                    st.markdown("**【流動性・乖離】**")
                    c_vol = st.checkbox("出来高(万株)", True, key=f"sc_vol_{i}")
                    vol_min = st.number_input("万株以上", value=10.0, key=f"sv_vol_{i}")
                    
                    c_vup = st.checkbox("出来高増加率(前日比)", i!=0, key=f"sc_vup_{i}")
                    vup_min = st.slider("増加倍率", 1.0, 5.0, 1.3 if i==0 else 1.1, 0.1, key=f"sv_vup_{i}")
                    
                    c_ma25 = st.checkbox("25日移動平均乖離率", True, key=f"sc_ma25_{i}")
                    ma25_rng = st.slider("偏差%", -20.0, 20.0, (0.0, 7.0) if i==0 else (-3.0, 2.0), 1.0, key=f"sv_ma25_{i}")

            # スクリーニング実行ボタン
            if st.button(f"🔍 {preset_names[i]} でスキャン実行", type="primary", use_container_width=True, key=f"run_sc_{i}"):
                # 設定パラメータの集約
                s_params = {
                    'c_p': c_p, 'p_range': p_rng, 'c_v': c_v, 'v_min': v_min, 
                    'c_atrp': c_atrp, 'atrp_range': atrp_rng, 'c_rsi': c_rsi, 'rsi_range': rsi_rng,
                    'c_adx': c_adx, 'adx_range': adx_rng, 'c_rci': c_rci, 'rci_range': rci_rng,
                    'c_vol': c_vol, 'vol_min': vol_min, 'c_vup': c_vup, 'vup_min': vup_min,
                    'c_ma25': c_ma25, 'ma25_range': ma25_rng
                }
                
                # スキャン実行
                all_tickers = list(TICKER_NAME_MAP.keys())
                screened_results = []
                
                with st.status(f"🔍 {preset_names[i]} 条件で全銘柄をチェック中...", expanded=True) as status:
                    pb = st.progress(0)
                    for idx, t in enumerate(all_tickers):
                        pb.progress((idx + 1) / len(all_tickers))
                        # 日次データの取得（スクリーニングは日次で行う）
                        df_d = yf.download(t, period="3mo", interval="1d", progress=False, auto_adjust=False)
                        if df_d.empty: continue
                        
                        # logic_core の判定関数を呼び出し
                        res = core.evaluate_screening_conditions(df_d, s_params)
                        if res:
                            res['コード'] = t
                            res['銘柄名'] = TICKER_NAME_MAP.get(t, t)
                            screened_results.append(res)
                    status.update(label="✅ スキャン完了！", state="complete")

                if screened_results:
                    res_df = pd.DataFrame(screened_results)
                    st.success(f"🎯 {len(res_df)} 銘柄が条件に合致しました。")
                    
                    # 転送機能付きデータフレーム
                    sel_sc = st.dataframe(
                        res_df[['コード', '銘柄名', '株価', '前日比', '売買代金', 'ATR%']],
                        use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"df_sc_{i}"
                    )
                    
                    # 監視リストへの追加
                    if sel_sc.selection.rows:
                        sel_tickers = res_df.iloc[sel_sc.selection.rows]['コード'].tolist()
                        if st.button(f"➕ 選択した {len(sel_tickers)} 銘柄を監視リストに追加", key=f"add_sc_{i}"):
                            current = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
                            st.session_state['target_tickers'] = ", ".join(list(set(current + sel_tickers)))
                            st.rerun()
                else:
                    st.warning("合致する銘柄が見つかりませんでした。条件を緩めてください。")

# --- タブ3: バックテスト (6.3の全タブ移植) ---
with tab_bt:
    if st.button("📊 個別バックテスト実行", type="primary", use_container_width=True):
        t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
        end_date = datetime.now(); start_date = end_date - timedelta(days=days_back)
        all_trades = []; t_names = {}; pb = st.progress(0); st_text = st.empty()
        for i, t in enumerate(t_list):
            st_text.text(f"Testing {t}..."); pb.progress((i+1)/len(t_list))
            df = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
            p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
            all_trades.extend(core.run_ticker_simulation(t, df, p_map, o_map, a_map, params))
            t_names[t] = TICKER_NAME_MAP.get(t, t)
        st.session_state['res_df'] = pd.DataFrame(all_trades); st.session_state['t_names'] = t_names
        st.session_state['bt_period'] = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        st.rerun()

    # 分析結果サブタブの展開
    res_df = st.session_state['res_df']; t_names = st.session_state['t_names']
    if not res_df.empty:
        bt_tabs = st.tabs(["📊 サマリー", "🏅 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ"])
        
        with bt_tabs[0]: # 📊 サマリー
            wins = res_df[res_df['PnL'] > 0]; losses = res_df[res_df['PnL'] <= 0]
            st.markdown(f"<div class='metric-grid'>"
                f"<div class='summary-box'><div class='card-label'>回数</div><div class='card-value'>{len(res_df)}</div></div>"
                f"<div class='summary-box'><div class='card-label'>勝率</div><div class='card-value'>{(len(wins)/len(res_df)):.1%}</div></div>"
                f"<div class='summary-box'><div class='card-label'>PF</div><div class='card-value'>{(wins['PnL'].sum()/abs(losses['PnL'].sum()) if not losses.empty else 0):.2f}</div></div>"
                f"<div class='summary-box'><div class='card-label'>期待値</div><div class='card-value'>{res_df['PnL'].mean():.2%}</div></div>"
                f"</div>", unsafe_allow_html=True)
            # レポートテキスト
            rpt = ["=================\n BACKTEST REPORT \n================="]
            for t in res_df['Ticker'].unique():
                tdf = res_df[res_df['Ticker'] == t]; tw = tdf[tdf['PnL']>0]['PnL']; tl = tdf[tdf['PnL']<=0]['PnL']
                rpt.append(f">>> TICKER: {t} | {t_names.get(t,t)}\nトレード数: {len(tdf)} | 勝率: {(len(tw)/len(tdf)):.1%} | PF: {(tw.sum()/abs(tl.sum()) if not tl.empty else 9.9):.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            st.code("\n".join(rpt), language="text")

        with bt_tabs[5]: # 📝 詳細ログ
            log_report = []
            for t in res_df['Ticker'].unique():
                tdf = res_df[res_df['Ticker'] == t].copy().sort_values('Entry', ascending=False)
                log_report.append(f"[{t}] {t_names.get(t, t)} 取引履歴\n" + "-"*80)
                for _, row in tdf.iterrows():
                    vwap_dev = ((row['In'] - row['EntryVWAP']) / row['EntryVWAP']) * 100
                    log_report.append(f"{row['Entry'].strftime('%Y-%m-%d %H:%M')} | {row['Pattern']} | PnL: {row['PnL']:+.2%} | 買：{int(row['In'])} | 売：{int(row['Out'])} | VWAP乖離: {vwap_dev:+.2f}% | {row['Reason']}")
                log_report.append("\n")
            st.code("\n".join(log_report), language="text")

        if st.button("♻️ 個別テスト結果をリセット", key="reset_bt_tab", use_container_width=True):
            st.session_state['res_df'] = pd.DataFrame(); st.rerun()

# --- タブ4: ランキング (エラー修正 & 機能復旧版) ---
with tab_rank:
    st.markdown("### 🏆 登録銘柄期待値ランキング")
    
    # 1. 価格帯フィルターの設定
    p_range = st.slider("価格帯フィルター (円)", 0, 20000, (500, 5000), 500, key="rank_p_range")
    
    # 2. ランキング生成ボタン
    if st.button("🚀 ランキング生成開始", type="primary", use_container_width=True):
        rank_list = []
        all_tickers = list(TICKER_NAME_MAP.keys())
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        with st.status("🔍 全231銘柄を分析中...", expanded=True) as status:
            pb_r = st.progress(0)
            for i, t in enumerate(all_tickers):
                status.update(label=f"Scanning {i+1}/{len(all_tickers)}: {t}")
                pb_r.progress((i+1)/len(all_tickers))
                
                # データのダウンロードとMultiIndex対策
                df_r = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
                if df_r.empty: continue
                if isinstance(df_r.columns, pd.MultiIndex):
                    df_r.columns = df_r.columns.get_level_values(0)
                
                try:
                    # 確実に数値(scalar)として取得して比較
                    current_p = float(df_r['Close'].iloc[-1])
                    if not (p_range[0] <= current_p <= p_range[1]): 
                        continue
                    
                    # シミュレーション実行とスコア算出
                    p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
                    t_trades = core.run_ticker_simulation(t, df_r, p_map, o_map, a_map, params)
                    
                    if t_trades:
                        score_data = core.get_one_touch_score(t_trades)
                        rank_list.append({
                            'コード': t, '銘柄名': TICKER_NAME_MAP.get(t, t),
                            '勝率': score_data['win_rate'], 'PF': score_data['pf'], '期待値': score_data['ev']
                        })
                except:
                    continue
            
            status.update(label="✅ スキャン完了！", state="complete")
        
        if rank_list:
            # 期待値順に並べて上位20件を保持
            st.session_state['last_rank_df'] = pd.DataFrame(rank_list).sort_values('期待値', ascending=False).head(20)
            st.rerun()

    # 3. 結果の表示と監視リストへの転送機能
    if 'last_rank_df' in st.session_state:
        rdf = st.session_state['last_rank_df']
        st.caption("👇 表の左端をクリックして選択し、「監視リストに追加」を押してください。")
        
        # 選択機能付きのデータフレーム
        event = st.dataframe(
            rdf.style.format({'勝率': '{:.1%}', '期待値': '{:+.2%}', 'PF': '{:.2f}'}),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row"
        )
        
        # 選択された行がある場合の追加処理
        selected_rows = event.selection.rows
        if selected_rows:
            selected_tickers = rdf.iloc[selected_rows]['コード'].tolist()
            if st.button(f"➕ 選択した {len(selected_tickers)} 銘柄を監視リストに追加", use_container_width=True):
                # 現在の入力リストと統合（重複排除）
                current = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
                updated_list = sorted(list(set(current + selected_tickers)))
                st.session_state['target_tickers'] = ", ".join(updated_list)
                st.toast(f"{len(selected_tickers)} 銘柄を最上部の監視リストに追加しました！")
                st.rerun()

        if st.button("♻️ ランキング結果をクリア", key="clear_rank", use_container_width=True):
            del st.session_state['last_rank_df']
            st.rerun()
