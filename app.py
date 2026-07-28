"""
ماسح الحيتان v5.0 — منصة التداول الاحترافية
============================================
منصة حقيقية لتحليل السوق الأمريكي — لا وهميات.
"""
import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf
import sqlite3
import os
import time

# ─── الصفحة ────────────────────────────────────────────────────
st.set_page_config(
    page_title="ماسح الحيتان — منصة تداول",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": " Whale Scanner v5.0 — Professional US Stock Scanner"}
)

# ─── CSS احترافي ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
    --bg-primary: #0a0e17;
    --bg-secondary: #111827;
    --bg-card: #1a1f2e;
    --bg-card-hover: #232a3b;
    --border: #2a3042;
    --border-active: #3b82f6;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-blue: #3b82f6;
    --accent-green: #10b981;
    --accent-red: #ef4444;
    --accent-yellow: #f59e0b;
    --accent-purple: #8b5cf6;
    --accent-cyan: #06b6d4;
    --accent-orange: #f97316;
}

[data-testid="stAppViewContainer"] {background: var(--bg-primary) !important;}
[data-testid="stSidebar"] {background: var(--bg-secondary) !important;}
[data-testid="stHeader"] {background: var(--bg-secondary) !important;}

.main .block-container {padding-top: 0.5rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%;}

/* Navigation */
.nav-bar {
    display: flex; gap: 0; background: var(--bg-card); border-radius: 12px;
    padding: 4px; margin-bottom: 1rem; border: 1px solid var(--border);
}
.nav-item {
    flex: 1; padding: 12px 16px; border-radius: 8px; text-align: center;
    cursor: pointer; font-weight: 500; color: var(--text-secondary);
    transition: all 0.2s; font-size: 14px;
}
.nav-item:hover {background: var(--bg-card-hover); color: var(--text-primary);}
.nav-item.active {background: var(--accent-blue); color: white; font-weight: 600;}

/* Cards */
.metric-card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; margin-bottom: 8px; transition: all 0.2s;
}
.metric-card:hover {border-color: var(--border-active); transform: translateY(-1px);}
.metric-label {font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;}
.metric-value {font-size: 24px; font-weight: 700; color: var(--text-primary);}
.metric-change {font-size: 13px; font-weight: 500;}
.metric-change.up {color: var(--accent-green);}
.metric-change.down {color: var(--accent-red);}

/* Session Indicator */
.session-badge {
    display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px;
    border-radius: 20px; font-size: 13px; font-weight: 600;
}
.session-badge.live {background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3);}
.session-badge.premarket {background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3);}
.session-badge.afterhours {background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.3);}
.session-badge.closed {background: rgba(100, 116, 139, 0.15); color: #64748b; border: 1px solid rgba(100, 116, 139, 0.3);}
.pulse-dot {width: 8px; height: 8px; border-radius: 50%; background: #10b981; animation: pulse 2s infinite;}
@keyframes pulse {0%, 100% {opacity: 1;} 50% {opacity: 0.4;}}

/* Badges */
.badge {
    display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px;
    border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase;
}
.badge-a {background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3);}
.badge-b {background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3);}
.badge-c {background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3);}
.badge-d {background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3);}
.badge-volume {background: rgba(6, 182, 212, 0.15); color: #06b6d4; border: 1px solid rgba(6, 182, 212, 0.3);}
.badge-squeeze {background: rgba(249, 115, 22, 0.15); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.3);}
.badge-accum {background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.3);}
.badge-options {background: rgba(236, 72, 153, 0.15); color: #ec4899; border: 1px solid rgba(236, 72, 153, 0.3);}
.badge-short {background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3);}
.badge-ai {background: rgba(168, 85, 247, 0.15); color: #a855f7; border: 1px solid rgba(168, 85, 247, 0.3);}
.badge-gap {background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3);}
.badge-news {background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3);}
.badge-insider {background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3);}

/* Stock Row */
.stock-row {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;
}
.stock-row:hover {border-color: var(--border-active); background: var(--bg-card-hover);}
.stock-symbol {font-size: 18px; font-weight: 700; color: var(--text-primary);}
.stock-price {font-size: 16px; font-weight: 600; color: var(--text-primary);}
.stock-change {font-size: 14px; font-weight: 600; padding: 2px 8px; border-radius: 4px;}
.stock-change.up {background: rgba(16, 185, 129, 0.15); color: #10b981;}
.stock-change.down {background: rgba(239, 68, 68, 0.15); color: #ef4444;}

/* Alert Panel */
.alert-panel {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; border-left: 4px solid var(--accent-blue);
}
.alert-item {
    display: flex; align-items: center; gap: 12px; padding: 10px 0;
    border-bottom: 1px solid var(--border);
}
.alert-item:last-child {border-bottom: none;}

/* Score Gauge */
.score-gauge {
    width: 80px; height: 80px; border-radius: 50%; display: flex;
    align-items: center; justify-content: center; font-size: 20px;
    font-weight: 800; border: 3px solid;
}
.score-gauge.high {border-color: var(--accent-green); color: var(--accent-green);}
.score-gauge.mid {border-color: var(--accent-blue); color: var(--accent-blue);}
.score-gauge.low {border-color: var(--accent-yellow); color: var(--accent-yellow);}
.score-gauge.weak {border-color: var(--accent-red); color: var(--accent-red);}

/* Section Headers */
.section-header {
    font-size: 18px; font-weight: 700; color: var(--text-primary);
    margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border);
}

/* Sidebar */
div[data-testid="stSidebarNav"] {padding-top: 0;}
.sidebar-section {margin-bottom: 16px;}
.sidebar-label {font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;}

/* Tabs */
.tab-container {display: flex; gap: 0; background: var(--bg-card); border-radius: 8px; padding: 3px; margin-bottom: 16px;}
.tab-item {
    flex: 1; padding: 10px 16px; border-radius: 6px; text-align: center;
    font-weight: 500; color: var(--text-secondary); cursor: pointer; font-size: 13px;
    transition: all 0.15s;
}
.tab-item:hover {color: var(--text-primary);}
.tab-item.active {background: var(--accent-blue); color: white;}

/* Progress Bar */
.progress-bar {height: 6px; background: var(--border); border-radius: 3px; overflow: hidden;}
.progress-fill {height: 100%; border-radius: 3px; transition: width 0.3s;}

/* Table */
.data-table {width: 100%; border-collapse: collapse;}
.data-table th {
    background: var(--bg-card); padding: 12px 16px; text-align: right;
    font-size: 11px; font-weight: 600; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border);
}
.data-table td {
    padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 14px;
    color: var(--text-primary);
}
.data-table tr:hover td {background: var(--bg-card-hover);}
</style>
""", unsafe_allow_html=True)

# ─── Functions ─────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_results():
    import urllib.request
    for candidate in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scan_results.json'),
        'scan_results.json',
    ]:
        try:
            with open(candidate, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data and data.get('signals'):
                    return data
        except Exception:
            pass
    try:
        url = "https://raw.githubusercontent.com/abdsebvip-byte/whale-scanner/main/scan_results.json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_stock_chart(symbol, period="1mo"):
    try:
        df = yf.download(symbol, period=period, progress=False)
        if df is None or len(df) == 0:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

def get_current_session():
    from datetime import timezone
    EDT = timezone(timedelta(hours=-4))
    now = datetime.now(EDT)
    t = now.hour * 60 + now.minute
    if 390 <= t < 570:
        return "premarket", "ماقبل التداول", "premarket"
    elif 570 <= t < 960:
        return "regular", "الجلسة الرسمية", "live"
    elif 960 <= t < 1200:
        return "afterhours", "الجلسة المسائية", "afterhours"
    else:
        return "closed", "السوق مغلق", "closed"

def get_badge_html(sig_type):
    badges = {
        'VOLUME_ANOMALY': ('badge-volume', '📊 حجم'),
        'BOLLINGER_SQUEEZE': ('badge-squeeze', '🔴 انكماش'),
        'ACCUMULATION': ('badge-accum', '🐋 تجميع'),
        'MULTI_DAY_VOLUME': ('badge-volume', '📈 حجم متعدد'),
        'UNUSUAL_OPTIONS': ('badge-options', '🔥 خيارات'),
        'HIGH_SHORT_INTEREST': ('badge-short', '⬆️ عَمَي'),
        'ANOMALY_DETECTED': ('badge-ai', '🤖 شذوذ'),
        'GAP_DETECTED': ('badge-gap', '📐 فجوة'),
        'NEWS_HEAVY': ('badge-news', '📰 أخبار'),
        'INSIDER_BUYING': ('badge-insider', '💰 داخلي'),
    }
    cls, label = badges.get(sig_type, ('badge-b', sig_type))
    return f'<span class="badge {cls}">{label}</span>'

def get_grade_html(grade):
    grade_map = {
        'A+': ('badge-a', 'A+'), 'A': ('badge-a', 'A'),
        'B+': ('badge-b', 'B+'), 'B': ('badge-b', 'B'),
        'C': ('badge-c', 'C'), 'D': ('badge-d', 'D'),
    }
    cls, label = grade_map.get(grade, ('badge-d', '?'))
    return f'<span class="badge {cls}">{label}</span>'

def get_score_class(score):
    if score >= 60: return 'high'
    if score >= 40: return 'mid'
    if score >= 25: return 'low'
    return 'weak'

SIGNAL_TYPE_LABELS = {
    'VOLUME_ANOMALY': '📊 حجم غير عادي',
    'BOLLINGER_SQUEEZE': '🔴 انكماش Bollinger',
    'ACCUMULATION': '🐋 تجميع أموال',
    'MULTI_DAY_VOLUME': '📈 حجم عالي متعدد الأيام',
    'UNUSUAL_OPTIONS': '🔥 خيارات غير عادية',
    'HIGH_SHORT_INTEREST': '⬆️ بيع عَمَي مرتفع',
    'ANOMALY_DETECTED': '🤖 شذوذ ذكاء اصطناعي',
    'GAP_DETECTED': '📐 فجوة سعرية',
    'NEWS_HEAVY': '📰 أخبار كثيرة',
    'INSIDER_BUYING': '💰 شراء داخلي',
}

# ─── Main ──────────────────────────────────────────────────────
def main():
    session_code, session_name, session_css = get_current_session()
    data = load_results()

    # ─── Header ───
    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-bottom:1px solid var(--border); margin-bottom:16px;">
        <div style="display:flex; align-items:center; gap:16px;">
            <div style="font-size:28px; font-weight:800; color:var(--text-primary);">🐋 ماسح الحيتان</div>
            <div style="font-size:12px; color:var(--text-muted);">v5.0 — منصة تداول احترافية</div>
        </div>
        <div style="display:flex; align-items:center; gap:16px;">
            <div class="session-badge {session_css}">
                <div class="pulse-dot"></div>
                {session_name}
            </div>
            <div style="font-size:13px; color:var(--text-muted);">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if data is None:
        st.markdown("""
        <div style="text-align:center; padding:80px 20px;">
            <div style="font-size:64px; margin-bottom:16px;">📡</div>
            <div style="font-size:24px; font-weight:700; color:var(--text-primary); margin-bottom:8px;">لا توجد بيانات</div>
            <div style="color:var(--text-secondary);">شغّل الماسح أولاً — python run_scan.py</div>
        </div>
        """, unsafe_allow_html=True)
        return

    signals = data.get('signals', [])
    scan_time = data.get('scan_time', '')

    # ─── Navigation ───
    if 'nav_page' not in st.session_state:
        st.session_state.nav_page = 'dashboard'

    nav_cols = st.columns(7)
    pages = [
        ('dashboard', '📊 الرئيسية'),
        ('predictions', '🔮 التنبؤات'),
        ('sessions', '⏱ الجلسات'),
        ('scanner', '🔍 الماسح'),
        ('alerts', '🔔 التنبيهات'),
        ('analytics', '📈 التحليلات'),
        ('history', '📋 التاريخ'),
    ]
    for i, (key, label) in enumerate(pages):
        with nav_cols[i]:
            if st.button(label, key=f"nav_{key}", use_container_width=True):
                st.session_state.nav_page = key

    st.markdown('<div style="height:1px; background:var(--border); margin:8px 0 16px 0;"></div>', unsafe_allow_html=True)

    page = st.session_state.nav_page

    # ═══════════════════════════════════════════════════════════
    #  الصفحة الرئيسية
    # ═══════════════════════════════════════════════════════════
    if page == 'dashboard':
        render_dashboard(signals, scan_time, session_name)

    # ═══════════════════════════════════════════════════════════
    #  التنبؤات
    # ═══════════════════════════════════════════════════════════
    elif page == 'predictions':
        render_predictions()

    # ═══════════════════════════════════════════════════════════
    #  الجلسات
    # ═══════════════════════════════════════════════════════════
    elif page == 'sessions':
        render_sessions(signals, session_code)

    # ═══════════════════════════════════════════════════════════
    #  الماسح
    # ═══════════════════════════════════════════════════════════
    elif page == 'scanner':
        render_scanner(signals)

    # ═══════════════════════════════════════════════════════════
    #  التنبيهات
    # ═══════════════════════════════════════════════════════════
    elif page == 'alerts':
        render_alerts(signals)

    # ═══════════════════════════════════════════════════════════
    #  التحليلات
    # ═══════════════════════════════════════════════════════════
    elif page == 'analytics':
        render_analytics(signals)

    # ═══════════════════════════════════════════════════════════
    #  التاريخ
    # ═══════════════════════════════════════════════════════════
    elif page == 'history':
        render_history()


# ─── الصفحة الرئيسية ──────────────────────────────────────────
def render_dashboard(signals, scan_time, session_name):
    total = len(signals)
    avg_score = sum(s.get('whale_score', 0) for s in signals) / total if total else 0
    a_count = len([s for s in signals if s.get('grade', '') in ['A+', 'A']])
    options_count = len([s for s in signals if any(sig['type'] == 'UNUSUAL_OPTIONS' for sig in s.get('signals', []))])

    # ─── Metrics Row ───
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">إجمالي الإشارات</div>
            <div class="metric-value">{total}</div>
            <div class="metric-change up">آخر مسح: {scan_time[:16]}</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">متوسط الدرجة</div>
            <div class="metric-value">{avg_score:.0f}/100</div>
            <div class="metric-change up">إشارات قوية: {a_count}</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">خيارات غير عادية</div>
            <div class="metric-value">{options_count}</div>
            <div class="metric-change up">عقود مثيرة</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        vol_count = len([s for s in signals if any(sig['type'] == 'VOLUME_ANOMALY' for sig in s.get('signals', []))])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">حجم غير عادي</div>
            <div class="metric-value">{vol_count}</div>
            <div class="metric-change up">Z-Score > 2</div>
        </div>
        """, unsafe_allow_html=True)
    with m5:
        gap_count = len([s for s in signals if any(sig['type'] == 'GAP_DETECTED' for sig in s.get('signals', []))])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">فجوات سعرية</div>
            <div class="metric-value">{gap_count}</div>
            <div class="metric-change up">فجوات > 2%</div>
        </div>
        """, unsafe_allow_html=True)
    with m6:
        insider_count = len([s for s in signals if any(sig['type'] == 'INSIDER_BUYING' for sig in s.get('signals', []))])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">شراء داخلي</div>
            <div class="metric-value">{insider_count}</div>
            <div class="metric-change up">مسؤولون يشترون</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

    # ─── Top Signals + Chart ───
    col_list, col_chart = st.columns([2, 3])

    with col_list:
        st.markdown('<div class="section-header">🏆 أفضل الإشارات</div>', unsafe_allow_html=True)
        for i, sig in enumerate(signals[:15], 1):
            vd = sig.get('volume_data', {})
            score = sig.get('whale_score', 0)
            grade = sig.get('grade', '?')
            sigs = sig.get('signals', [])
            badges_html = ' '.join([get_badge_html(s['type']) for s in sigs])

            st.markdown(f"""
            <div class="stock-row">
                <div style="display:flex; align-items:center; justify-content:space-between;">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <div class="score-gauge {get_score_class(score)}">{score}</div>
                        <div>
                            <div class="stock-symbol">{sig['symbol']}</div>
                            <div style="margin-top:4px;">{badges_html}</div>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div class="stock-price">${sig.get('price', 0):.2f}</div>
                        <div style="margin-top:4px;">{get_grade_html(grade)}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col_chart:
        if signals:
            top = signals[0]
            st.markdown(f'<div class="section-header">📈 {top["symbol"]} — الرسم البياني</div>', unsafe_allow_html=True)
            chart_df = get_stock_chart(top['symbol'])
            if chart_df is not None:
                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.03, row_heights=[0.7, 0.3]
                )
                fig.add_trace(go.Candlestick(
                    x=chart_df.index, open=chart_df['Open'], high=chart_df['High'],
                    low=chart_df['Low'], close=chart_df['Close'], name='السعر'
                ), row=1, col=1)

                if len(chart_df) > 20:
                    sma20 = chart_df['Close'].rolling(20).mean()
                    fig.add_trace(go.Scatter(
                        x=chart_df.index, y=sma20, name='SMA 20',
                        line=dict(color='#f59e0b', width=1)
                    ), row=1, col=1)

                fig.add_trace(go.Bar(
                    x=chart_df.index, y=chart_df['Volume'], name='الحجم',
                    marker_color='rgba(59, 130, 246, 0.3)'
                ), row=2, col=1)

                fig.update_layout(
                    height=500, template="plotly_dark", showlegend=True,
                    margin=dict(l=0, r=0, t=30, b=0),
                    paper_bgcolor='#0a0e17', plot_bgcolor='#111827',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                fig.update_xaxes(rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

                # Signal details
                st.markdown(f'<div class="section-header">📋 تفاصيل {top["symbol"]}</div>', unsafe_allow_html=True)
                for signal in top.get('signals', []):
                    label = SIGNAL_TYPE_LABELS.get(signal['type'], signal['type'])
                    st.markdown(f"""
                    <div style="padding:8px 12px; background:var(--bg-card); border-radius:8px; margin-bottom:4px; border-right:3px solid var(--accent-blue);">
                        <span style="font-weight:600; color:var(--text-primary);">{label}</span>
                        <span style="color:var(--text-secondary); margin-right:8px;">{signal['detail']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("الرسم البياني غير متاح")


# ─── صفحة الجلسات ──────────────────────────────────────────────
def render_sessions(signals, current_session):
    st.markdown('<div class="section-header">⏱ تحليل الجلسات</div>', unsafe_allow_html=True)

    tab_premarket, tab_regular, tab_afterhours, tab_closed = st.tabs([
        "🌅 ما قبل التداول", "📊 الجلسة الرسمية", "🌙 الجلسة المسائية", "📊 ملخص الجلسات"
    ])

    with tab_premarket:
        premarket = [s for s in signals if s.get('session') == 'premarket']
        if premarket:
            st.markdown(f"**{len(premarket)} سهم ببيانات ما قبل التداول**")
            for sig in premarket[:10]:
                vd = sig.get('volume_data', {})
                score = sig.get('whale_score', 0)
                badges_html = ' '.join([get_badge_html(s['type']) for s in sig.get('signals', [])])
                st.markdown(f"""
                <div class="stock-row">
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div class="score-gauge {get_score_class(score)}">{score}</div>
                            <div>
                                <div class="stock-symbol">{sig['symbol']}</div>
                                <div style="margin-top:4px;">{badges_html}</div>
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div class="stock-price">${sig.get('price', 0):.2f}</div>
                            <div class="metric-change {'up' if sig.get('change_5d', 0) > 0 else 'down'}">
                                {sig.get('change_5d', 0):+.1f}% (5 أيام)
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("لا توجد بيانات ما قبل التداول — الماسح يجمع البيانات أثناء الجلسة فقط.")

    with tab_regular:
        regular = [s for s in signals if s.get('session') == 'regular']
        if regular:
            st.markdown(f"**{len(regular)} سهم بالجلسة الرسمية**")
            for sig in regular[:10]:
                vd = sig.get('volume_data', {})
                score = sig.get('whale_score', 0)
                badges_html = ' '.join([get_badge_html(s['type']) for s in sig.get('signals', [])])
                st.markdown(f"""
                <div class="stock-row">
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div class="score-gauge {get_score_class(score)}">{score}</div>
                            <div>
                                <div class="stock-symbol">{sig['symbol']}</div>
                                <div style="margin-top:4px;">{badges_html}</div>
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div class="stock-price">${sig.get('price', 0):.2f}</div>
                            <div class="metric-change {'up' if sig.get('change_5d', 0) > 0 else 'down'}">
                                {sig.get('change_5d', 0):+.1f}% (5 أيام)
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("لا توجد بيانات جلسة رسمية.")

    with tab_afterhours:
        afterhours = [s for s in signals if s.get('session') == 'afterhours']
        if afterhours:
            st.markdown(f"**{len(afterhours)} سهم بالجلسة المسائية**")
            for sig in afterhours[:10]:
                vd = sig.get('volume_data', {})
                score = sig.get('whale_score', 0)
                badges_html = ' '.join([get_badge_html(s['type']) for s in sig.get('signals', [])])
                st.markdown(f"""
                <div class="stock-row">
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div class="score-gauge {get_score_class(score)}">{score}</div>
                            <div>
                                <div class="stock-symbol">{sig['symbol']}</div>
                                <div style="margin-top:4px;">{badges_html}</div>
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div class="stock-price">${sig.get('price', 0):.2f}</div>
                            <div class="metric-change {'up' if sig.get('change_5d', 0) > 0 else 'down'}">
                                {sig.get('change_5d', 0):+.1f}% (5 أيام)
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("لا توجد بيانات جلسة مسائية.")

    with tab_closed:
        st.markdown('<div class="section-header">📊 ملخص الجلسات</div>', unsafe_allow_html=True)

        sessions_data = {}
        for sig in signals:
            sess = sig.get('session', 'unknown')
            if sess not in sessions_data:
                sessions_data[sess] = {'count': 0, 'scores': [], 'symbols': []}
            sessions_data[sess]['count'] += 1
            sessions_data[sess]['scores'].append(sig.get('whale_score', 0))
            sessions_data[sess]['symbols'].append(sig['symbol'])

        session_names = {'premarket': 'ما قبل التداول', 'regular': 'الجلسة الرسمية', 'afterhours': 'الجلسة المسائية'}
        for sess, label in session_names.items():
            if sess in sessions_data:
                d = sessions_data[sess]
                avg_score = sum(d['scores']) / len(d['scores']) if d['scores'] else 0
                st.markdown(f"""
                <div class="metric-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div class="metric-label">{label}</div>
                            <div class="metric-value">{d['count']} سهم</div>
                        </div>
                        <div style="text-align:right;">
                            <div class="metric-label">متوسط الدرجة</div>
                            <div class="metric-value">{avg_score:.0f}/100</div>
                        </div>
                        <div style="text-align:right;">
                            <div class="metric-label">أفضل الأسهم</div>
                            <div style="color:var(--text-primary); font-weight:600;">{', '.join(d['symbols'][:3])}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)


# ─── صفحة الماسح ──────────────────────────────────────────────
def render_scanner(signals):
    st.markdown('<div class="section-header">🔍 فلترة متقدمة</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_grade = st.selectbox("الحد الأدنى للدرجة", ['A+', 'A', 'B+', 'B', 'C', 'D'], index=3)
    with col2:
        min_zscore = st.slider("Z-Score", 0.0, 10.0, 1.5, 0.5)
    with col3:
        max_price = st.number_input("أعلى سعر", value=1000, step=10)
    with col4:
        sort_by = st.selectbox("ترتيب", ["درجة الحوت", "Z-Score", "CMF", "السعر"])

    grade_order = {'A+': 6, 'A': 5, 'B+': 4, 'B': 3, 'C': 2, 'D': 1}
    min_grade_val = grade_order.get(min_grade, 1)

    filter_signal_types = st.multiselect(
        "نوع الإشارة",
        options=list(SIGNAL_TYPE_LABELS.keys()),
        default=list(SIGNAL_TYPE_LABELS.keys()),
        format_func=lambda x: SIGNAL_TYPE_LABELS.get(x, x)
    )

    filtered = []
    for s in signals:
        if s.get('price', 0) > max_price:
            continue
        if s.get('volume_data', {}).get('z_score', 0) < min_zscore:
            continue
        if grade_order.get(s.get('grade', 'D'), 1) < min_grade_val:
            continue
        sig_types = [sig['type'] for sig in s.get('signals', [])]
        if not any(st in filter_signal_types for st in sig_types):
            continue
        filtered.append(s)

    if sort_by == "درجة الحوت":
        filtered.sort(key=lambda x: x.get('whale_score', 0), reverse=True)
    elif sort_by == "Z-Score":
        filtered.sort(key=lambda x: x.get('volume_data', {}).get('z_score', 0), reverse=True)
    elif sort_by == "CMF":
        filtered.sort(key=lambda x: x.get('accumulation', {}).get('cmf', 0), reverse=True)
    elif sort_by == "السعر":
        filtered.sort(key=lambda x: x.get('price', 0))

    st.markdown(f"**{len(filtered)} سهم**")

    # Export
    if filtered:
        export_data = []
        for s in filtered:
            vd = s.get('volume_data', {})
            acc = s.get('accumulation', {})
            export_data.append({
                'الرمز': s['symbol'], 'السعر': round(s.get('price', 0), 2),
                'درجة الحوت': s.get('whale_score', 0), 'الدرجة': s.get('grade', '?'),
                'Z-Score': vd.get('z_score', 0), 'CMF': acc.get('cmf', 0),
                'RSI': s.get('rsi', 50), 'تغيير 5 أيام': f"{s.get('change_5d', 0):+.1f}%",
            })
        csv = pd.DataFrame(export_data).to_csv(index=False, encoding='utf-8-sig')
        st.download_button("📥 تصدير CSV", csv, f"whale_{datetime.now().strftime('%Y%m%d')}.csv")

    for sig in filtered:
        vd = sig.get('volume_data', {})
        score = sig.get('whale_score', 0)
        grade = sig.get('grade', '?')
        sigs = sig.get('signals', [])
        badges_html = ' '.join([get_badge_html(s['type']) for s in sigs])

        with st.expander(f"{sig['symbol']} — ${sig.get('price', 0):.2f} | {score}/100 ({grade}) | {len(sigs)} إشارات"):
            c1, c2 = st.columns([1, 1])
            with c1:
                acc = sig.get('accumulation', {})
                bb = sig.get('bollinger', {})
                st.markdown(f"**الحجم:** Z={vd.get('z_score', 0)} | نسبي={vd.get('relative_volume', 0)}x | يوم={vd.get('today_volume', 0):,}")
                st.markdown(f"**المؤشرات:** CMF={acc.get('cmf', 0)} | OBV={acc.get('obv_trend', '')} | RSI={sig.get('rsi', 50)}")
                st.markdown(f"**Bollinger:** {'انكماش' if bb.get('squeeze') else 'عادي'} | AI={sig.get('anomaly_score', 0)}")
                st.markdown(f"**تغيير 5 أيام:** {sig.get('change_5d', 0):+.1f}%")

                for signal in sigs:
                    st.markdown(f"- {SIGNAL_TYPE_LABELS.get(signal['type'], signal['type'])}: {signal['detail']}")

            with c2:
                chart_df = get_stock_chart(sig['symbol'], period="1mo")
                if chart_df is not None:
                    fig = go.Figure(data=[go.Candlestick(
                        x=chart_df.index, open=chart_df['Open'], high=chart_df['High'],
                        low=chart_df['Low'], close=chart_df['Close']
                    )])
                    fig.update_layout(
                        height=300, template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0),
                        xaxis_rangeslider_visible=False, paper_bgcolor='#0a0e17', plot_bgcolor='#111827',
                    )
                    st.plotly_chart(fig, use_container_width=True)


# ─── صفحة التنبيهات ───────────────────────────────────────────
def render_alerts(signals):
    st.markdown('<div class="section-header">🔔 التنبيهات الفورية</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="alert-panel">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
            <div class="pulse-dot"></div>
            <span style="font-weight:600; color:var(--text-primary);">تنبيهات نشطة</span>
        </div>
    """, unsafe_allow_html=True)

    alerts = []
    for sig in signals:
        score = sig.get('whale_score', 0)
        sigs = sig.get('signals', [])
        sig_types = [s['type'] for s in sigs]

        alert_level = 'critical' if score >= 60 else 'warning' if score >= 30 else 'info'
        alert_color = {'critical': 'var(--accent-red)', 'warning': 'var(--accent-yellow)', 'info': 'var(--accent-blue)'}
        alert_icon = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}

        badges_html = ' '.join([get_badge_html(s['type']) for s in sigs])

        alerts.append(f"""
        <div class="alert-item">
            <div style="font-size:20px;">{alert_icon[alert_level]}</div>
            <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-weight:700; font-size:16px; color:var(--text-primary);">{sig['symbol']}</span>
                    <span style="color:var(--text-secondary);">${sig.get('price', 0):.2f}</span>
                    <span class="badge badge-{'a' if score >= 60 else 'b' if score >= 30 else 'c'}">{score}/100</span>
                </div>
                <div style="margin-top:4px;">{badges_html}</div>
            </div>
            <div style="text-align:right; color:var(--text-muted); font-size:12px;">
                {', '.join(sig_types[:3])}
            </div>
        </div>
        """)

    for a in alerts:
        st.markdown(a, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ─── صفحة التحليلات ───────────────────────────────────────────
def render_analytics(signals):
    st.markdown('<div class="section-header">📈 تحليلات الأداء</div>', unsafe_allow_html=True)

    if not signals:
        st.info("لا توجد بيانات كافية للتحليل.")
        return

    total = len(signals)

    # Distribution
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**توزيع الدرجات**")
        grade_counts = {}
        for s in signals:
            g = s.get('grade', '?')
            grade_counts[g] = grade_counts.get(g, 0) + 1

        fig = go.Figure(data=[go.Pie(
            labels=list(grade_counts.keys()),
            values=list(grade_counts.values()),
            hole=0.6,
            marker=dict(colors=['#10b981', '#68d391', '#3b82f6', '#4299e1', '#f59e0b', '#ef4444']),
            textinfo='label+percent',
            textfont=dict(size=14, color='white'),
        )])
        fig.update_layout(
            height=300, template="plotly_dark", showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor='#0a0e17', plot_bgcolor='#111827',
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("**توزيع الإشارات**")
        signal_counts = {}
        for s in signals:
            for sig in s.get('signals', []):
                t = sig['type']
                signal_counts[t] = signal_counts.get(t, 0) + 1

        fig = go.Figure(data=[go.Bar(
            x=list(signal_counts.values()),
            y=list(signal_counts.keys()),
            orientation='h',
            marker_color='#3b82f6',
        )])
        fig.update_layout(
            height=300, template="plotly_dark",
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor='#0a0e17', plot_bgcolor='#111827',
        )
        st.plotly_chart(fig, use_container_width=True)

    # Score distribution
    st.markdown("**توزيع درجات الحوت**")
    scores = [s.get('whale_score', 0) for s in signals]
    fig = go.Figure(data=[go.Histogram(
        x=scores, nbinsx=20,
        marker_color='#8b5cf6',
    )])
    fig.update_layout(
        height=250, template="plotly_dark",
        xaxis_title="درجة الحوت", yaxis_title="عدد الأسهم",
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='#0a0e17', plot_bgcolor='#111827',
    )
    st.plotly_chart(fig, use_container_width=True)


# ─── صفحة التاريخ ─────────────────────────────────────────────
def render_history():
    st.markdown('<div class="section-header">📋 تاريخ الإشارات والنتائج</div>', unsafe_allow_html=True)

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_history.db")
    if not os.path.exists(db_path):
        st.info("قاعدة البيانات غير موجودة — ستُنشأ بعد أول مسح.")
        return

    try:
        conn = sqlite3.connect(db_path)

        tab1, tab2, tab3 = st.tabs(["📊 آخر الإشارات", "📈 تتبع النتائج", "🧠 التعلم الذاتي"])

        with tab1:
            df = pd.read_sql_query(
                "SELECT scan_time, symbol, score, grade FROM scan_history ORDER BY id DESC LIMIT 200", conn
            )
            if not df.empty:
                st.dataframe(df, use_container_width=True)
            else:
                st.info("لا توجد بيانات بعد.")

        with tab2:
            df2 = pd.read_sql_query(
                "SELECT symbol, scan_time, price_at_scan, price_1d, price_3d, price_5d, change_1d, change_3d, change_5d FROM outcome_tracking WHERE change_1d IS NOT NULL ORDER BY id DESC LIMIT 100", conn
            )
            if not df2.empty:
                st.dataframe(df2, use_container_width=True)
            else:
                st.info("لا توجد نتائج مُتتبّعة بعد — يحتاج وقتاً.")

        with tab3:
            memory_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_memory.json")
            if os.path.exists(memory_path):
                with open(memory_path, 'r', encoding='utf-8') as f:
                    mem = json.load(f)
                lessons = mem.get('lessons', [])
                if lessons:
                    st.markdown(f"**{len(lessons)} درس مُتعلّم**")
                    for l in lessons[-10:]:
                        st.markdown(f"- {l['symbol']}: تغيّر={l.get('actual_change_pct', 0):.1f}% | أسباب={l.get('reason_we_missed', [])}")
                else:
                    st.info("لا توجد درس بعد.")
            else:
                st.info("الذاكرة غير موجودة.")

        conn.close()
    except Exception as e:
        st.error(f"خطأ في قاعدة البيانات: {e}")


# ─── صفحة التنبؤات ────────────────────────────────────────────
def render_predictions():
    st.markdown('<div class="section-header">🔮 تنبؤات الانفجار — الجلسة القادمة</div>', unsafe_allow_html=True)

    # تحميل التنبؤات
    pred_data = None
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'predictions.json'),
        'predictions.json',
    ]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                pred_data = json.load(f)
                if pred_data and pred_data.get('predictions'):
                    break
        except:
            pass

    if not pred_data:
        try:
            url = "https://raw.githubusercontent.com/abdsebvip-byte/whale-scanner/main/predictions.json"
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as resp:
                pred_data = json.loads(resp.read().decode('utf-8'))
        except:
            pass

    if not pred_data or not pred_data.get('predictions'):
        st.markdown("""
        <div class="info-box">
        <b>لا توجد تنبؤات بعد.</b><br>
        الماسح التنبؤي يُشغّل تلقائياً بعد نهاية كل جلسة عبر GitHub Actions.<br>
        أو شغّله يدوياً: <code>python predictive_scanner.py</code>
        </div>
        """, unsafe_allow_html=True)
        return

    predictions = pred_data.get('predictions', [])
    scan_time = pred_data.get('scan_time', '')
    model_trained = pred_data.get('model_trained', False)
    total_analyzed = pred_data.get('total_analyzed', len(predictions))

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="metric-card"><div class="metric-label">مُحلل</div>
        <div class="metric-value">{total_analyzed}</div><div class="metric-change up">{scan_time[:16]}</div></div>""", unsafe_allow_html=True)
    with c2:
        high = len([p for p in predictions if p.get('explosion_probability', 0) >= 50])
        st.markdown(f"""<div class="metric-card"><div class="metric-label">احتمالية عالية</div>
        <div class="metric-value" style="color:#10b981;">{high}</div><div class="metric-change up">50%+</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="metric-card"><div class="metric-label">النموذج</div>
        <div class="metric-value">{'ML' if model_trained else 'قواعد'}</div></div>""", unsafe_allow_html=True)
    with c4:
        avg = sum(p.get('explosion_probability', 0) for p in predictions) / len(predictions) if predictions else 0
        st.markdown(f"""<div class="metric-card"><div class="metric-label">متوسط الاحتمالية</div>
        <div class="metric-value">{avg:.0f}%</div></div>""", unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    for i, p in enumerate(predictions[:20], 1):
        prob = p.get('explosion_probability', 0)
        if prob >= 70:
            badge_cls, badge_text = 'badge-a', 'عالي جداً'
            prob_color = '#10b981'
        elif prob >= 50:
            badge_cls, badge_text = 'badge-b', 'مرتفع'
            prob_color = '#3b82f6'
        elif prob >= 30:
            badge_cls, badge_text = 'badge-c', 'متوسط'
            prob_color = '#f59e0b'
        else:
            badge_cls, badge_text = 'badge-d', 'منخفض'
            prob_color = '#ef4444'

        squeeze = p.get('bollinger_squeeze', False)
        obv = p.get('obv_above_sma', False)
        vr = p.get('volume_ratio', 0)
        cmf = p.get('cmf', 0)
        z = p.get('z_score', 0)

        indicators = []
        if squeeze: indicators.append('🔴 انكماش')
        if obv: indicators.append('📈 OBV صاعد')
        if vr > 2: indicators.append(f'📊 حجم {vr}x')
        if cmf > 0.15: indicators.append('🐋 تجميع')
        if z > 2: indicators.append(f'Z={z}')

        badges_html = ' '.join([f'<span class="badge {badge_cls}" style="margin:2px;">{ind}</span>' for ind in indicators])

        st.markdown(f"""
        <div class="stock-row">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="display:flex;align-items:center;gap:16px;">
                    <div style="min-width:80px;text-align:center;">
                        <div style="font-size:28px;font-weight:800;color:{prob_color};">{prob}%</div>
                        <span class="badge {badge_cls}">{badge_text}</span>
                    </div>
                    <div>
                        <div class="stock-symbol">{p.get('symbol', '')}</div>
                        <div style="margin-top:6px;">{badges_html if badges_html else '<span style="color:var(--text-muted);">—</span>'}</div>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div class="stock-price">${p.get('price', 0):.2f}</div>
                    <div class="stock-change {'up' if p.get('change_1d', 0) > 0 else 'down'}">{p.get('change_1d', 0):+.1f}% اليوم | {p.get('change_5d', 0):+.1f}% 5 أيام</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # تفاصيل سهم
    if predictions:
        selected = st.selectbox("اختر سهم لعرض تفاصيله", [p['symbol'] for p in predictions[:30]])
        if selected:
            p = next((x for x in predictions if x['symbol'] == selected), None)
            if p:
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    st.markdown(f"### {selected}")
                    st.markdown(f"**احتمال الانفجار:** {p.get('explosion_probability', 0)}%")
                    st.markdown(f"**السعر:** ${p.get('price', 0):.2f}")
                    st.markdown(f"**حجم نسبي:** {p.get('volume_ratio', 0)}x")
                    st.markdown(f"**Z-Score:** {p.get('z_score', 0)}")
                    st.markdown(f"**RSI:** {p.get('rsi', 50)}")
                    st.markdown(f"**CMF:** {p.get('cmf', 0)}")
                    st.markdown(f"**Bollinger:** {'انكماش' if p.get('bollinger_squeeze') else 'عادي'}")
                    st.markdown(f"**OBV:** {'صاعد' if p.get('obv_above_sma') else 'هابط'}")
                    st.markdown(f"**MACD:** {p.get('macd_diff', 0)}")
                    st.markdown(f"**ATR:** {p.get('atr_ratio', 0)}")
                    st.markdown(f"**تغيير 1 يوم:** {p.get('change_1d', 0):+.1f}%")
                    st.markdown(f"**تغيير 5 أيام:** {p.get('change_5d', 0):+.1f}%")

                with col_b:
                    chart_df = get_stock_chart(selected)
                    if chart_df is not None:
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03, row_heights=[0.7, 0.3])
                        fig.add_trace(go.Candlestick(
                            x=chart_df.index, open=chart_df['Open'], high=chart_df['High'],
                            low=chart_df['Low'], close=chart_df['Close'], name='السعر'
                        ), row=1, col=1)
                        if len(chart_df) > 20:
                            sma20 = chart_df['Close'].rolling(20).mean()
                            fig.add_trace(go.Scatter(x=chart_df.index, y=sma20, name='SMA 20',
                                line=dict(color='#f59e0b', width=1)), row=1, col=1)
                        fig.add_trace(go.Bar(x=chart_df.index, y=chart_df['Volume'], name='الحجم',
                            marker_color='rgba(59,130,246,0.3)'), row=2, col=1)
                        fig.update_layout(height=450, template="plotly_dark",
                            margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False,
                            paper_bgcolor='#0a0e17', plot_bgcolor='#111827')
                        st.plotly_chart(fig, use_container_width=True)


# ─── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
