import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone, time

# 外部モジュールのインポート
from const import SECTOR_MAP, TICKER_DETAILS, MARKET_INDICES
import logic_core as core

# --- 1. ページ設定 & セッション管理 (永続化の定義) ---
st.set_page_config(page_title="FORE CASTER", page_icon="image_12.png", layout="wide")
st.logo("image_13.png", icon_image="image_12.png")

# 基本情報の初期化
if 'target_tickers' not in st.session_state: st.session_state['target_tickers'] = ""
if 'preset' not in st.session_state: st.session_state['preset'] = "NORMAL"
if 'res_df' not in st.session_state: st.session_state['res_df'] = pd.DataFrame()
if 't_names' not in st.session_state: st.session_state['t_names'] = {}

# main.py 冒頭：sc_params の初期値を新しいIDに合わせて修正
# --- 戦略別パラメーターの最適化（実戦テスト反映版） ---
if 'sc_params' not in st.session_state:
    st.session_state['sc_params'] = [
        # 🔍 通常フィルター：全業種を対象にトレンドを追う
        {
            'sector': [0], # 全業種
            'c_gain': True, 'gain_rng': (0.5, 5.0), 
            'c_p': True, 'p_rng': (300, 6000),          # 通常：300〜6000
            'c_v': True, 'v_min': 30.0, 
            'c_atrp': False, 'atrp_rng': (1.5, 5.0), 
            'c_ma': True, 'ma_opt': "最強：上昇トレンド", 
            'c_ema': True, 'ema_opt': "強気：EMAの上で価格維持", 
            'c_adx': False, 'adx_rng': (20, 100), 
            'c_rci': False, 'rci_rng': (0, 100), 
            'c_rsi': True, 'rsi_rng': (50, 80), 
            'c_vup': False, 'vup_min': 1.2, 
            'c_ma25': True, 'ma25_rng': (0.0, 10.0), 
            'c_bb': True, 'bb_rng': (0.5, 2.5)
        },
        # 🛡️ ディフェンシブ：【守り】ボラティリティを徹底的に抑える
        {
            'sector': [2, 5, 13, 14, 16], 
            'c_gain': False, 'gain_rng': (-2.0, 1.0), 
            'c_p': True, 'p_rng': (500, 6000), 
            'c_v': True, 'v_min': 50.0,      # 高い流動性を維持
            'c_atrp': True, 'atrp_rng': (0.5, 2.0), # 低ボラに絞る (2.5→2.0)
            'c_ma': False, 'ma_opt': "収束：嵐の前の静けさ", 
            'c_ema': False, 'ema_opt': "安定：EMA付近での推移", 
            'c_adx': False, 'adx_rng': (0, 30), 
            'c_rci': False, 'rci_rng': (-80, 20), 
            'c_rsi': True, 'rsi_rng': (40, 65),     # 上限を下げて過熱感を排除
            'c_vup': False, 'vup_min': 1.0, 
            'c_ma25': True, 'ma25_rng': (-2.0, 5.0), # 25日線付近の安定株に限定
            'c_bb': False, 'bb_rng': (-2.0, 0.5)
        },
        # ↔️ 横ばい相場：【攻め】売られすぎからの「リバウンド」に特化。若干順張り寄り。
        {
            'sector': [2, 3, 4, 8, 9], 
            'c_gain': True, 'gain_rng': (-1.0, 3.0), # 上限を少し広げる
            'c_p': True, 'p_rng': (200, 6000), 
            'c_v': True, 'v_min': 20.0, 
            'c_atrp': True, 'atrp_rng': (1.5, 4.0), # ある程度の値幅が必要 (1.0→1.5)
            'c_ma': True, 'ma_opt': "リバウンド：短期MA上抜け", 
            'c_ema': False, 'ema_opt': "レンジ：EMAを上下にまたぐ", 
            'c_adx': False, 'adx_rng': (10, 30), 
            'c_rci': True, 'rci_rng': (-70, 0),     # 逆張りのためにマイナス圏を指定。-90～-30 から、少し上の -70～0 へ
            'c_rsi': True, 'rsi_rng': (35, 55),     # 売られすぎ圏からの脱出を狙う。30～50 から、少し上の 35～55 へ
            'c_vup': True, 'vup_min': 1.2,          # 資金流入の兆しを重視 (1.1→1.2)
            'c_ma25': True, 'ma25_rng': (-5.0, 2.0), # 大幅乖離からの戻りを狙う。マイナス圏限定から、25日線付近まで許可
            'c_bb': False, 'bb_rng': (-1.0, 1.0)
        }
    ]

# 各タブのスキャン結果保持用
for i in range(3):
    if f"sc_res_df_{i}" not in st.session_state: st.session_state[f"sc_res_df_{i}"] = None

# --- 2. デザインCSSの読み込み (style.css) ---
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# style.css を読み込む
local_css("style.css")

# --- 3. サイドバー設定 (戦略プリセット + バックテスト設定) ---
st.sidebar.header("🎲 戦略実行プリセット")
for p, l in [("NORMAL","通常フィルター"), ("DEFENSIVE","ディフェンシブ"), ("RANGE","横ばい相場対応")]:
    is_sel = (st.session_state['preset'] == p)
    # 重複エラーを防ぐためキーを一意にする
    if st.sidebar.button(l + (" [ 選択中 ]" if is_sel else ""), key=f"side_ps_btn_{p}", type="primary" if is_sel else "secondary"):
        st.session_state['preset'] = p
        st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ バックテスト設定")
days_back = st.sidebar.slider("過去何日分を取得", 10, 59, 59)
s_t = st.sidebar.time_input("開始時間", time(9, 0), step=300); e_t = st.sidebar.time_input("終了時間", time(9, 15), step=300)
st.sidebar.write("")
st.sidebar.header("📈 エントリー条件")
u_vwap = st.sidebar.checkbox("VWAPより上でエントリー", value=True)
u_ema = st.sidebar.checkbox("EMA5より上でエントリー", value=True)
u_rsi = st.sidebar.checkbox("RSIが45以上or上向き", value=True)
u_macd = st.sidebar.checkbox("MACDが上向き", value=True)
st.sidebar.write("")
st.sidebar.write("")
g_min = st.sidebar.slider("寄付ダウン下限 (%)", -10.0, 0.0, -3.0, 0.05) / 100
g_max = st.sidebar.slider("寄付アップ上限 (%)", -5.0, 5.0, 1.0, 0.05) / 100
st.sidebar.divider()
st.sidebar.header("💰 決済ルール")
ts_s = st.sidebar.number_input("トレイリング開始 (%)", 0.1, 5.0, 0.5, 0.05) / 100
ts_w = st.sidebar.number_input("トレイリング幅 (%)", 0.1, 5.0, 0.2, 0.05) / 100
sl_f = st.sidebar.number_input("損切り (%)", -5.0, -0.1, -0.5, 0.05) / 100
st.sidebar.divider()
st.sidebar.header("📉 動的損切り設定")
u_atr = st.sidebar.checkbox("ATR損切りを使用", value=True)
a_mul = st.sidebar.number_input("ATR倍率", 0.5, 5.0, 1.5, 0.1)
a_min = st.sidebar.number_input("最低損切り (%)", 0.1, 5.0, 0.5, 0.1) / 100

params = {
    'days': days_back, 'start_t': s_t, 'end_t': e_t, 'u_vwap': u_vwap, 'u_ema': u_ema, 'u_rsi': u_rsi, 'u_macd': u_macd,
    'g_min': g_min, 'g_max': g_max, 'ts_start': ts_s, 'ts_width': ts_w, 'sl_fix': sl_f, 'u_atr': u_atr, 'atr_mul': a_mul, 'atr_min': a_min
}

# --- 4. メインヘッダー & 【全タブ共通】銘柄入力欄 ---
st.markdown(f"<div class='header-container'><h1 class='main-title'>FORE CASTER</h1><p class='sub-title'>SCREENING & BACKTEST | ver 4.5</p></div>", unsafe_allow_html=True)

# 【修正ポイント】key="target_tickers" を削除し、value= を使用します
ticker_input_val = st.text_input(
    "銘柄コード (カンマ区切り)", 
    value=st.session_state['target_tickers']
)

# ユーザーが直接手入力した場合、セッション状態を更新してリラン
if ticker_input_val != st.session_state['target_tickers']:
    st.session_state['target_tickers'] = ticker_input_val
    st.rerun()

# --- 5. メインタブ構成 ---
tab_top, tab_screen, tab_bt, tab_strategy, tab_rank = st.tabs(["🏠 ワンタッチ", "🔍 スキャン", "📈 バックテスト", "✨ 指値戦略", "🏆 ランキング"])

# --- タブ1: ワンタッチ (FC 3.3：統合修正版) ---
with tab_top:
    # 1. 日本時間の定義と取得 (指定フォーマット: YYYY/MM/DD/HH:MM)
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime('%Y/%m/%d/%H:%M')
    
    # 2. データの取得 (logic_core の関数を呼び出し)
    m_data = core.fetch_market_info(MARKET_INDICES)
    diag = core.analyze_market_environment()
    
    strat_names = ["通常フィルター", "ディフェンシブ", "横ばい相場"]
    rec_strat = strat_names[diag["strategy"]]
    
    # 3. 市場指標ウォッチの表示
    with st.expander("🕒 指標ウォッチ（タップで開閉）", expanded=False):
        # 【修正】指定形式の時刻入り更新ボタン
        if st.button(f"🔄 更新 ▶︎ {now_jst}", use_container_width=True, key="refresh_top_btn"):
            st.cache_data.clear()
            st.rerun()
            
        # A. 指標カードの表示
        cards_html = '<div class="metric-grid">'
        for n, t in MARKET_INDICES.items():
            i = m_data.get(n, {})
            if i.get("val") is not None:
                v = f"{i['val']:,.1f}" if i['val'] > 200 else f"{i['val']:,.2f}"
                cls = "plus" if i['pct'] >= 0 else "minus"
                cards_html += f'<div class="metric-card"><div class="card-label">{n}</div><div class="card-value">{v}</div><div class="delta-badge {cls}">{"＋" if i["pct"]>=0 else ""}{i["pct"]:.2f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)
        
        # B. 今日のマーケットAI診断（最新ロジック反映版）
        # main.py の診断表示部分
        diag_html = f"""
        <div class="ai-diagnosis-box">
            <div class="ai-diag-header-container">
                <div class="ai-diag-main-title">📀 今日のマーケットAI診断</div>
                <div class="ai-diag-status-badge">{diag['alert_level']}</div>
            </div>
            <div class="ai-diag-row"><b>バランス：</b> {diag['balance']}</div>
            <div class="ai-diag-row"><b>推奨戦略：</b> {rec_strat}</div>
            <div class="ai-diag-row"><b>{diag.get('forecast_title', '寄付予測')}：</b> {diag['opening_forecast']}</div>
            <div class="ai-diag-row"><b>相場展望：</b> {diag['phase_comment']}</div>
            <div class="ai-diag-row-last"><b>米国株の影響：</b> {diag['us_impact']}</div>
            <h4 class="ai-diag-main-title">👀 指標から推測できる注目セクター</h4>
            <div class="ai-sector-tips">{diag.get('tips', '個別材料株（全業種対象）')}</div>
        </div>
        <div class="ai-diag-footer"></div>
        """
        st.markdown(diag_html, unsafe_allow_html=True)

    # 4. ワンタッチ判定：全自動スキャン開始ボタン
    if st.button("👉 ワンタッチ／銘柄候補を自動で選出", type="primary", use_container_width=True, key="ot_full_scan_btn"):
        current_preset = st.session_state['preset'] 
        p_idx = 0 if current_preset == "NORMAL" else 1 if current_preset == "DEFENSIVE" else 2
        p = st.session_state['sc_params'][p_idx]
        
        s_logic_params = {
            'c_gain': p.get('c_gain'), 'gain_range': p.get('gain_rng'),
            'c_p': p.get('c_p'), 'p_range': p.get('p_rng'), 'c_v': p.get('c_v'), 'v_min': p.get('v_min'), 
            'c_atrp': p.get('c_atrp'), 'atrp_range': p.get('atrp_rng'), 'c_ma': p.get('c_ma'), 'ma_opt': p.get('ma_opt'), 
            'c_ema': p.get('c_ema'), 'ema_opt': p.get('ema_opt'), 'c_adx': p.get('c_adx'), 'adx_range': p.get('adx_rng'), 
            'c_rci': p.get('c_rci'), 'rci_range': p.get('rci_rng'), 'c_rsi': p.get('c_rsi'), 'rsi_range': p.get('rsi_rng'),
            'c_vup': p.get('c_vup'), 'vup_min': p.get('vup_min'), 'c_ma25': p.get('c_ma25'), 'ma25_range': p.get('ma25_rng'),
            'c_bb': p.get('c_bb'), 'bb_range': p.get('bb_rng')
        }
        
        # 【修正】業種フィルターの適用
        selected_sids = p.get('sector', [0])
        if 0 in selected_sids or not selected_sids:
            all_tickers = list(TICKER_DETAILS.keys())
        else:
            all_tickers = [t for t, d in TICKER_DETAILS.items() if d[1] in selected_sids]
            
        ot_results = []
        
        with st.status(f"🔍 {current_preset} 戦略で全銘柄をフル分析中...", expanded=True) as status:
            pb_ot = st.progress(0)
            for idx, t in enumerate(all_tickers):
                pb_ot.progress((idx+1)/len(all_tickers))
                status.update(label=f"分析中 ({idx+1}/{len(all_tickers)}): {t}")
                
                df_d = yf.download(t, period="3mo", interval="1d", progress=False)
                if not df_d.empty:
                    if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.get_level_values(0)
                    scr_res = core.evaluate_screening_conditions(df_d, s_logic_params)
                    if scr_res:
                        end_date = datetime.now(); start_date = end_date - timedelta(days=days_back)
                        df_5m = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
                        
                        if not df_5m.empty:
                            if isinstance(df_5m.columns, pd.MultiIndex): df_5m.columns = df_5m.columns.get_level_values(0)
                            p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
                            trades = core.run_ticker_simulation(t, df_5m, p_map, o_map, a_map, params)
                            score_data = core.get_one_touch_score(trades)
                            if score_data:
                                # 【修正】項目の追加
                                ot_results.append({
                                    'コード': t, '銘柄名': TICKER_DETAILS.get(t, [t])[0],
                                    '前日比': scr_res.get('前日比', 0), '回数': score_data['count'],
                                    '勝率': score_data['win_rate'], '利益平均': score_data['avg_win'],
                                    '損失平均': score_data['avg_loss'], 'PF': score_data['pf'],
                                    '期待値': score_data['ev'], '総合スコア': score_data['score']
                                })
                                
            status.update(label="✅ 分析完了！", state="complete")

        # 結果の保存と0件フラグ制御
        if ot_results:
            top_5_df = pd.DataFrame(ot_results).sort_values('総合スコア', ascending=False).head(5)
            st.session_state['ot_last_top5'] = top_5_df
            st.session_state['ot_no_results'] = False
            
            # 監視リスト反映
            current_str = st.session_state.get('target_tickers', "")
            current_list = [t.strip() for t in current_str.split(",") if t.strip()]
            combined_list = sorted(list(set(current_list + top_5_df['コード'].tolist())))
            st.session_state['target_tickers'] = ", ".join(combined_list)
            st.rerun()
        else:
            st.session_state['ot_no_results'] = True
            st.session_state.pop('ot_last_top5', None)
            st.rerun()

    # --- 【修正】スキャン実行後に結果が0件だった時の通知 ---
    if st.session_state.get('ot_no_results'):
        st.warning("⚠️ 条件に合致する銘柄が見つかりませんでした。")

    # --- 厳選トップ5のリスト表示（10項目 ＆ ％表記版） ---
    if 'ot_last_top5' in st.session_state:
        st.markdown("### 🏆本日の厳選銘柄トップ５")
        rdf_ot = st.session_state['ot_last_top5']
        
        # 表示する列の順番を指定し、％表記を適用
        st.dataframe(
            rdf_ot[['コード', '銘柄名', '前日比', '回数', '勝率', '利益平均', '損失平均', 'PF', '期待値', '総合スコア']].style.format({
                '前日比': '{:+.2f}%', 
                '勝率': '{:.1%}', 
                '利益平均': '{:+.2%}', 
                '損失平均': '{:+.2%}', 
                '期待値': '{:+.2%}', 
                'PF': '{:.2f}', 
                '総合スコア': '{:.2%}' # 0.0190 → 1.90% に変換
            }),
            use_container_width=True, hide_index=True, selection_mode=None
        )
        
        if st.button("♻️ ワンタッチ結果をクリア", key="ot_clear_res_btn"):
            del st.session_state['ot_last_top5']
            st.session_state['ot_no_results'] = False
            st.rerun()
            
# --- タブ2: スクリーニングの実装 (12パラメーター対応版) ---
with tab_screen:
    st.markdown("<br>", unsafe_allow_html=True)
    s_tabs = st.tabs(["🔍 通常フィルタ", "🔍 ディフェンシブ", "🔍 横ばい相場"])
    
    for i, s_tab in enumerate(s_tabs):
        with s_tab:
            p = st.session_state['sc_params'][i]
            exp_t = f"🔍 スクリーニング設定 ({['通常フィルタ', 'ディフェンシブ', '横ばい相場'][i]})"
            
            # --- 1. パラメーター設定エリア ---
            with st.expander(exp_t, expanded=False):
                # --- A. 業種選択 ---
                p['sector'] = st.pills(
                    "**対象業種 (タップで複数選択)**",
                    options=list(SECTOR_MAP.keys()),
                    format_func=lambda x: f"{SECTOR_MAP[x]}",
                    selection_mode="multi",
                    default=p['sector'],
                    key=f"v_sector_pill_{i}"
                )
                st.divider()
 
                c1, c2, c3 = st.columns(3)
                with c1:
                    p['c_p'] = st.checkbox("**株価の範囲**", p['c_p'], key=f"c_p_{i}")
                    # メモリを 100〜10000 に統一、ステップを 100円刻みに設定
                    p['p_rng'] = st.slider("価格(円)", 100, 10000, p['p_rng'], step=100, key=f"v_p_{i}")
                    st.divider()
                    p['c_v'] = st.checkbox("**売買代金**", p['c_v'], key=f"c_v_{i}")
                    p['v_min'] = st.number_input("億円以上", value=p['v_min'], step=10.0, key=f"v_v_{i}")
                    st.divider()
                    p['c_atrp'] = st.checkbox("**平均値幅 (ATR%)**", p['c_atrp'], key=f"c_atrp_{i}")
                    p['atrp_rng'] = st.slider("期待範囲%", 0.5, 5.0, p['atrp_rng'], step=0.1, key=f"v_atrp_{i}")
                    st.divider()
                    p['c_ma'] = st.checkbox("**移動平均上抜け/並び**", p['c_ma'], key=f"c_ma_{i}")
                    p['ma_opt'] = st.selectbox("条件選択", ["最強：上昇トレンド", "転換：GC直後", "収束：嵐の前の静けさ", "リバウンド：短期MA上抜け"], index=["最強：上昇トレンド", "転換：GC直後", "収束：嵐の前の静けさ", "リバウンド：短期MA上抜け"].index(p['ma_opt']), key=f"v_ma_{i}")
                    st.divider()

                with c2:
                    p['c_gain'] = st.checkbox("**前日値上がり率 (%)**", p['c_gain'], key=f"c_gain_{i}")
                    p['gain_rng'] = st.slider("変動幅%", -10.0, 10.0, p['gain_rng'], step=0.5, key=f"v_gain_{i}")
                    st.divider()
                    p['c_ema'] = st.checkbox("**EMA (9日・21日)**", p['c_ema'], key=f"c_ema_{i}")
                    p['ema_opt'] = st.selectbox("EMA基準", ["強気：EMAの上で価格維持", "安定：EMA付近での推移", "レンジ：EMAを上下にまたぐ"], index=["強気：EMAの上で価格維持", "安定：EMA付近での推移", "レンジ：EMAを上下にまたぐ"].index(p['ema_opt']), key=f"v_ema_{i}")
                    st.divider()
                    p['c_adx'] = st.checkbox("**ADX (強度)**", p['c_adx'], key=f"c_adx_{i}")
                    p['adx_rng'] = st.slider("強度スコア", 0, 100, p['adx_rng'], step=5, key=f"v_adx_{i}")
                    st.divider()
                    p['c_rci'] = st.checkbox("**RCI (過熱感)**", p['c_rci'], key=f"c_rci_{i}")
                    p['rci_rng'] = st.slider("RCI範囲", -100, 100, p['rci_rng'], step=5, key=f"v_rci_{i}")
                    st.divider()

                with c3:
                    p['c_rsi'] = st.checkbox("**RSI (レンジ)**", p['c_rsi'], key=f"c_rsi_{i}")
                    p['rsi_rng'] = st.slider("RSIレンジ", 0, 100, p['rsi_rng'], step=5, key=f"v_rsi_{i}")
                    st.divider()
                    p['c_vup'] = st.checkbox("**出来高増加率**", p['c_vup'], key=f"c_vup_{i}")
                    p['vup_min'] = st.slider("増加倍率", 1.0, 5.0, p['vup_min'], step=0.1, key=f"v_vup_{i}")
                    st.divider()
                    p['c_ma25'] = st.checkbox("**25MA乖離率**", p['c_ma25'], key=f"c_ma25_{i}")
                    p['ma25_rng'] = st.slider("偏差%", -20.0, 20.0, p['ma25_rng'], step=1.0, key=f"v_ma25_{i}")
                    st.divider()
                    p['c_bb'] = st.checkbox("**ボリンジャーバンド**", p['c_bb'], key=f"c_bb_{i}")
                    p['bb_rng'] = st.slider("σ範囲", -3.0, 3.0, p['bb_rng'], step=1.0, key=f"v_bb_{i}")
                    st.divider()

            # --- 2. スクリーニング実行 (計算のみ) ---
            if st.button(f"{['通常フィルタ', 'ディフェンシブ', '横ばい相場'][i]} スキャン開始", key=f"btn_sc_exec_{i}", type="primary", use_container_width=True):
                # (スキャン実行ロジックは変更なし)
                selected_sids = p['sector']
                if 0 in selected_sids or not selected_sids:
                    target_tickers = list(TICKER_DETAILS.keys())
                    scan_label = "全業種"
                else:
                    target_tickers = [t for t, d in TICKER_DETAILS.items() if d[1] in selected_sids]
                    scan_label = ", ".join([SECTOR_MAP[sid] for sid in selected_sids])
                
                s_logic_params = {
                    'c_gain': p['c_gain'], 'gain_range': p['gain_rng'],
                    'c_p': p['c_p'], 'p_range': p['p_rng'], 'c_v': p['c_v'], 'v_min': p['v_min'], 
                    'c_atrp': p['c_atrp'], 'atrp_range': p['atrp_rng'], 'c_ma': p['c_ma'], 'ma_opt': p['ma_opt'],
                    'c_ema': p['c_ema'], 'ema_opt': p['ema_opt'], 'c_adx': p['c_adx'], 'adx_range': p['adx_rng'], 
                    'c_rci': p['c_rci'], 'rci_range': p['rci_rng'], 'c_rsi': p['c_rsi'], 'rsi_range': p['rsi_rng'],
                    'c_vup': p['c_vup'], 'vup_min': p['vup_min'],
                    'c_ma25': p['c_ma25'], 'ma25_range': p['ma25_rng'], 'c_bb': p['c_bb'], 'bb_range': p['bb_rng']
                }

                results = []
                with st.status(f"🔍 {scan_label} をスキャン中...", expanded=True) as status:
                    pb = st.progress(0)
                    for idx, t in enumerate(target_tickers):
                        pb.progress((idx+1)/len(target_tickers))
                        df_d = yf.download(t, period="3mo", interval="1d", progress=False)
                        if not df_d.empty:
                            if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.get_level_values(0)
                            res = core.evaluate_screening_conditions(df_d, s_logic_params)
                            if res:
                                res['コード'] = t
                                res['銘柄名'] = TICKER_DETAILS[t][0]
                                results.append(res)
                    status.update(label=f"✅ {len(results)} 銘柄発見", state="complete")
                
                # 【修正】結果の保存と同時に0件フラグを制御
                st.session_state[f"sc_res_df_{i}"] = pd.DataFrame(results) if results else None
                # スキャン実行後の0件判定フラグを設定
                st.session_state[f"sc_no_results_{i}"] = True if not results else False
                st.rerun()

            # --- 【修正】スキャン実行後に結果が0件だった時の通知 ---
            if st.session_state.get(f"sc_no_results_{i}"):
                st.warning("⚠️ 条件に合致する銘柄が見つかりませんでした。")

            # --- 結果表示 (並び替え・全件表示・書式設定済み) ---
            current_res = st.session_state.get(f"sc_res_df_{i}")
            if current_res is not None and not current_res.empty:
                # (以降、st.info や st.dataframe 表示ロジックは維持)
                st.caption("👇 チェックを入れると銘柄リストに追加できます。")
                st.markdown("<br>", unsafe_allow_html=True)
                current_res = current_res.sort_values("売買代金", ascending=False)
                df_height = (len(current_res) + 1) * 35 + 5 # 縦スクロール防止
                
                sel_event = st.dataframe(
                    current_res[['コード', '銘柄名', '株価', '前日比', 'RSI', '25MA乖離', 'ATR%', '売買代金']],
                    use_container_width=True, hide_index=True, 
                    on_select="rerun", selection_mode="multi-row", 
                    key=f"df_sc_view_final_{i}",
                    height=df_height,
                    column_config={
                        "前日比": st.column_config.NumberColumn("前日比", format="%+.2f%%"),
                        "25MA乖離": st.column_config.NumberColumn("25MA乖離", format="%+.2f%%"),
                        "ATR%": st.column_config.NumberColumn("ATR%", format="%.2f%%"),
                        "売買代金": st.column_config.NumberColumn("売買代金(億)", format="%.1f")
                    }
                )
                
                # 自動入力ロジック
                if sel_event.selection.rows:
                    selected_codes = current_res.iloc[sel_event.selection.rows]['コード'].tolist()
                    current_str = st.session_state.get('target_tickers', "")
                    current_list = [t.strip() for t in current_str.split(",") if t.strip()]
                    new_only = [c for c in selected_codes if c not in current_list]
                    if new_only:
                        new_combined = sorted(list(set(current_list + new_only)))
                        st.session_state['target_tickers'] = ", ".join(new_combined)
                        st.session_state[f"sc_no_results_{i}"] = False # 監視リスト追加時は警告を消す
                        st.toast(f"監視リストに {len(new_only)} 銘柄を反映しました")
                        st.rerun()
                        
# --- タブ3: バックテスト (Ver 4.6.0：始値自動取得統合版) ---
with tab_bt:
    if st.button("バックテスト実行", type="primary", use_container_width=True, key="bt_run_main"):
        t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]
        if not t_list:
            st.error("銘柄コードを入力してください。")
        else:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            all_trades = []; t_names = {}
            pb = st.progress(0); st_text = st.empty()
            
            for i, t in enumerate(t_list):
                st_text.text(f"分析中 {t}..."); pb.progress((i+1)/len(t_list))
                
                # --- ⚡️ 重要：本日の始値を自動取得してセッションに保存 ---
                # 指値戦略タブの入力欄（act_in_銘柄コード）とキーを同期させます
                st.session_state[f"act_in_{t}"] = core.get_realtime_opening_price(t)
                
                # データのダウンロードとMultiIndex対策
                df = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
                if df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                # シミュレーション実行
                p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
                trades = core.run_ticker_simulation(t, df, p_map, o_map, a_map, params)
                all_trades.extend(trades)
                t_names[t] = TICKER_DETAILS.get(t, [t])[0]
                
            st.session_state['res_df'] = pd.DataFrame(all_trades)
            st.session_state['t_names'] = t_names
            st_text.empty(); pb.empty()
            st.rerun()

    # 分析結果サブタブの展開
    res_df = st.session_state['res_df']
    ticker_names = st.session_state['t_names']
    
    if not res_df.empty:
        bt_tabs = st.tabs(["📊 サマリー", "🏅 勝ちパターン", "📉 ギャップ分析", "🧐 VWAP分析", "🕒 時間分析", "📝 詳細ログ"])
        
        with bt_tabs[0]: # 📊 サマリー (6.3 完全移植 + 3.0 整合版)
            # --- 1. 計測期間の取得 (フォールバック付) ---
            display_period = st.session_state.get('bt_period')
            if not display_period or display_period == "不明":
                display_period = f"{(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')} - {datetime.now().strftime('%Y-%m-%d')}"
            
            # --- 2. 全体集計 ---
            count_all = len(res_df)
            wins_all = res_df[res_df['PnL'] > 0]
            losses_all = res_df[res_df['PnL'] <= 0]
            win_rate_all = len(wins_all) / count_all if count_all > 0 else 0
            pf_all = wins_all['PnL'].sum() / abs(losses_all['PnL'].sum()) if not losses_all.empty else 0
            expectancy_all = res_df['PnL'].mean()

            # --- 3. メトリクス表示 (3.0のデザインを継承) ---
            st.markdown(f"""
                <div class='metric-grid'>
                    <div class='summary-box'><div class='card-label'>総トレード数</div><div class='card-value'>{count_all}</div></div>
                    <div class='summary-box'><div class='card-label'>勝率</div><div class='card-value'>{win_rate_all:.1%}</div></div>
                    <div class='summary-box'><div class='card-label'>PF（利益÷損失）</div><div class='card-value'>{pf_all:.2f}</div></div>
                    <div class='summary-box'><div class='card-label'>期待値</div><div class='card-value'>{expectancy_all:.2%}</div></div>
                </div>""", unsafe_allow_html=True)
            st.divider()
        
            # --- 4. テキストレポート生成 (6.3の詳細度を復元) ---
            report = ["=================\n BACKTEST REPORT \n=================", f"Period: {display_period}\n"]
            
            for t in res_df['Ticker'].unique():
                tdf = res_df[res_df['Ticker'] == t]
                if tdf.empty: continue
                
                t_wins = tdf[tdf['PnL'] > 0]
                t_losses = tdf[tdf['PnL'] <= 0]
                t_wr = len(t_wins) / len(tdf)
                t_pf = t_wins['PnL'].sum() / abs(t_losses['PnL'].sum()) if not t_losses.empty else 9.9
                
                report.append(f">>> TICKER: {t} | {ticker_names.get(t, t)}")
                report.append(f"トレード数: {len(tdf)} | 勝率: {t_wr:.1%} | 利益平均: {t_wins['PnL'].mean():+.2%} | 損失平均: {t_losses['PnL'].mean():+.2%} | PF: {t_pf:.2f} | 期待値: {tdf['PnL'].mean():+.2%}\n")
            
            st.caption("右上のコピーボタンで全文コピーできます↓")
            st.code("\n".join(report), language="text")

            if st.button("♻️ バックテスト結果をクリア", key="reset_summary_final"):
                st.session_state['res_df'] = pd.DataFrame()
                st.rerun()
                
        with bt_tabs[1]: # 🏅 勝ちパターン (3回以上優先 ＆ 1回以上代用版)
            st.markdown("### 🏅 勝ちパターン分析")
            st.caption("チャートパターン別の成績分析と、ベストなエントリー条件を言語化して勝ちパターンを抽出します。")
            if not res_df.empty and 'Ticker' in res_df.columns:
                unique_res_tickers = res_df['Ticker'].unique()

                for t in unique_res_tickers:
                    tdf = res_df[res_df['Ticker'] == t].copy()
                    if tdf.empty: continue
                    t_name = ticker_names.get(t, t)
                    st.markdown(f"### [{t}] {t_name}")

                    # --- 勝ちパターン分析 (文字列変換 ＆ 左揃え) ---
                    pat_stats = tdf.groupby('Pattern', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                    pat_stats.columns = ['パターン', '回数', '勝率', '平均損益']

                    # 表示用に全ての列を文字列に変換する
                    pat_stats_disp = pat_stats.copy()
                    pat_stats_disp['回数'] = pat_stats_disp['回数'].astype(str)
                    pat_stats_disp['勝率'] = pat_stats_disp['勝率'].apply(lambda x: f"{x:.1%}")
                    pat_stats_disp['平均損益'] = pat_stats_disp['平均損益'].apply(lambda x: f"{x:+.2%}")

                    st.dataframe(
                        pat_stats_disp.style.set_properties(**{'text-align': 'left'}), # 文字列なので確実に左に寄る
                        hide_index=True, 
                        use_container_width=True
                    )

                    # 2. ベスト条件抽出用ヘルパー関数 (代用ロジック)
                    def get_best_row(df, count_col, rate_col, threshold=3):
                        # まずは3回以上で探す
                        valid = df[df[count_col] >= threshold]
                        if valid.empty:
                            # なければ1回以上で探す (一番良い数字を代用)
                            valid = df[df[count_col] >= 1]
                        return valid.loc[valid[rate_col].idxmax()] if not valid.empty else None

                    try:
                        # A. ギャップ分析 (0.5%刻み)
                        g_min, g_max = tdf['Gap(%)'].min(), tdf['Gap(%)'].max()
                        if pd.isna(g_min): g_min, g_max = -3.0, 1.0
                        bins_g = np.arange(np.floor(g_min), np.ceil(g_max) + 0.5, 0.5)
                        if len(bins_g) < 2: bins_g = [g_min - 0.5, g_min + 0.5] # 境界不足対策
                        tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=bins_g)
                        g_s = tdf.groupby('GapRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()
                        
                        # B. VWAP分析 (0.2%刻み)
                        tdf['VWAP_Diff'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                        v_min, v_max = tdf['VWAP_Diff'].min(), tdf['VWAP_Diff'].max()
                        if pd.isna(v_min): v_min, v_max = -1.0, 1.0
                        bins_v = np.arange(np.floor(v_min*5)/5, np.ceil(v_max*5)/5 + 0.2, 0.2)
                        if len(bins_v) < 2: bins_v = [v_min - 0.2, v_min + 0.2]
                        tdf['VwapRange'] = pd.cut(tdf['VWAP_Diff'], bins=bins_v)
                        v_s = tdf.groupby('VwapRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()

                        # C. 時間分析 (5分刻み)
                        tdf['TR'] = tdf['Entry'].apply(lambda dt: f"{dt.strftime('%H:%M')}～{(dt + timedelta(minutes=5)).strftime('%H:%M')}")
                        t_s = tdf.groupby('TR', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean()]).reset_index()

                        # ベスト行の取得 (3回以上を優先し、なければ最大値を採用)
                        best_p = get_best_row(pat_stats, '回数', '勝率')
                        best_g = get_best_row(g_s, 'count', '<lambda_0>')
                        best_v = get_best_row(v_s, 'count', '<lambda_0>')
                        best_t = get_best_row(t_s, 'count', '<lambda_0>')

                        if all([best_p is not None, best_g is not None, best_v is not None, best_t is not None]):
                            g_txt = "ギャップアップ" if best_g['GapRange'].left >= 0 else "ギャップダウン"
                            reliability = "⭐⭐" if best_p['回数'] >= 3 else "⭐" # 信頼度アイコン
                            
                            st.info(f"**🏆 最高勝率パターン {reliability}**\n\n"
                                    f"最も勝率が高かったのは、"
                                    f"**{g_txt} ({best_g['GapRange'].left:.1f}% ～ {best_g['GapRange'].right:.1f}%)** スタートで、"
                                    f"**{best_p['パターン']}** の形になり、"
                                    f"**VWAPから {best_v['VwapRange'].left:.1f}% ～ {best_v['VwapRange'].right:.1f}%** の位置にある時、"
                                    f"**{best_t['TR']}** にエントリーするパターンです。\n\n"
                                    f"（GAP勝率: {best_g['<lambda_0>']:.1%} / VWAP勝率: {best_v['<lambda_0>']:.1%} / 時間勝率: {best_t['<lambda_0>']:.1%})")
                        else:
                            st.warning("⚠️ パターンを特定するためのトレードデータが足りません。")
                            
                    except Exception as e:
                        st.error(f"[{t}] 分析エラー: データの範囲が狭すぎるか、不足しています。")
                    st.divider()

        with bt_tabs[2]: # 📉 ギャップ分析 (BACK TESTER 6.3 完全移植版)
            if not res_df.empty and 'Ticker' in res_df.columns:
                for t in res_df['Ticker'].unique():
                    tdf = res_df[res_df['Ticker'] == t].copy()
                    t_name = ticker_names.get(t, t)
                    st.markdown(f"### [{t}] {t_name}")
                    
                    # --- 1. 始値ギャップ方向の分析 ---
                    st.markdown("##### 始値ギャップ方向と成績")
                    tdf['GapDir'] = tdf['Gap(%)'].apply(lambda x: 'ギャップアップ' if x > 0 else ('ギャップダウン' if x < 0 else 'フラット'))
                    gap_dir_stats = tdf.groupby('GapDir', observed=True).agg(
                        Count=('PnL', 'count'), WinRate=('PnL', lambda x: (x > 0).mean()), AvgPnL=('PnL', 'mean')
                    ).reset_index()
                    
                    gap_dir_disp = gap_dir_stats.copy()
                    gap_dir_disp['WinRate'] = gap_dir_disp['WinRate'].apply(lambda x: f"{x:.1%}")
                    gap_dir_disp['AvgPnL'] = gap_dir_disp['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                    gap_dir_disp.columns = ['方向', '回数', '勝率', '平均損益']
                    
                    # --- 【修正点】文字列変換 ＆ 左揃えを適用 ---
                    gap_dir_disp['回数'] = gap_dir_disp['回数'].astype(str)
                    st.dataframe(
                        gap_dir_disp.style.set_properties(**{'text-align': 'left'}), 
                        hide_index=True, use_container_width=True
                    )

                    # --- 2. ギャップ幅ごとの分析 (0.5%刻み) ---
                    st.markdown("##### ギャップ幅ごとの勝率")
                    try:
                        min_g = np.floor(tdf['Gap(%)'].min()); max_g = np.ceil(tdf['Gap(%)'].max())
                        bins_g = np.arange(min_g if not np.isnan(min_g) else -3.0, (max_g if not np.isnan(max_g) else 1.0) + 0.5, 0.5)
                        tdf['GapRange'] = pd.cut(tdf['Gap(%)'], bins=bins_g)
                        gap_range_stats = tdf.groupby('GapRange', observed=True).agg(
                            Count=('PnL', 'count'), WinRate=('PnL', lambda x: (x > 0).mean()), AvgPnL=('PnL', 'mean')
                        ).reset_index()
                        gap_range_stats['RangeLabel'] = gap_range_stats['GapRange'].apply(lambda i: f"{i.left:.1f}% ～ {i.right:.1f}%")
                        disp_gap = gap_range_stats[['RangeLabel', 'Count', 'WinRate', 'AvgPnL']].copy()
                        disp_gap['WinRate'] = disp_gap['WinRate'].apply(lambda x: f"{x:.1%}")
                        disp_gap['AvgPnL'] = disp_gap['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                        disp_gap.columns = ['ギャップ幅', '回数', '勝率', '平均損益']
                        
                        # --- 【修正点】文字列変換 ＆ 左揃えを適用 ---
                        disp_gap['回数'] = disp_gap['回数'].astype(str)
                        st.dataframe(
                            disp_gap.style.set_properties(**{'text-align': 'left'}), 
                            hide_index=True, use_container_width=True
                        )
                    except: st.warning(f"[{t}] ギャップ幅分析用のデータが不足しています。")
                    st.divider()

        with bt_tabs[3]: # 🧐 VWAP分析 (BACK TESTER 6.3 完全移植 & 3.0 変数同期版)
            # --- データの存在チェック ---
            if not res_df.empty and 'Ticker' in res_df.columns:
                # 実際に結果が存在する銘柄コードのみを抽出してループ
                unique_res_tickers = res_df['Ticker'].unique()
                
                for t in unique_res_tickers:
                    tdf = res_df[res_df['Ticker'] == t].copy()
                    if tdf.empty: continue
                    
                    t_name = ticker_names.get(t, t)
                    st.markdown(f"### [{t}] {t_name}")
                    st.markdown("##### エントリー時のVWAPと勝率")
                    
                    # --- VWAP乖離の計算 ---
                    # EntryVWAP（エントリー時点のVWAP値）から乖離率を算出
                    tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                    
                    try:
                        # レンジ（bin）の作成 (0.2%刻みに調整)
                        # 最小・最大値を0.2単位で丸めて範囲を決定
                        min_dev = np.floor(tdf['VWAP乖離(%)'].min() * 5) / 5
                        max_dev = np.ceil(tdf['VWAP乖離(%)'].max() * 5) / 5
                        if np.isnan(min_dev): min_dev = -1.0; max_dev = 1.0
                        
                        # 0.2刻みの配列を生成
                        bins = np.arange(min_dev, max_dev + 0.2, 0.2)
                        tdf['Range'] = pd.cut(tdf['VWAP乖離(%)'], bins=bins)
                        
                        # 統計集計（Named Aggregation形式）
                        vwap_stats = tdf.groupby('Range', observed=True).agg(
                            Count=('PnL', 'count'), 
                            WinRate=('PnL', lambda x: (x > 0).mean()), 
                            AvgPnL=('PnL', 'mean')
                        ).reset_index()
                        
                        # ラベルの整形 (0.2%刻みを正確に表示)
                        def format_vwap_interval(i): 
                            return f"{i.left:.1f}% ～ {i.right:.1f}%"
                        vwap_stats['RangeLabel'] = vwap_stats['Range'].apply(format_vwap_interval)
                        
                        # 表示用データフレームの構築
                        display_stats = vwap_stats[['RangeLabel', 'Count', 'WinRate', 'AvgPnL']].copy()
                        display_stats['WinRate'] = display_stats['WinRate'].apply(lambda x: f"{x:.1%}")
                        display_stats['AvgPnL'] = display_stats['AvgPnL'].apply(lambda x: f"{x:+.2%}")
                        display_stats['Count'] = display_stats['Count'].astype(str)
                        display_stats.columns = ['乖離率レンジ', '回数', '勝率', '平均損益']
                        
                        # 表の表示
                        st.dataframe(display_stats.style.set_properties(**{'text-align': 'left'}), hide_index=True, use_container_width=True)
                    
                    except Exception:
                        st.warning(f"[{t}] VWAP乖離分析を生成するためのデータが不足しています。")
                    
                    st.divider()

        with bt_tabs[4]: # 🕒 時間分析 (BACK TESTER 6.3 完全移植版)
            # --- データの存在チェック ---
            if not res_df.empty and 'Ticker' in res_df.columns:
                # 実際に結果が存在する銘柄コードのみを抽出してループ
                unique_res_tickers = res_df['Ticker'].unique()

                for t in unique_res_tickers:
                    tdf = res_df[res_df['Ticker'] == t].copy()
                    if tdf.empty: continue
                    
                    t_name = ticker_names.get(t, t)
                    st.markdown(f"### [{t}] {t_name}")
                    st.markdown("##### エントリー時間帯ごとの勝率")
                    
                    # --- エントリー時間帯の5分刻み文字列作成 ---
                    def get_time_range(dt): 
                        return f"{dt.strftime('%H:%M')}～{(dt + timedelta(minutes=5)).strftime('%H:%M')}"
                    
                    tdf['TimeRange'] = tdf['Entry'].apply(get_time_range)
                    
                    # --- 時間帯ごとの集計 ---
                    try:
                        time_stats = tdf.groupby('TimeRange', observed=True)['PnL'].agg(['count', lambda x: (x>0).mean(), 'mean']).reset_index()
                        
                        # 表示用に整形
                        time_disp = time_stats.copy()
                        time_disp.columns = ['時間帯', 'count', 'win_rate', 'mean']
                        time_disp['WinRate'] = time_disp['win_rate'].apply(lambda x: f"{x:.1%}")
                        time_disp['AvgPnL'] = time_disp['mean'].apply(lambda x: f"{x:+.2%}")
                        time_disp['Count'] = time_disp['count'].astype(str)
                        
                        # 最終的な表示用カラム
                        final_disp = time_disp[['時間帯', 'Count', 'WinRate', 'AvgPnL']]
                        final_disp.columns = ['時間帯', '回数', '勝率', '平均損益']
                        
                        st.dataframe(final_disp, hide_index=True, use_container_width=True)
                    except Exception:
                        st.warning(f"[{t}] 時間分析を生成するためのデータが不足しています。")
                    
                    st.divider()

        with bt_tabs[5]: # 📝 詳細ログ (BACK TESTER 6.3 完全移植版)
            st.markdown("### 📝 詳細取引ログ")
            
            # --- データの存在チェック ---
            if not res_df.empty and 'Ticker' in res_df.columns:
                # リストの初期化
                log_report = []
                
                # 実際に結果が存在する銘柄コードのみを抽出してループ
                unique_res_tickers = res_df['Ticker'].unique()

                for t in unique_res_tickers:
                    # データの抽出とソート (新しい順)
                    tdf = res_df[res_df['Ticker'] == t].copy().sort_values('Entry', ascending=False).reset_index(drop=True)
                    if tdf.empty: continue
                    
                    # VWAP乖離の再計算
                    tdf['VWAP乖離(%)'] = ((tdf['In'] - tdf['EntryVWAP']) / tdf['EntryVWAP']) * 100
                    t_name = ticker_names.get(t, t)
                    
                    log_report.append(f"[{t}] {t_name} 取引履歴")
                    log_report.append("-" * 80)
                    
                    for i, row in tdf.iterrows():
                        entry_str = row['Entry'].strftime('%Y-%m-%d %H:%M')
                        
                        # VWAP表示の整形
                        if pd.notna(row['EntryVWAP']) and row['EntryVWAP'] != 0:
                            vwap_val = int(round(row['EntryVWAP']))
                            vwap_dev = f"{row['VWAP乖離(%)']:+.2f}%"
                            vwap_str = f"{vwap_val} (乖離 {vwap_dev})"
                        else:
                            vwap_str = "- (乖離 -)"
                        
                        # 6.3形式の1行詳細ログ作成 (金額は int で整形)
                        line = (
                            f"{entry_str} | "
                            f"前終値：{int(row['PrevClose'])} | 始値：{int(row['DayOpen'])} | "
                            f"{row['Pattern']} | "
                            f"PnL: {row['PnL']:+.2%} | Gap: {row['Gap(%)']:+.2f}% | "
                            f"買：{int(row['In'])} | 売：{int(row['Out'])} | "
                            f"VWAP: {vwap_str} | "
                            f"{row['Reason']}"
                        )
                        log_report.append(line)
                    log_report.append("\n")
                
                st.caption("右上のコピーボタンで全文コピーできます↓")
                st.code("\n".join(log_report), language="text")

                st.divider()

# --- タブ4: 指値戦略 (Ver 4.5.5：特殊スペース除去 & スタイル分離) ---
with tab_strategy:
    st.markdown("### ✨ 指値戦略プランナー")
    st.caption("統計的勝率・市場地合い・リアルタイムの勢いを統合した最終判断用パネルです。前場・後場の寄付き前と、始値確定後15分以内の利用を推奨します。")
    
    res_df = st.session_state.get('res_df', pd.DataFrame())
    ticker_names = st.session_state.get('t_names', {})
    t_list = [t.strip() for t in st.session_state['target_tickers'].split(",") if t.strip()]

    if not t_list:
        st.warning("⚠️ 監視リストに銘柄がありません。")
    elif res_df.empty:
        st.info("💡 まずは「バックテスト」を実行してください。過去の統計データが必要です。")
    else:
        diag = core.analyze_market_environment()
        m_curr_pct = diag.get('market_pct', 0.0)
        m_gap = diag.get('gap_pct', 0.0)

        m_cls = "rakuten-plus" if m_curr_pct >= 0 else "rakuten-minus"
        st.markdown(f"<div class='strat-market-header'><b>日経平均／前日比:</b> <span class='{m_cls}' style='font-size:1.2em; font-weight:bold;'>{m_curr_pct:+.2%}</span></div>", unsafe_allow_html=True)
        st.divider()

        for t in t_list:
            tdf = res_df[res_df['Ticker'] == t].copy()
            if tdf.empty: continue
            t_name = ticker_names.get(t, t)
            
            with st.expander(f"[{t}] {t_name}", expanded=True):
                with st.spinner("分析中..."):
                    ticker_live = yf.Ticker(t)
                    hist_live = ticker_live.history(period="30d")
                    if len(hist_live) >= 15:
                        last_c = hist_live['Close'].iloc[-1]
                        hl = hist_live['High'] - hist_live['Low']; hc = np.abs(hist_live['High'] - hist_live['Close'].shift()); lc = np.abs(hist_live['Low'] - hist_live['Close'].shift())
                        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
                        atr_p = (tr.rolling(14).mean().iloc[-1] / last_c) * 100
                    else: 
                        last_c = tdf['PrevClose'].iloc[-1]; atr_p = 1.5

                v_factor = max(0.6, min(2.5, atr_p / 1.5))
                tdf['Entry_Push'] = ((tdf['In'] - tdf['DayOpen']) / tdf['DayOpen']) * 100
                win_tdf = tdf[tdf['PnL'] > 0]
                avg_push = win_tdf['Entry_Push'].mean() if not win_tdf.empty else 0
                pred_o = last_c * (1 + m_gap)

                # --- 上段レイアウト (strat-card-top を使用) ---
                c_top_l, c_top_r = st.columns([2, 1])
                with c_top_l:
                    g_cls = "rakuten-plus" if m_gap >= 0 else "rakuten-minus"
                    st.markdown(f"""
                    <div class="mobile-flex-container">
                        <div class="flex-item strat-card-top">
                            <div class="card-label">最新終値</div>
                            <div class="strat-value">{last_c:,.0f}</div>
                            <div class="strat-guide">理想押し目 <span class="strat-percent">{avg_push:+.2f}%</span></div>
                        </div>
                        <div class="flex-item strat-card-top">
                            <div class="card-label">予想寄り付き</div>
                            <div class="strat-value">{pred_o:,.0f}</div>
                            <div class="strat-delta {g_cls}">{m_gap:+.2%}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with c_top_r:
                    input_key = f"act_in_{t}"
                    
                    # セッション状態（バックテスト時に取得した値）をデフォルト値に設定
                    actual_open_val = st.number_input(
                        f"始値を入力 ({t})", 
                        value=st.session_state.get(input_key), # 値がNoneなら空欄、あれば数値が入る
                        step=1.0,  # ← ここを float 型に統一 
                        key=input_key, 
                        label_visibility="collapsed", 
                        placeholder="始値を入力"
                    )
                    
                    # 最終的な確定ボタン
                    btn_calc = st.button(f"戦略を確定する ({t})", use_container_width=True, type="primary")

                # 2. エラー修正：actual_open_val が None（空）でないことを確認する条件に変更します
                if actual_open_val or btn_calc:
                    if not actual_open_val:
                        st.error("始値を入力してください。") # 未入力でボタンを押した時の警告
                    else:
                        with st.spinner("診断中..."):
                            df_m = ticker_live.history(interval="1m", period="1d")
                            rsi_slope = 0; ema_gap = 0; tech_warning = False
                            if len(df_m) >= 15:
                                rsi_series = core.calculate_rsi(df_m['Close'])
                                if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]):
                                    rsi_slope = rsi_series.iloc[-1] - rsi_series.iloc[-2]
                                ema5 = df_m['Close'].ewm(span=5, adjust=False).mean().iloc[-1]
                                ema_gap = ((actual_open_val - ema5) / ema5) * 100
                                if rsi_slope < 0 or abs(ema_gap) > 1.5: tech_warning = True

                        today_limit = actual_open_val * (1 + (avg_push / 100))
                        avg_profit = win_tdf['PnL'].mean() if not win_tdf.empty else 0
                        target_price = today_limit * (1 + avg_profit)
                        adj_sl = params['sl_fix'] * v_factor
                        stop_price = today_limit * (1 + adj_sl)

                    # --- 下段レイアウト (strat-card-bottom を使用：ボーダーなし) ---
                    st.markdown(f"""
                    <div class="mobile-flex-container" style="margin-top: 15px;">
                        <div class="flex-item strat-card-bottom">
                            <div class="card-label">今日の指値</div>
                            <div class="strat-value">{int(today_limit):,}</div>
                            <div class="strat-guide">で逆指値注文</div>
                        </div>
                        <div class="flex-item strat-card-bottom">
                            <div class="card-label">目標利確</div>
                            <div class="strat-value">{int(target_price):,}</div>
                            <div class="strat-delta rakuten-plus">{avg_profit:+.2%}</div>
                        </div>
                        <div class="flex-item strat-card-bottom">
                            <div class="card-label">損切ライン</div>
                            <div class="strat-value">{int(stop_price):,}</div>
                            <div class="strat-delta rakuten-minus">{adj_sl:+.2%}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 3. テクニカル診断 (RSIスロープのマイルド化 & アイコン削除)
                    with st.spinner("診断中..."):
                        df_m = ticker_live.history(interval="1m", period="1d")
                        rsi_slope = 0; ema_gap = 0; tech_warning = False
                        
                        if len(df_m) >= 15:
                            rsi_series = core.calculate_rsi(df_m['Close'])
                            
                            # --- マイルド判定ロジック：直近3分(平均) vs その前3分(平均) ---
                            if len(rsi_series) >= 6:
                                curr_rsi_avg = rsi_series.tail(3).mean()      # 最新3本の平均
                                prev_rsi_avg = rsi_series.iloc[-6:-3].mean() # その前3本の平均
                                rsi_slope = curr_rsi_avg - prev_rsi_avg
                            elif len(rsi_series) >= 2:
                                rsi_slope = rsi_series.iloc[-1] - rsi_series.iloc[-2]

                            # EMA5乖離の計算
                            ema5 = df_m['Close'].ewm(span=5, adjust=False).mean().iloc[-1]
                            ema_gap = ((actual_open_val - ema5) / ema5) * 100
                            
                            # 判定しきい値：わずかなノイズを無視するため -0.2 以下を「低下」と定義
                            if rsi_slope < -0.2 or abs(ema_gap) > 1.5: 
                                tech_warning = True

                    # --- テクニカル表示 (アイコンなし・マイルド判定反映) ---
                    r_cls = "rakuten-plus" if rsi_slope > -0.2 else "rakuten-minus"
                    r_text = "上昇・維持" if rsi_slope > -0.2 else "低下中"
                    
                    st.markdown(f"""
                    <div class="strat-tech-flex">
                        <div class="strat-tech-item"><b>RSI方向:</b> <span class='{r_cls}'>{r_text}</span></div>
                        <div class="strat-tech-item"><b>EMA5乖離:</b> {ema_gap:+.2f}%</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # --- 6. 最終判定 (乖離ガードロジック搭載版) ---
                    today_gap = (actual_open_val - last_c) / last_c
                    similar_trades = tdf[(tdf['Gap(%)'] >= (today_gap*100 - 0.5)) & (tdf['Gap(%)'] <= (today_gap*100 + 0.5))]
                    n_count = len(similar_trades)
                    sim_win_rate = len(similar_trades[similar_trades['PnL'] > 0]) / n_count if n_count > 0 else 0

                    # 新規追加：乖離チェックの実行
                    is_dev_large, dev_val = core.check_opening_deviation(actual_open_val, pred_o, last_c)

                    if is_dev_large:
                        # 🚫 乖離ガード発動 (最優先)
                        st.markdown(f"""<div class="strat-msg-box msg-bg-error">
                            ⚠️ <b>見送り</b><br>
                            予想乖離からのズレ: {dev_val:.2f}%<br>
                            寄付き乖離が大きいため見送り推奨です。
                        </div>""", unsafe_allow_html=True)
                    elif m_curr_pct < -0.003 and sim_win_rate >= 0.55:
                        # ⚠️ CAUTION
                        st.markdown(f"""<div class="strat-msg-box msg-bg-warning">
                            ⚠️ <b>CAUTION</b> (勝率 {sim_win_rate:.1%} / {n_count}回)<br>
                            地合い軟調。慎重に判断してください。
                        </div>""", unsafe_allow_html=True)
                    elif sim_win_rate >= 0.55:
                        # 🔥 エントリー可能
                        msg = "統計は良いが勢いが弱まっています。" if tech_warning else "統計・勢い共に良好。"
                        st.markdown(f"""<div class="strat-msg-box msg-bg-success">
                            🔥 <b>エントリー可能</b> (勝率 {sim_win_rate:.1%} / {n_count}回)<br>
                            {msg}
                        </div>""", unsafe_allow_html=True)
                    else:
                        # ❄️ エントリーなし
                        st.markdown(f"""<div class="strat-msg-box msg-bg-error">
                            ❄️ <b>エントリーなし</b> (勝率 {sim_win_rate:.1%} / {n_count}回)<br>
                            期待値が不十分です。
                        </div>""", unsafe_allow_html=True)

                    # --- 7. トレイリング案 ( st.markdown に置き換え ) ---
                    st.markdown(f"""<div class="strat-msg-box msg-bg-info">
                        🚀 <b>トレイリング最適化</b><br>
                        開始{params['ts_start']*v_factor:.2%} / 幅：{params['ts_width']*v_factor:.2%} / 損切り：{adj_sl:+.2%}
                    </div>""", unsafe_allow_html=True)

                    st.caption(f"ボラ係数: {v_factor:.2f}x (ATR {atr_p:.2f}%) | RR比: 1 : {abs(avg_profit/adj_sl):.2f}")
                    
                else:
                    st.caption("始値を入力して「戦略を確定する」をタップ")
            st.divider()
                    
# --- タブ5: ランキング (3.3 安定版：10項目 ＆ ％表記) ---
with tab_rank:
    st.markdown("### 🏆 登録銘柄ランキング")
    st.caption("日経225＋αの銘柄から、エントリー条件をクリアした期待値の高い20銘柄をランキングで抽出します。")
    p_range = st.slider("価格帯フィルター (円)", 0, 20000, (500, 5000), 500, key="rank_sld_p")
    
    if st.button("ランキング生成開始", type="primary", use_container_width=True, key="rank_run_btn"):
        rank_list = []
        all_tickers = list(TICKER_DETAILS.keys())
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        with st.status("🔍 全銘柄を分析中...", expanded=True) as status:
            pb_r = st.progress(0)
            for i, t in enumerate(all_tickers):
                pb_r.progress((i+1)/len(all_tickers))
                status.update(label=f"Scanning {i+1}/{len(all_tickers)}: {t}")


                # 1. 前日比取得のための日足取得
                df_d = yf.download(t, period="2d", interval="1d", progress=False)
                
                # 【修正箇所】データが空、または2件（当日・前日）揃っていない場合はスキップ
                if df_d.empty or len(df_d) < 2: 
                    continue
                
                if isinstance(df_d.columns, pd.MultiIndex): 
                    df_d.columns = df_d.columns.get_level_values(0)
                
                # 前日比の計算（2件あることが確定したので安全にアクセス可能）
                # 計算式: $Day\_Gain = \frac{Close_{today} - Close_{yesterday}}{Close_{yesterday}} \times 100$
                day_gain = ((df_d['Close'].iloc[-1] - df_d['Close'].iloc[-2]) / df_d['Close'].iloc[-2]) * 100
                current_p = float(df_d['Close'].iloc[-1])
                
                # 価格帯フィルター
                if p_range[0] <= current_p <= p_range[1]:
                    # 2. シミュレーション用の5分足取得
                    df_r = yf.download(t, start=start_date, interval="5m", progress=False, auto_adjust=False)
                    if df_r.empty: continue
                    if isinstance(df_r.columns, pd.MultiIndex): df_r.columns = df_r.columns.get_level_values(0)
                    
                    p_map, o_map, a_map = core.fetch_daily_stats_maps(t, start_date)
                    t_trades = core.run_ticker_simulation(t, df_r, p_map, o_map, a_map, params)
                    
                    if t_trades:
                        score_data = core.get_one_touch_score(t_trades)
                        if score_data:
                            # 【修正】10項目のデータ収集
                            rank_list.append({
                                'コード': t, 
                                '銘柄名': TICKER_DETAILS.get(t, [t])[0],
                                '前日比': day_gain,
                                '回数': score_data['count'],
                                '勝率': score_data['win_rate'], 
                                '利益平均': score_data['avg_win'],
                                '損失平均': score_data['avg_loss'],
                                'PF': score_data['pf'], 
                                '期待値': score_data['ev'],
                                '総合スコア': score_data['score']
                            })
            status.update(label="✅ スキャン完了！", state="complete")
        
        if rank_list:
            # 期待値順にソートして保存
            st.session_state['last_rank_df'] = pd.DataFrame(rank_list).sort_values('期待値', ascending=False).head(20)
            st.rerun()
        else:
            st.warning("⚠️ 指定した価格帯で期待値が算出された銘柄はありませんでした。")

    # --- 結果の表示と転送機能 ---
    if 'last_rank_df' in st.session_state:
        rdf = st.session_state['last_rank_df']
        st.caption("👇 チェックを入れると銘柄リストに追加できます。")
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 【修正】10項目の表示設定と％表記
        # ご自身で設定された高さ height=735 を維持しています。
        event = st.dataframe(
            rdf[['コード', '銘柄名', '前日比', '回数', '勝率', '利益平均', '損失平均', 'PF', '期待値', '総合スコア']].style.format({
                '前日比': '{:+.2f}%', '勝率': '{:.1%}', '期待値': '{:+.2%}', 
                '利益平均': '{:+.2%}', '損失平均': '{:+.2%}', 'PF': '{:.2f}', 
                '総合スコア': '{:.2%}' # ％表記に変更
            }),
            use_container_width=True, hide_index=True, 
            on_select="rerun", selection_mode="multi-row", 
            key="rank_df_view_final",
            height=735 
        )
        
        # 監視リストへの反映ロジック (既存維持)
        selected_rows = event.selection.rows
        if selected_rows:
            selected_codes = rdf.iloc[selected_rows]['コード'].tolist()
            current_str = st.session_state.get('target_tickers', "")
            current_list = [t.strip() for t in current_str.split(",") if t.strip()]
            new_found = [c for c in selected_codes if c not in current_list]
            if new_found:
                updated_list = sorted(list(set(current_list + selected_codes)))
                st.session_state['target_tickers'] = ", ".join(updated_list)
                st.toast(f"期待値トップ銘柄を監視リストに追加しました！")
                st.rerun() 

        if st.button("♻️ ランキングをクリア", key="rank_clear_btn"):
            del st.session_state['last_rank_df']
            st.rerun()
