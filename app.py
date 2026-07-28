"""
ماسح الحيتان v5.0 — منصة تداول احترافية
==========================================
بيانات حقيقية فقط. لا وهميات.
"""
import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, timezone
import yfinance as yf
import sqlite3
import os
import sys
import io

if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except:
        pass

st.set_page_config(page_title="ماسح الحيتان", page_icon="🐋", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root{--bg:#0a0e17;--bg2:#111827;--card:#1a1f2e;--card2:#232a3b;--border:#2a3042;--blue:#3b82f6;
--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--purple:#8b5cf6;--cyan:#06b6d4;--orange:#f97316;
--pink:#ec4899;--text:#f1f5f9;--text2:#94a3b8;--text3:#64748b;}
[data-testid="stAppViewContainer"]{background:var(--bg)!important;}
[data-testid="stSidebar"]{background:var(--bg2)!important;}
.main .block-container{padding-top:0.5rem;max-width:100%;}
.c{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:8px;}
.c:hover{border-color:var(--blue);}
.lb{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.vl{font-size:24px;font-weight:700;color:var(--text);}
.ch{font-size:13px;font-weight:500;}
.ch.up{color:var(--green);}.ch.dn{color:var(--red);}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block;animation:pu 2s infinite;}
@keyframes pu{0%,100%{opacity:1;}50%{opacity:.4;}}
.badge{display:inline-block;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;margin:2px;}
.b-green{background:rgba(16,185,129,.15);color:var(--green);border:1px solid rgba(16,185,129,.3);}
.b-blue{background:rgba(59,130,246,.15);color:var(--blue);border:1px solid rgba(59,130,246,.3);}
.b-yellow{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3);}
.b-red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);}
.b-purple{background:rgba(139,92,246,.15);color:var(--purple);border:1px solid rgba(139,92,246,.3);}
.b-cyan{background:rgba(6,182,212,.15);color:var(--cyan);border:1px solid rgba(6,182,212,.3);}
.b-pink{background:rgba(236,72,153,.15);color:var(--pink);border:1px solid rgba(236,72,153,.3);}
.b-orange{background:rgba(249,115,22,.15);color:var(--orange);border:1px solid rgba(249,115,22,.3);}
.info{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin:12px 0;}
.warn{background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.3);border-radius:12px;padding:20px;margin:12px 0;}
</style>
""", unsafe_allow_html=True)

# ─── تحميل البيانات ─────────────────────────────────────────
def load_scan():
    """يحمّل نتائج المسح — يقبل كلا الصيغتين"""
    for p in ['scan_results.json', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scan_results.json')]:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if d:
                    return d
        except: pass
    try:
        import urllib.request
        url = "https://raw.githubusercontent.com/abdsebvip-byte/whale-scanner/main/scan_results.json"
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except: pass
    return {}

def load_predictions():
    """يحمّل التنبؤات"""
    for p in ['predictions.json', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'predictions.json')]:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if d and d.get('predictions'):
                    return d
        except: pass
    try:
        import urllib.request
        url = "https://raw.githubusercontent.com/abdsebvip-byte/whale-scanner/main/predictions.json"
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except: pass
    return {}

@st.cache_data(ttl=300)
def get_chart(sym, period="3mo"):
    try:
        df = yf.download(sym, period=period, progress=False)
        if df is None or len(df) == 0: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def get_session():
    EDT = timezone(timedelta(hours=-4))
    now = datetime.now(EDT)
    t = now.hour * 60 + now.minute
    if 390 <= t < 570: return "premarket", "ما قبل التداول"
    elif 570 <= t < 960: return "regular", "الجلسة الرسمية"
    elif 960 <= t < 1200: return "afterhours", "الجلسة المسائية"
    else: return "closed", "السوق مغلق"

def prob_color(p):
    if p >= 70: return "var(--green)"
    if p >= 50: return "var(--blue)"
    if p >= 30: return "var(--yellow)"
    return "var(--text3)"

def prob_badge(p):
    if p >= 70: return "b-green", "عالي جداً"
    if p >= 50: return "b-blue", "مرتفع"
    if p >= 30: return "b-yellow", "متوسط"
    return "b-red", "منخفض"

SIGNAL_LABELS = {
    'VOLUME_ANOMALY': 'حجم غير عادي',
    'BOLLINGER_SQUEEZE': 'انكماش',
    'ACCUMULATION': 'تجميع أموال',
    'MULTI_DAY_VOLUME': 'حجم متعدد الأيام',
    'UNUSUAL_OPTIONS': 'خيارات غير عادية',
    'HIGH_SHORT_INTEREST': 'بيع عَمَي مرتفع',
    'ANOMALY_DETECTED': 'شذوذ ذكاء اصطناعي',
    'GAP_DETECTED': 'فجوة سعرية',
    'NEWS_HEAVY': 'أخبار كثيرة',
    'INSIDER_BUYING': 'شراء داخلي',
}

SIGNAL_ICONS = {
    'VOLUME_ANOMALY': '📊', 'BOLLINGER_SQUEEZE': '🔴', 'ACCUMULATION': '🐋',
    'MULTI_DAY_VOLUME': '📈', 'UNUSUAL_OPTIONS': '🔥', 'HIGH_SHORT_INTEREST': '⬆️',
    'ANOMALY_DETECTED': '🤖', 'GAP_DETECTED': '📐', 'NEWS_HEAVY': '📰',
    'INSIDER_BUYING': '💰',
}

# ─── الصفحة الرئيسية ──────────────────────────────────────────
def main():
    scan = load_scan()
    preds = load_predictions()
    session_code, session_name = get_session()

    # البيانات: ناخد signals أو predictions
    signals = scan.get('signals', preds.get('predictions', []))
    predictions = preds.get('predictions', [])
    scan_time = scan.get('scan_time', preds.get('scan_time', ''))

    # ─── الهيدر ───
    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border);margin-bottom:12px;">
        <div style="display:flex;align-items:center;gap:16px;">
            <div style="font-size:26px;font-weight:800;color:var(--text);">🐋 ماسح الحيتان</div>
            <div style="font-size:11px;color:var(--text3);">منصة تداول احترافية v5.0</div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;">
            <div style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:16px;font-size:12px;font-weight:600;
                background:rgba(16,185,129,.12);color:var(--green);border:1px solid rgba(16,185,129,.25);">
                <span class="pulse"></span>{session_name}
            </div>
            <div style="font-size:12px;color:var(--text3);">{datetime.now().strftime('%H:%M')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ─── التنقل ───
    tabs = ["📊 الرئيسية", "🔮 التنبؤات", "⏱ الجلسات", "🔍 الماسح", "🔔 التنبيهات", "📈 التحليلات", "📋 التاريخ"]
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    cols = [c1, c2, c3, c4, c5, c6, c7]
    keys = ['home', 'predict', 'sessions', 'scan', 'alerts', 'analytics', 'history']

    if 'page' not in st.session_state:
        st.session_state.page = 'home'

    for i, (col, label, key) in enumerate(zip(cols, tabs, keys)):
        with col:
            if st.button(label, key=f"n{i}", use_container_width=True):
                st.session_state.page = key

    page = st.session_state.page
    st.markdown('<div style="height:1px;background:var(--border);margin:4px 0 16px 0;"></div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    if page == 'home':
        page_home(signals, scan_time, session_name)
    elif page == 'predict':
        page_predictions(predictions, preds)
    elif page == 'sessions':
        page_sessions(signals)
    elif page == 'scan':
        page_scanner(signals)
    elif page == 'alerts':
        page_alerts(signals)
    elif page == 'analytics':
        page_analytics(signals, predictions)
    elif page == 'history':
        page_history()


# ═══════════════════════════════════════════════════════════════
#  الرئيسية
# ═══════════════════════════════════════════════════════════════
def page_home(signals, scan_time, session_name):
    total = len(signals)
    if total == 0 and not predictions_available():
        st.markdown("""
        <div class="info" style="text-align:center;">
            <div style="font-size:48px;margin-bottom:12px;">📡</div>
            <div style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:8px;">لا توجد بيانات بعد</div>
            <div style="color:var(--text2);">شغّل الماسح: <code>python predictive_scanner.py</code></div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ملخص
    preds = load_predictions()
    pred_list = preds.get('predictions', [])
    high_count = len([p for p in pred_list if p.get('explosion_probability', 0) >= 50])

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<div class="c"><div class="lb">التنبؤات</div><div class="vl">{len(pred_list)}</div><div class="ch up">سهم مُحلل</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="c"><div class="lb">احتمالية عالية</div><div class="vl" style="color:var(--green);">{high_count}</div><div class="ch up">50%+</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="c"><div class="lb">آخر مسح</div><div class="vl" style="font-size:16px;">{scan_time[:16] if scan_time else "—"}</div></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="c"><div class="lb">الجلسة</div><div class="vl" style="font-size:16px;">{session_name}</div></div>', unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # أفضل 5 تنبؤات
    if pred_list:
        st.markdown("### 🔮 أعلى 5 احتمالات للانفجار")
        for p in pred_list[:5]:
            prob = p.get('explosion_probability', 0)
            bc, bt = prob_badge(prob)
            pc = prob_color(prob)

            indicators = []
            if p.get('bollinger_squeeze'): indicators.append('انكماش')
            if p.get('obv_above_sma'): indicators.append('OBV صاعد')
            if p.get('volume_ratio', 0) > 2: indicators.append(f'حجم {p["volume_ratio"]}x')
            if p.get('cmf', 0) > 0.15: indicators.append('تجميع')
            if p.get('z_score', 0) > 2: indicators.append(f'Z={p["z_score"]}')

            ind_html = ' '.join([f'<span class="badge b-cyan">{i}</span>' for i in indicators]) if indicators else '<span style="color:var(--text3);">—</span>'

            st.markdown(f"""
            <div class="c" style="border-left:4px solid {pc};">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:16px;">
                        <div style="min-width:70px;text-align:center;">
                            <div style="font-size:28px;font-weight:800;color:{pc};">{prob}%</div>
                            <span class="badge {bc}">{bt}</span>
                        </div>
                        <div>
                            <div style="font-size:18px;font-weight:700;color:var(--text);">{p.get('symbol', '')}</div>
                            <div style="margin-top:4px;">{ind_html}</div>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:18px;font-weight:600;color:var(--text);">${p.get('price', 0):.2f}</div>
                        <div class="ch {'up' if p.get('change_1d', 0) > 0 else 'dn'}">{p.get('change_1d', 0):+.1f}% يوم | {p.get('change_5d', 0):+.1f}% 5 أيام</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


def predictions_available():
    try:
        p = load_predictions()
        return bool(p and p.get('predictions'))
    except: return False


# ═══════════════════════════════════════════════════════════════
#  التنبؤات
# ═══════════════════════════════════════════════════════════════
def page_predictions(predictions, preds):
    st.markdown("### 🔮 تنبؤات انفجار الأسهم — الجلسة القادمة")

    st.markdown("""
    <div class="info">
        <b>كيف يشتغل هذا القسم؟</b><br>
        الماسح يُشغّل بعد نهاية كل جلسة. يحلل 400+ سهم ويتوقع أيهم ممكن ينفجر في الجلسة القادمة.
        الاحتمال مبني على: حجم التداول + قوة التجميع + انكماش السعر + مؤشرات فنية.
    </div>
    """, unsafe_allow_html=True)

    if not predictions:
        st.warning("لا توجد تنبؤات. شغّل الماسح: <code>python predictive_scanner.py</code>")
        return

    model = preds.get('model_trained', False)
    analyzed = preds.get('total_analyzed', len(predictions))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="c"><div class="lb">مُحلل</div><div class="vl">{analyzed} سهم</div></div>', unsafe_allow_html=True)
    with c2:
        high = len([p for p in predictions if p.get('explosion_probability', 0) >= 50])
        st.markdown(f'<div class="c"><div class="lb">احتمالية عالية</div><div class="vl" style="color:var(--green);">{high}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="c"><div class="lb">النموذج</div><div class="vl">{"ذكاء اصطناعي" if model else "قواعد"}</div></div>', unsafe_allow_html=True)

    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    # جدول التنبؤات
    table_data = []
    for p in predictions:
        table_data.append({
            'السهم': p.get('symbol', ''),
            'السعر': f"${p.get('price', 0):.2f}",
            'احتمال الانفجار': f"{p.get('explosion_probability', 0)}%",
            'الحجم': f"{p.get('volume_ratio', 0)}x",
            'Z-Score': p.get('z_score', 0),
            'RSI': f"{p.get('rsi', 0):.0f}",
            'قوة التجميع': round(p.get('cmf', 0), 3),
            'انكماش': 'نعم' if p.get('bollinger_squeeze') else 'لا',
            'OBV': 'صاعد' if p.get('obv_above_sma') else 'هابط',
            'يوم': f"{p.get('change_1d', 0):+.1f}%",
            '5 أيام': f"{p.get('change_5d', 0):+.1f}%",
        })
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, height=400)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # شارت سهم
    syms = [p['symbol'] for p in predictions[:30]]
    selected = st.selectbox("اختر سهم لعرض شارته", syms)
    if selected:
        p = next((x for x in predictions if x['symbol'] == selected), None)
        chart = get_chart(selected)
        if chart is not None and p:
            col_a, col_b = st.columns([1, 1])
            with col_a:
                prob = p.get('explosion_probability', 0)
                bc, bt = prob_badge(prob)
                pc = prob_color(prob)
                st.markdown(f"""
                <div class="c" style="border-left:4px solid {pc};">
                    <div style="font-size:28px;font-weight:800;color:{pc};">{prob}% احتمال الانفجار</div>
                    <span class="badge {bc}" style="margin-top:8px;">{bt}</span>
                    <div style="margin-top:12px;color:var(--text2);line-height:2;">
                        السعر: <b style="color:var(--text);">${p.get('price', 0):.2f}</b><br>
                        الحجم: <b style="color:var(--text);">{p.get('volume_ratio', 0)}x</b> من المتوسط<br>
                        Z-Score: <b style="color:var(--text);">{p.get('z_score', 0)}</b><br>
                        RSI: <b style="color:var(--text);">{p.get('rsi', 0):.0f}</b><br>
                        قوة التجميع: <b style="color:var(--text);">{p.get('cmf', 0):.3f}</b><br>
                        انكماش: <b style="color:var(--text);">{"نعم" if p.get('bollinger_squeeze') else "لا"}</b><br>
                        OBV: <b style="color:var(--text);">{"صاعد" if p.get('obv_above_sma') else "هابط"}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col_b:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=chart.index, open=chart['Open'], high=chart['High'],
                    low=chart['Low'], close=chart['Close'], name='السعر'), row=1, col=1)
                if len(chart) > 20:
                    sma = chart['Close'].rolling(20).mean()
                    fig.add_trace(go.Scatter(x=chart.index, y=sma, name='متوسط 20 يوم',
                        line=dict(color='#f59e0b', width=1)), row=1, col=1)
                fig.add_trace(go.Bar(x=chart.index, y=chart['Volume'], name='الحجم',
                    marker_color='rgba(59,130,246,0.3)'), row=2, col=1)
                fig.update_layout(height=450, template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0),
                    xaxis_rangeslider_visible=False, paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
                st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
#  الجلسات
# ═══════════════════════════════════════════════════════════════
def page_sessions(signals):
    st.markdown("### ⏱ تحليل الجلسات")
    st.markdown("""
    <div class="info">
        <b>الجلسات الثلاث:</b><br>
        🌅 <b>ما قبل التداول</b> (6:30 - 9:30 صباحاً) — تحركات مبكرة قبل الافتتاح<br>
        📊 <b>الجلسة الرسمية</b> (9:30 - 4:00 مساءً) — التداول الأساسي<br>
        🌙 <b>الجلسة المسائية</b> (4:00 - 8:00 مساءً) — تحركات مؤسسية<br><br>
        الماسح يُشغّل بعد نهاية كل جلسة ويتنبأ بالقادمة.
    </div>
    """, unsafe_allow_html=True)

    preds = load_predictions()
    pred_list = preds.get('predictions', [])
    pred_session = preds.get('session', preds.get('session_name', ''))

    # ملخص الحالة
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="c"><div class="lb">آخر مسح</div><div class="vl" style="font-size:14px;">{preds.get("scan_time", "—")[:16]}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="c"><div class="lb">الجلسة</div><div class="vl" style="font-size:14px;">{preds.get("session_name", "—")}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="c"><div class="lb">عدد التنبؤات</div><div class="vl">{len(pred_list)}</div></div>', unsafe_allow_html=True)
    with c4:
        high = len([p for p in pred_list if p.get('explosion_probability', 0) >= 50])
        st.markdown(f'<div class="c"><div class="lb">احتمالية عالية</div><div class="vl" style="color:var(--green);">{high}</div></div>', unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    if pred_list:
        # فلترة حسب الاحتمال
        min_prob = st.slider("أدنى احتمال (%)", 0, 100, 30, 5)
        filtered = [p for p in pred_list if p.get('explosion_probability', 0) >= min_prob]

        for p in filtered[:15]:
            prob = p.get('explosion_probability', 0)
            bc, bt = prob_badge(prob)
            pc = prob_color(prob)
            st.markdown(f"""
            <div class="c" style="border-left:4px solid {pc};">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <div style="font-size:22px;font-weight:800;color:{pc};">{prob}%</div>
                        <div>
                            <div style="font-size:16px;font-weight:700;color:var(--text);">{p.get('symbol', '')} — ${p.get('price', 0):.2f}</div>
                            <div style="margin-top:4px;">
                                <span class="badge {bc}">{bt}</span>
                                <span class="badge b-cyan">حجم {p.get('volume_ratio', 0)}x</span>
                                <span class="badge b-purple">RSI {p.get('rsi', 0):.0f}</span>
                                {"<span class='badge b-orange'>انكماش</span>" if p.get('bollinger_squeeze') else ""}
                            </div>
                        </div>
                    </div>
                    <div class="ch {'up' if p.get('change_1d',0) > 0 else 'dn'}">{p.get('change_1d', 0):+.1f}%</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("لا توجد تنبؤات. شغّل الماسح أولاً.")


# ═══════════════════════════════════════════════════════════════
#  الماسح
# ═══════════════════════════════════════════════════════════════
def page_scanner(signals):
    st.markdown("### 🔍 فلترة وتحليل")

    preds = load_predictions()
    pred_list = preds.get('predictions', [])

    if not pred_list:
        st.info("لا توجد بيانات. شغّل الماسح أولاً.")
        return

    # فلاتر
    c1, c2, c3 = st.columns(3)
    with c1:
        min_prob = st.slider("أدنى احتمال", 0, 100, 20, 5)
    with c2:
        max_price = st.number_input("أعلى سعر ($)", value=1000, step=10)
    with c3:
        sort_by = st.selectbox("ترتيب", ["احتمال الانفجار", "Z-Score", "السعر"])

    filtered = [p for p in pred_list if p.get('explosion_probability', 0) >= min_prob and p.get('price', 0) <= max_price]

    if sort_by == "احتمال الانفجار":
        filtered.sort(key=lambda x: x.get('explosion_probability', 0), reverse=True)
    elif sort_by == "Z-Score":
        filtered.sort(key=lambda x: x.get('z_score', 0), reverse=True)
    elif sort_by == "السعر":
        filtered.sort(key=lambda x: x.get('price', 0))

    # تصدير
    if filtered:
        csv = pd.DataFrame(filtered).to_csv(index=False, encoding='utf-8-sig')
        st.download_button("📥 تصدير CSV", csv, "whale_predictions.csv")

    st.markdown(f"**{len(filtered)} سهم**")

    for p in filtered:
        prob = p.get('explosion_probability', 0)
        bc, bt = prob_badge(prob)
        pc = prob_color(prob)

        with st.expander(f"{p.get('symbol', '')} — ${p.get('price', 0):.2f} — {prob}% احتمال"):
            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.markdown(f"""
                <div style="line-height:2;color:var(--text2);font-size:14px;">
                    <b style="color:{pc};font-size:20px;">{prob}%</b> <span class="badge {bc}">{bt}</span><br>
                    السعر: <b style="color:var(--text);">${p.get('price', 0):.2f}</b><br>
                    الحجم: <b style="color:var(--text);">{p.get('volume_ratio', 0)}x</b> من المتوسط<br>
                    Z-Score: <b style="color:var(--text);">{p.get('z_score', 0)}</b><br>
                    RSI: <b style="color:var(--text);">{p.get('rsi', 0):.0f}</b><br>
                    قوة التجميع: <b style="color:var(--text);">{p.get('cmf', 0):.3f}</b><br>
                    انكماش: <b style="color:var(--text);">{"نعم" if p.get('bollinger_squeeze') else "لا"}</b><br>
                    OBV: <b style="color:var(--text);">{"صاعد" if p.get('obv_above_sma') else "هابط"}</b><br>
                    تغيير يوم: <b class="ch {'up' if p.get('change_1d',0)>0 else 'dn'}">{p.get('change_1d', 0):+.1f}%</b><br>
                    تغيير 5 أيام: <b class="ch {'up' if p.get('change_5d',0)>0 else 'dn'}">{p.get('change_5d', 0):+.1f}%</b>
                </div>
                """, unsafe_allow_html=True)
            with col_b:
                chart = get_chart(p['symbol'], period="1mo")
                if chart is not None:
                    fig = go.Figure(data=[go.Candlestick(x=chart.index, open=chart['Open'],
                        high=chart['High'], low=chart['Low'], close=chart['Close'])])
                    fig.update_layout(height=300, template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0),
                        xaxis_rangeslider_visible=False, paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
                    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
#  التنبيهات
# ═══════════════════════════════════════════════════════════════
def page_alerts(signals):
    st.markdown("### 🔔 التنبيهات")

    preds = load_predictions()
    pred_list = preds.get('predictions', [])

    if not pred_list:
        st.info("لا توجد تنبيهات.")
        return

    critical = [p for p in pred_list if p.get('explosion_probability', 0) >= 70]
    warning = [p for p in pred_list if 50 <= p.get('explosion_probability', 0) < 70]
    info = [p for p in pred_list if 30 <= p.get('explosion_probability', 0) < 50]

    if critical:
        st.markdown("#### 🔴 تنبيهات حرجة (70%+)")
        for p in critical:
            st.markdown(f"""
            <div class="c" style="border-left:4px solid var(--red);">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <div style="font-size:16px;">🔴</div>
                        <div>
                            <div style="font-weight:700;color:var(--text);font-size:16px;">{p.get('symbol', '')} — {p.get('explosion_probability', 0)}%</div>
                            <div style="color:var(--text2);font-size:13px;">${p.get('price', 0):.2f} | حجم {p.get('volume_ratio', 0)}x | Z={p.get('z_score', 0)}</div>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if warning:
        st.markdown("#### 🟡 تحذيرات (50-70%)")
        for p in warning:
            st.markdown(f"""
            <div class="c" style="border-left:4px solid var(--yellow);">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <div style="font-size:16px;">🟡</div>
                        <div>
                            <div style="font-weight:700;color:var(--text);font-size:16px;">{p.get('symbol', '')} — {p.get('explosion_probability', 0)}%</div>
                            <div style="color:var(--text2);font-size:13px;">${p.get('price', 0):.2f} | حجم {p.get('volume_ratio', 0)}x</div>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if info:
        st.markdown("#### 🔵 ملاحظات (30-50%)")
        for p in info[:5]:
            st.markdown(f"""
            <div class="c" style="border-left:4px solid var(--blue);">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <div style="font-size:16px;">🔵</div>
                        <div>
                            <div style="font-weight:700;color:var(--text);font-size:16px;">{p.get('symbol', '')} — {p.get('explosion_probability', 0)}%</div>
                            <div style="color:var(--text2);font-size:13px;">${p.get('price', 0):.2f}</div>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  التحليلات
# ═══════════════════════════════════════════════════════════════
def page_analytics(signals, predictions):
    st.markdown("### 📈 تحليلات")

    preds = load_predictions()
    pred_list = preds.get('predictions', [])

    if not pred_list:
        st.info("لا توجد بيانات كافية.")
        return

    import plotly.express as px

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**توزيع احتمالات الانفجار**")
        probs = [p.get('explosion_probability', 0) for p in pred_list]
        fig = go.Figure(data=[go.Histogram(x=probs, nbinsx=12, marker_color='#3b82f6')])
        fig.update_layout(height=300, template="plotly_dark", xaxis_title="احتمالية %",
            margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("**الحجم vs الاحتمالية**")
        fig = go.Figure(data=[go.Scatter(
            x=[p.get('volume_ratio', 0) for p in pred_list],
            y=[p.get('explosion_probability', 0) for p in pred_list],
            text=[p.get('symbol', '') for p in pred_list],
            mode='markers+text', textposition='top center',
            marker=dict(color=[p.get('explosion_probability', 0) for p in pred_list],
            colorscale='RdYlGn', size=10))])
        fig.update_layout(height=300, template="plotly_dark", xaxis_title="نسبة الحجم", yaxis_title="احتمالية %",
            margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
        st.plotly_chart(fig, use_container_width=True)

    # Top 10
    st.markdown("**أعلى 10 by حجم**")
    top_vol = sorted(pred_list, key=lambda x: x.get('volume_ratio', 0), reverse=True)[:10]
    fig = go.Figure(data=[go.Bar(
        y=[p.get('symbol', '') for p in top_vol],
        x=[p.get('volume_ratio', 0) for p in top_vol],
        orientation='h', marker_color='#8b5cf6')])
    fig.update_layout(height=350, template="plotly_dark", xaxis_title="نسبة الحجم",
        margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
#  التاريخ
# ═══════════════════════════════════════════════════════════════
def page_history():
    st.markdown("### 📋 تاريخ التنبؤات")

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_history.db")
    if not os.path.exists(db_path):
        st.info("قاعدة البيانات غير موجودة — ستُنشأ تلقائياً بعد أول مسح.")
        return

    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            "SELECT scan_time as الوقت, symbol as السهم, volume_ratio as الحجم, z_score as ZScore, rsi as RSI, round(cmf,3) as قوة_التجميع FROM session_data ORDER BY id DESC LIMIT 100", conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد بيانات بعد.")
    except Exception as e:
        st.error(f"خطأ: {e}")


# ─── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
