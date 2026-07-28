"""
ماسح الحيتان v5.0 — منصة التنبؤ بالانفجارات
=============================================
منصة حقيقية تتنبأ بالأسهم اللي ممكن تنفجر في الجلسة القادمة.
"""
import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf
import sqlite3
import os

st.set_page_config(
    page_title="ماسح الحيتان — تنبؤ بالانفجارات",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root{--bg:#0a0e17;--bg2:#111827;--card:#1a1f2e;--card2:#232a3b;--border:#2a3042;--accent:#3b82f6;
--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--purple:#8b5cf6;--cyan:#06b6d4;--orange:#f97316;
--text:#f1f5f9;--text2:#94a3b8;--text3:#64748b;}
[data-testid="stAppViewContainer"]{background:var(--bg)!important;}
[data-testid="stSidebar"]{background:var(--bg2)!important;}
.main .block-container{padding-top:0.5rem;max-width:100%;}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:8px;transition:all .2s;}
.card:hover{border-color:var(--accent);transform:translateY(-1px);}
.label{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.value{font-size:24px;font-weight:700;color:var(--text);}
.change{font-size:13px;font-weight:500;}
.up{color:var(--green);}.down{color:var(--red);}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--green);animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}
.prob-bar{height:8px;border-radius:4px;background:var(--border);overflow:hidden;margin-top:4px;}
.prob-fill{height:100%;border-radius:4px;transition:width .3s;}
.badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;}
.badge-green{background:rgba(16,185,129,.15);color:var(--green);border:1px solid rgba(16,185,129,.3);}
.badge-blue{background:rgba(59,130,246,.15);color:var(--accent);border:1px solid rgba(59,130,246,.3);}
.badge-yellow{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3);}
.badge-red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);}
.badge-purple{background:rgba(139,92,246,.15);color:var(--purple);border:1px solid rgba(139,92,246,.3);}
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border);margin-bottom:16px;}
.logo{font-size:28px;font-weight:800;color:var(--text);}
.session-live{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:20px;font-size:13px;font-weight:600;background:rgba(16,185,129,.15);color:var(--green);border:1px solid rgba(16,185,129,.3);}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=30)
def load_predictions():
    import urllib.request
    for path in [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'predictions.json'),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scan_results.json'),
                 'predictions.json', 'scan_results.json']:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data and (data.get('predictions') or data.get('signals')):
                    return data
        except:
            pass
    try:
        url = "https://raw.githubusercontent.com/abdsebvip-byte/whale-scanner/main/predictions.json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except:
        pass
    try:
        url = "https://raw.githubusercontent.com/abdsebvip-byte/whale-scanner/main/scan_results.json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except:
        return None


@st.cache_data(ttl=300)
def get_chart(symbol, period="3mo"):
    try:
        df = yf.download(symbol, period=period, progress=False)
        if df is None or len(df) == 0: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df
    except: return None


def get_session():
    from datetime import timezone
    EDT = timezone(timedelta(hours=-4))
    now = datetime.now(EDT)
    t = now.hour * 60 + now.minute
    if 390 <= t < 570: return "premarket", "ما قبل التداول"
    elif 570 <= t < 960: return "regular", "الجلسة الرسمية"
    elif 960 <= t < 1200: return "afterhours", "الجلسة المسائية"
    else: return "closed", "السوق مغلق"


def prob_color(prob):
    if prob >= 70: return "var(--green)"
    if prob >= 50: return "var(--cyan)"
    if prob >= 30: return "var(--yellow)"
    return "var(--text3)"


def prob_badge(prob):
    if prob >= 70: return "badge-green", "عالي جداً"
    if prob >= 50: return "badge-blue", "مرتفع"
    if prob >= 30: return "badge-yellow", "متوسط"
    return "badge-red", "منخفض"


def main():
    data = load_predictions()
    session_code, session_name = get_session()

    # ─── Header ───
    st.markdown(f"""
    <div class="header">
        <div style="display:flex;align-items:center;gap:16px;">
            <div class="logo">🐋 ماسح الحيتان</div>
            <div style="font-size:12px;color:var(--text3);">تنبؤ بالانفجارات — v5.0</div>
        </div>
        <div style="display:flex;align-items:center;gap:16px;">
            <div class="session-live"><div class="pulse"></div>{session_name}</div>
            <div style="font-size:13px;color:var(--text3);">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if data is None:
        st.markdown("""
        <div style="text-align:center;padding:60px;">
            <div style="font-size:48px;margin-bottom:12px;">📡</div>
            <div style="font-size:20px;font-weight:700;color:var(--text);margin-bottom:8px;">لا توجد تنبؤات بعد</div>
            <div style="color:var(--text2);">شغّل الماسح التنبؤي: python predictive_scanner.py</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Get predictions or signals
    predictions = data.get('predictions', data.get('signals', []))
    scan_time = data.get('scan_time', '')
    model_trained = data.get('model_trained', False)
    total_analyzed = data.get('total_analyzed', len(predictions))

    # Normalize data format
    for p in predictions:
        if 'explosion_probability' not in p and 'whale_score' in p:
            p['explosion_probability'] = p['whale_score']
        if 'explosion_probability' not in p:
            p['explosion_probability'] = 0

    predictions.sort(key=lambda x: x.get('explosion_probability', 0), reverse=True)

    # ─── Tabs ───
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔮 التنبؤات", "📊 الشارت", "⏱ الجلسات", "📈 التحليلات", "📋 التاريخ"
    ])

    # ═══════════════════════════════════════════════════════════
    #  تبويب التنبؤات
    # ═══════════════════════════════════════════════════════════
    with tab1:
        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""<div class="card"><div class="label">إجمالي المُحلل</div>
            <div class="value">{total_analyzed}</div><div class="change up">{scan_time[:16]}</div></div>""", unsafe_allow_html=True)
        with c2:
            high_prob = len([p for p in predictions if p.get('explosion_probability', 0) >= 50])
            st.markdown(f"""<div class="card"><div class="label">احتمالية عالية</div>
            <div class="value" style="color:var(--green);">{high_prob}</div><div class="change up">50%+</div></div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="card"><div class="label">النموذج</div>
            <div class="value">{'ML' if model_trained else 'قواعد'}</div>
            <div class="change up">{'مُدرّب' if model_trained else 'مبني على الأنماط'}</div></div>""", unsafe_allow_html=True)
        with c4:
            avg_prob = sum(p.get('explosion_probability', 0) for p in predictions) / len(predictions) if predictions else 0
            st.markdown(f"""<div class="card"><div class="label">متوسط الاحتمالية</div>
            <div class="value">{avg_prob:.0f}%</div></div>""", unsafe_allow_html=True)

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Prediction list
        for i, p in enumerate(predictions[:20], 1):
            prob = p.get('explosion_probability', 0)
            badge_cls, badge_text = prob_badge(prob)
            squeeze = p.get('bollinger_squeeze', False)
            obv = p.get('obv_above_sma', False)
            rsi = p.get('rsi', 50)

            indicators = []
            if squeeze: indicators.append("🔴 انكماش")
            if obv: indicators.append("📈 OBV صاعد")
            if p.get('volume_ratio', 0) > 2: indicators.append(f"📊 حجم {p.get('volume_ratio', 0)}x")
            if p.get('cmf', 0) > 0.15: indicators.append("🐋 تجميع")
            if p.get('z_score', 0) > 2: indicators.append(f"Z={p.get('z_score', 0)}")

            st.markdown(f"""
            <div class="card">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:16px;">
                        <div style="min-width:60px;text-align:center;">
                            <div style="font-size:28px;font-weight:800;color:{prob_color(prob)};">{prob}%</div>
                            <span class="badge {badge_cls}">{badge_text}</span>
                        </div>
                        <div>
                            <div style="font-size:18px;font-weight:700;color:var(--text);">{p.get('symbol', '')}</div>
                            <div style="color:var(--text2);font-size:13px;margin-top:4px;">{' | '.join(indicators) if indicators else '—'}</div>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:18px;font-weight:600;color:var(--text);">${p.get('price', 0):.2f}</div>
                        <div class="change {'up' if p.get('change_1d', 0) > 0 else 'down'}">{p.get('change_1d', 0):+.1f}% اليوم</div>
                    </div>
                </div>
                <div class="prob-bar"><div class="prob-fill" style="width:{prob}%;background:{prob_color(prob)};"></div></div>
            </div>
            """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    #  تبويب الشارت
    # ═══════════════════════════════════════════════════════════
    with tab2:
        symbols = [p.get('symbol', '') for p in predictions[:30]]
        if not symbols:
            st.info("لا توجد أسهم للعرض.")
        else:
            selected = st.selectbox("اختر سهم", symbols)
            if selected:
                p = next((x for x in predictions if x['symbol'] == selected), None)
                chart_data = get_chart(selected)

                if chart_data is not None:
                    fig = make_subplots(
                        rows=3, cols=1, shared_xaxes=True,
                        vertical_spacing=0.02, row_heights=[0.6, 0.2, 0.2]
                    )

                    # Shammع
                    fig.add_trace(go.Candlestick(
                        x=chart_data.index, open=chart_data['Open'], high=chart_data['High'],
                        low=chart_data['Low'], close=chart_data['Close'], name='السعر',
                        increasing_line_color='#10b981', decreasing_line_color='#ef4444'
                    ), row=1, col=1)

                    # SMA
                    if len(chart_data) > 20:
                        sma20 = chart_data['Close'].rolling(20).mean()
                        fig.add_trace(go.Scatter(x=chart_data.index, y=sma20, name='SMA 20',
                            line=dict(color='#f59e0b', width=1)), row=1, col=1)
                    if len(chart_data) > 50:
                        sma50 = chart_data['Close'].rolling(50).mean()
                        fig.add_trace(go.Scatter(x=chart_data.index, y=sma50, name='SMA 50',
                            line=dict(color='#8b5cf6', width=1)), row=1, col=1)

                    # Bollinger Bands
                    import ta as ta_lib
                    bb = ta_lib.volatility.BollingerBands(chart_data['Close'], window=20, window_dev=2)
                    fig.add_trace(go.Scatter(x=chart_data.index, y=bb.bollinger_hband(), name='BB Upper',
                        line=dict(color='rgba(100,116,139,0.3)', width=1, dash='dot')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_data.index, y=bb.bollinger_lband(), name='BB Lower',
                        line=dict(color='rgba(100,116,139,0.3)', width=1, dash='dot'),
                        fill='tonexty', fillcolor='rgba(100,116,139,0.05)'), row=1, col=1)

                    # Volume
                    colors = ['#10b981' if c > o else '#ef4444'
                              for c, o in zip(chart_data['Close'], chart_data['Open'])]
                    fig.add_trace(go.Bar(x=chart_data.index, y=chart_data['Volume'], name='الحجم',
                        marker_color=colors, opacity=0.5), row=2, col=1)

                    # RSI
                    rsi = ta_lib.momentum.RSIIndicator(chart_data['Close'], window=14)
                    fig.add_trace(go.Scatter(x=chart_data.index, y=rsi.rsi(), name='RSI',
                        line=dict(color='#06b6d4', width=1.5)), row=3, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="rgba(239,68,68,0.3)", row=3, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="rgba(16,185,129,0.3)", row=3, col=1)

                    fig.update_layout(
                        height=700, template="plotly_dark", showlegend=True,
                        margin=dict(l=0, r=0, t=30, b=0),
                        paper_bgcolor='#0a0e17', plot_bgcolor='#111827',
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    fig.update_xaxes(rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

                    # Signal details
                    if p:
                        prob = p.get('explosion_probability', 0)
                        badge_cls, badge_text = prob_badge(prob)
                        st.markdown(f"""
                        <div class="card" style="border-left:4px solid {prob_color(prob)};">
                            <div style="display:flex;align-items:center;gap:16px;">
                                <div style="font-size:32px;font-weight:800;color:{prob_color(prob)};">{prob}%</div>
                                <div>
                                    <div style="font-size:18px;font-weight:700;color:var(--text);">احتمال انفجار {selected}</div>
                                    <div style="margin-top:4px;">
                                        <span class="badge {badge_cls}">{badge_text}</span>
                                        <span class="badge badge-purple">RSI: {p.get('rsi', 50):.0f}</span>
                                        <span class="badge badge-blue">حجم: {p.get('volume_ratio', 0)}x</span>
                                        <span class="badge badge-yellow">CMF: {p.get('cmf', 0):.3f}</span>
                                        {'<span class="badge badge-red">انكماش Bollinger</span>' if p.get('bollinger_squeeze') else ''}
                                        {'<span class="badge badge-green">OBV صاعد</span>' if p.get('obv_above_sma') else ''}
                                    </div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info(f"الرسم البياني لـ {selected} غير متاح.")

    # ═══════════════════════════════════════════════════════════
    #  تبويب الجلسات
    # ═══════════════════════════════════════════════════════════
    with tab3:
        st.markdown("### ⏱ تحليل ما بعد الجلسة")
        st.markdown("""
        <div class="card" style="border-left:4px solid var(--accent);">
            <div style="font-weight:600;color:var(--text);margin-bottom:8px;">كيف يعمل الماسح التنبؤي؟</div>
            <div style="color:var(--text2);font-size:14px;line-height:1.8;">
            1. يُشغّل <b>بعد نهاية كل جلسة</b> (ما قبل التداول، الرسمية، المسائية)<br>
            2. يجمع بيانات <b>كل الأسهم</b> اللي تحركت خلال الجلسة<br>
            3. يحلل <b>المؤشرات الفنية</b> (حجم، RSI، Bollinger، CMF، OBV)<br>
            4. يقارن مع <b>الأنماط التاريخية</b> للأسهم اللي انفجرت سابقاً<br>
            5. يتنبأ بأعلى <b>احتمالية انفجار</b> في الجلسة القادمة
            </div>
        </div>
        """, unsafe_allow_html=True)

        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_history.db")
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                df = pd.read_sql_query("""
                    SELECT session_type, COUNT(*) as count,
                           AVG(volume_ratio) as avg_vol_ratio,
                           AVG(z_score) as avg_z,
                           SUM(CASE WHEN exploded=1 THEN 1 ELSE 0 END) as explosions
                    FROM session_data
                    WHERE scan_time > datetime('now', '-7 days')
                    GROUP BY session_type
                """, conn)
                conn.close()
                if not df.empty:
                    st.dataframe(df, use_container_width=True)
            except:
                st.info("لا توجد بيانات جلسات بعد.")

    # ═══════════════════════════════════════════════════════════
    #  تبويب التحليلات
    # ═══════════════════════════════════════════════════════════
    with tab4:
        if not predictions:
            st.info("لا توجد بيانات كافية للتحليل.")
        else:
            import plotly.express as px
            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**توزيع احتمالات الانفجار**")
                probs = [p.get('explosion_probability', 0) for p in predictions]
                fig = go.Figure(data=[go.Histogram(x=probs, nbinsx=15, marker_color='#3b82f6')])
                fig.update_layout(height=300, template="plotly_dark", xaxis_title="احتمالية %",
                    margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                st.markdown("**الحجم vs احتمال الانفجار**")
                vr = [p.get('volume_ratio', 0) for p in predictions]
                pr = [p.get('explosion_probability', 0) for p in predictions]
                syms = [p.get('symbol', '') for p in predictions]
                fig = go.Figure(data=[go.Scatter(x=vr, y=pr, mode='markers+text',
                    text=syms, textposition='top center', marker=dict(color=pr, colorscale='RdYlGn',
                    size=10))])
                fig.update_layout(height=300, template="plotly_dark",
                    xaxis_title="نسبة الحجم", yaxis_title="احتمالية %",
                    margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
                st.plotly_chart(fig, use_container_width=True)

    # ═══════════════════════════════════════════════════════════
    #  تبويب التاريخ
    # ═══════════════════════════════════════════════════════════
    with tab5:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_history.db")
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                df = pd.read_sql_query(
                    "SELECT scan_time, symbol, volume_ratio, z_score, rsi, cmf, next_session_change, exploded FROM session_data ORDER BY id DESC LIMIT 100", conn)
                conn.close()
                if not df.empty:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("لا توجد بيانات بعد.")
            except:
                st.info("خطأ في قاعدة البيانات.")
        else:
            st.info("قاعدة البيانات غير موجودة.")

    st.markdown('<div style="height:1px;background:var(--border);margin:16px 0;"></div>', unsafe_allow_html=True)
    st.caption("ماسح الحيتان v5.0 — تنبؤ بالانفجارات | بيانات حقيقية فقط | لا توصيات")


if __name__ == "__main__":
    main()
