"""
Whale Scanner v6.0 — Professional Trading Dashboard
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

st.set_page_config(page_title="Whale Scanner", page_icon=" whale", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

* { font-family: 'Inter', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #111827 50%, #0d1b2a 100%) !important;
}
[data-testid="stSidebar"] {
    background: #0f1729 !important;
    border-right: 1px solid #1e293b !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdown"] h3 {
    color: #60a5fa !important;
    font-size: 13px !important;
    text-transform: uppercase !important;
    letter-spacing: 2px !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] button {
    background: #1e293b !important;
    color: #94a3b8 !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] button:hover {
    background: #334155 !important;
    color: #e2e8f0 !important;
    border-color: #60a5fa !important;
}

/* Cards */
.metric-card {
    background: linear-gradient(145deg, #111827 0%, #1a1f35 100%);
    border: 1px solid #1e293b;
    border-radius: 16px;
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6);
}
.metric-card.green::before { background: linear-gradient(90deg, #10b981, #34d399); }
.metric-card.yellow::before { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.metric-card.red::before { background: linear-gradient(90deg, #ef4444, #f87171); }
.metric-card.purple::before { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }

.metric-label {
    font-size: 11px; font-weight: 600; color: #64748b;
    text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 8px;
}
.metric-value {
    font-size: 32px; font-weight: 800; color: #f1f5f9;
    line-height: 1;
}
.metric-sub {
    font-size: 13px; font-weight: 600; margin-top: 6px;
}

/* Section Header */
.section-title {
    font-size: 14px; font-weight: 700; color: #64748b;
    text-transform: uppercase; letter-spacing: 2px;
    padding: 8px 0; border-bottom: 1px solid #1e293b;
    margin: 24px 0 16px 0;
}

/* Prediction Row */
.pred-card {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 8px;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.pred-card:hover {
    border-color: #3b82f6;
    box-shadow: 0 0 20px rgba(59,130,246,0.1);
}
.pred-card .left { display: flex; align-items: center; gap: 20px; }
.pred-card .prob {
    font-size: 28px; font-weight: 800;
    min-width: 80px; text-align: center;
    font-family: 'Inter', monospace;
}
.pred-card .info .sym { font-size: 18px; font-weight: 700; color: #f1f5f9; }
.pred-card .info .price { font-size: 14px; color: #94a3b8; margin-top: 2px; }
.pred-card .tags { display: flex; gap: 6px; flex-wrap: wrap; }
.pred-card .tag {
    padding: 3px 10px; border-radius: 6px;
    font-size: 11px; font-weight: 600;
    background: #1e293b; color: #94a3b8;
    border: 1px solid #334155;
}
.pred-card .tag.g { background: rgba(16,185,129,0.1); color: #34d399; border-color: rgba(16,185,129,0.3); }
.pred-card .tag.b { background: rgba(59,130,246,0.1); color: #60a5fa; border-color: rgba(59,130,246,0.3); }
.pred-card .tag.o { background: rgba(249,115,22,0.1); color: #fb923c; border-color: rgba(249,115,22,0.3); }
.pred-card .change {
    font-size: 16px; font-weight: 700; min-width: 80px; text-align: right;
}

/* Session Cards */
.sess-card {
    background: #111827; border: 1px solid #1e293b;
    border-radius: 16px; padding: 24px; text-align: center;
    transition: all 0.2s; height: 180px;
}
.sess-card.active {
    border-color: #3b82f6;
    background: linear-gradient(145deg, #111827 0%, #0f1d35 100%);
    box-shadow: 0 4px 30px rgba(59,130,246,0.15);
}
.sess-card .icon { font-size: 32px; margin-bottom: 8px; }
.sess-card .name { font-size: 18px; font-weight: 700; color: #f1f5f9; }
.sess-card .hours { font-size: 13px; color: #64748b; margin-top: 4px; }
.sess-card .status { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; }
.sess-card .status.live { color: #34d399; }
.sess-card .status.off { color: #475569; }
.sess-card .remaining { font-size: 13px; color: #60a5fa; margin-top: 4px; }

/* Alert rows */
.alert-critical { border-left: 4px solid #ef4444; }
.alert-warning { border-left: 4px solid #f59e0b; }
.alert-info { border-left: 4px solid #3b82f6; }

/* Header */
.dash-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0 0 20px 0;
    border-bottom: 1px solid #1e293b; margin-bottom: 20px;
}
.dash-header h1 { font-size: 24px; font-weight: 800; color: #f1f5f9; margin: 0; }
.dash-header .meta { font-size: 12px; color: #64748b; }

/* Table overrides */
.stDataFrame { border-radius: 12px !important; border: 1px solid #1e293b !important; overflow: hidden !important; }
</style>
""", unsafe_allow_html=True)


def load_predictions():
    for p in ['predictions.json']:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if d and d.get('predictions'):
                    return d
        except:
            pass
    return {}


@st.cache_data(ttl=300)
def get_chart(sym):
    try:
        df = yf.download(sym, period="3mo", progress=False)
        if df is None or len(df) == 0:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None


def get_session():
    import pytz
    try:
        et = pytz.timezone('US/Eastern')
    except:
        et = timezone(timedelta(hours=-4))
    now = datetime.now(et)
    t = now.hour * 60 + now.minute
    if 240 <= t < 570: return "premarket", "Pre-Market"
    elif 570 <= t < 960: return "regular", "Regular"
    elif 960 <= t < 1200: return "afterhours", "After-Hours"
    else: return "closed", "Market Closed"


def build_df(preds):
    rows = []
    for p in preds:
        sigs = []
        if p.get('bollinger_squeeze'): sigs.append("Squeeze")
        if p.get('obv_above_sma'): sigs.append("OBV Up")
        if p.get('cmf', 0) > 0.15: sigs.append("Accum")
        if p.get('volume_ratio', 0) > 2: sigs.append("Vol Spike")
        rows.append({
            'Symbol': p.get('symbol', ''),
            'Price': p.get('price', 0),
            'Probability %': p.get('explosion_probability', 0),
            'Vol Ratio': p.get('volume_ratio', 0),
            'Z-Score': p.get('z_score', 0),
            'RSI': p.get('rsi', 50),
            'CMF': p.get('cmf', 0),
            '1D %': p.get('change_1d', 0),
            '5D %': p.get('change_5d', 0),
            'Squeeze': 'Yes' if p.get('bollinger_squeeze') else '',
            'OBV': 'Up' if p.get('obv_above_sma') else '',
            'Signals': ', '.join(sigs) if sigs else '-',
        })
    return pd.DataFrame(rows)


def pred_row_html(p, index=""):
    prob = p.get('explosion_probability', 0)
    if prob >= 60: pc = "#34d399"
    elif prob >= 40: pc = "#60a5fa"
    elif prob >= 25: pc = "#fbbf24"
    else: pc = "#64748b"

    chg = p.get('change_1d', 0)
    if chg > 0: cc, arrow = "#34d399", "+"
    elif chg < 0: cc, arrow = "#f87171", ""
    else: cc, arrow = "#94a3b8", ""

    tags = ""
    if p.get('bollinger_squeeze'): tags += '<span class="tag b">Squeeze</span>'
    if p.get('obv_above_sma'): tags += '<span class="tag g">OBV Up</span>'
    if p.get('cmf', 0) > 0.15: tags += '<span class="tag g">Accumulation</span>'
    if p.get('volume_ratio', 0) > 2: tags += '<span class="tag o">Vol {0:.1f}x</span>'.format(p['volume_ratio'])
    if not tags: tags = '<span class="tag">-</span>'

    return f"""<div class="pred-card">
        <div class="left">
            <div class="prob" style="color:{pc};">{prob}%</div>
            <div class="info">
                <div class="sym">{p.get('symbol','')}</div>
                <div class="price">${p.get('price',0):.2f}</div>
            </div>
            <div class="tags">{tags}</div>
        </div>
        <div class="change" style="color:{cc};">{arrow}{chg:.1f}% 1D</div>
    </div>"""


def page_overview(preds, data, session_name):
    high = len([p for p in preds if p.get('explosion_probability', 0) >= 50])
    critical = len([p for p in preds if p.get('explosion_probability', 0) >= 60])
    scan_time = data.get('scan_time', '')

    st.markdown(f"""<div class="dash-header">
        <div><h1>Overview</h1><div class="meta">Scan: {scan_time[:16] if scan_time else 'N/A'} | Session: {session_name} | Model: {'ML' if data.get('model_trained') else 'Rules'}</div></div>
    </div>""", unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Analyzed</div><div class="metric-value">{data.get("total_analyzed",0)}</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Predictions</div><div class="metric-value">{len(preds)}</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="metric-card green"><div class="metric-label">High 50%+</div><div class="metric-value" style="color:#34d399;">{high}</div></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="metric-card yellow"><div class="metric-label">Critical 60%+</div><div class="metric-value" style="color:#fbbf24;">{critical}</div></div>', unsafe_allow_html=True)

    if not preds:
        st.warning("No predictions yet.")
        return

    st.markdown('<div class="section-title">Top Predictions - Next Session</div>', unsafe_allow_html=True)

    html = ""
    for p in preds[:10]:
        html += pred_row_html(p)
    st.markdown(html, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Probability Distribution</div>', unsafe_allow_html=True)
    probs = [p.get('explosion_probability', 0) for p in preds]
    fig = go.Figure(data=[go.Histogram(x=probs, nbinsx=12, marker_color='#3b82f6', marker_line=dict(width=1, color='#1e293b'))])
    fig.update_layout(height=250, template="plotly_dark", margin=dict(l=40,r=10,t=10,b=40),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#111827', xaxis=dict(gridcolor='#1e293b', title="Probability %"), yaxis=dict(gridcolor='#1e293b'))
    st.plotly_chart(fig, use_container_width=True)


def page_all_preds(preds):
    st.markdown(f"""<div class="dash-header">
        <div><h1>All Predictions</h1><div class="meta">{len(preds)} stocks ranked by explosion probability</div></div>
    </div>""", unsafe_allow_html=True)

    if not preds:
        st.warning("No predictions.")
        return

    df = build_df(preds)
    st.dataframe(df, column_config={
        'Probability %': st.column_config.ProgressColumn('Probability %', min_value=0, max_value=100, format="%d%%"),
        'Price': st.column_config.NumberColumn('Price', format="$%.2f"),
        'Vol Ratio': st.column_config.NumberColumn('Vol Ratio', format="%.1fx"),
        'Z-Score': st.column_config.NumberColumn('Z-Score', format="%.2f"),
        'RSI': st.column_config.NumberColumn('RSI', format="%.0f"),
        'CMF': st.column_config.NumberColumn('CMF', format="%.3f"),
        '1D %': st.column_config.NumberColumn('1D %', format="%+.1f%%"),
        '5D %': st.column_config.NumberColumn('5D %', format="%+.1f%%"),
    }, use_container_width=True, height=500, hide_index=True)

    st.markdown('<div class="section-title">Stock Chart</div>', unsafe_allow_html=True)
    syms = [p['symbol'] for p in preds]
    selected = st.selectbox("Select stock", syms)
    if selected:
        p = next((x for x in preds if x['symbol'] == selected), None)
        chart = get_chart(selected)
        if chart is not None and p:
            col_a, col_b = st.columns([1, 2])
            with col_a:
                prob = p.get('explosion_probability', 0)
                pc = "#34d399" if prob >= 60 else "#60a5fa" if prob >= 40 else "#fbbf24"
                st.markdown(f"""<div class="metric-card" style="border-left:3px solid {pc};">
                    <div class="metric-label">Explosion Probability</div>
                    <div class="metric-value" style="color:{pc};font-size:40px;">{prob}%</div>
                    <div style="margin-top:16px;font-size:13px;color:#94a3b8;line-height:2.2;">
                        Price: <b style="color:#f1f5f9;">${p.get('price',0):.2f}</b><br>
                        Volume: <b style="color:#f1f5f9;">{p.get('volume_ratio',0):.1f}x</b> avg<br>
                        RSI: <b style="color:#f1f5f9;">{p.get('rsi',0):.0f}</b><br>
                        CMF: <b style="color:#f1f5f9;">{p.get('cmf',0):.3f}</b><br>
                        Squeeze: <b style="color:#f1f5f9;">{'Yes' if p.get('bollinger_squeeze') else 'No'}</b><br>
                        OBV: <b style="color:#f1f5f9;">{'Above' if p.get('obv_above_sma') else 'Below'}</b>
                    </div>
                </div>""", unsafe_allow_html=True)
            with col_b:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=chart.index, open=chart['Open'], high=chart['High'],
                    low=chart['Low'], close=chart['Close'], name='Price',
                    increasing_line_color='#34d399', decreasing_line_color='#f87171'), row=1, col=1)
                if len(chart) > 20:
                    sma20 = chart['Close'].rolling(20).mean()
                    fig.add_trace(go.Scatter(x=chart.index, y=sma20, name='SMA 20',
                        line=dict(color='#f59e0b', width=1, dash='dot')), row=1, col=1)
                fig.add_trace(go.Bar(x=chart.index, y=chart['Volume'], name='Volume',
                    marker_color='rgba(59,130,246,0.25)'), row=2, col=1)
                fig.update_layout(height=450, template="plotly_dark", margin=dict(l=0,r=0,t=10,b=0),
                    xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#111822',
                    font=dict(family="Inter", color="#94a3b8"))
                fig.update_xaxes(gridcolor='#1e293b')
                fig.update_yaxes(gridcolor='#1e293b')
                st.plotly_chart(fig, use_container_width=True)


def page_sessions(preds, data):
    import pytz
    try:
        et = pytz.timezone('US/Eastern')
    except:
        et = timezone(timedelta(hours=-4))
    now = datetime.now(et)
    current_min = now.hour * 60 + now.minute
    code_now, name_now = get_session()
    scan_time = data.get('scan_time', '')
    pred_session = data.get('session_name', '')

    st.markdown(f"""<div class="dash-header">
        <div><h1>Market Sessions</h1><div class="meta">Eastern Time: {now.strftime('%I:%M %p')} | Current: {name_now}</div></div>
    </div>""", unsafe_allow_html=True)

    sessions = [
        {"name": "Pre-Market", "ar": "ما قبل التداول", "hours": "4:00 AM - 9:30 AM ET", "start": 240, "end": 570, "code": "premarket", "icon": "🌅"},
        {"name": "Regular", "ar": "الجلسة الرسمية", "hours": "9:30 AM - 4:00 PM ET", "start": 570, "end": 960, "code": "regular", "icon": "📊"},
        {"name": "After-Hours", "ar": "الجلسة المسائية", "hours": "4:00 PM - 8:00 PM ET", "start": 960, "end": 1200, "code": "afterhours", "icon": "🌙"},
    ]

    sess_html = '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;">'
    for sess in sessions:
        is_active = sess['code'] == code_now
        active_class = "active" if is_active else ""
        status_class = "live" if is_active else "off"

        if is_active:
            remaining = sess['end'] - current_min
            status_text = f'<div class="status live">● LIVE</div><div class="remaining">{remaining//60}h {remaining%60}m remaining</div>'
        else:
            if current_min < sess['start']:
                to_go = sess['start'] - current_min
                status_text = f'<div class="status off">Starts in {to_go//60}h {to_go%60}m</div>'
            else:
                status_text = '<div class="status off">Closed</div>'

        sess_html += f"""<div class="sess-card {active_class}">
            <div class="icon">{sess['icon']}</div>
            <div class="name">{sess['name']}</div>
            <div style="font-size:13px;color:#64748b;">{sess['ar']}</div>
            <div class="hours">{sess['hours']}</div>
            {status_text}
        </div>"""
    sess_html += '</div>'
    st.markdown(sess_html, unsafe_allow_html=True)

    st.markdown(f'<div class="section-title">Last Scan — {pred_session} — {scan_time[:16] if scan_time else "—"}</div>', unsafe_allow_html=True)

    if not preds:
        st.info("No scan data.")
        return

    html = ""
    for p in preds[:15]:
        html += pred_row_html(p)
    st.markdown(html, unsafe_allow_html=True)


def page_scanner(preds):
    st.markdown(f"""<div class="dash-header">
        <div><h1>Scanner & Filters</h1><div class="meta">Filter and sort predictions</div></div>
    </div>""", unsafe_allow_html=True)

    if not preds:
        st.info("No data.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        min_prob = st.slider("Min Probability %", 0, 100, 20, 5)
    with c2:
        max_price = st.number_input("Max Price $", value=500, step=50)
    with c3:
        sort_by = st.selectbox("Sort By", ["Probability %", "Vol Ratio", "Price", "Z-Score"])

    sort_map = {"Probability %": "explosion_probability", "Vol Ratio": "volume_ratio", "Price": "price", "Z-Score": "z_score"}
    filtered = [p for p in preds if p.get('explosion_probability', 0) >= min_prob and p.get('price', 0) <= max_price]
    filtered.sort(key=lambda x: x.get(sort_map[sort_by], 0), reverse=True)

    st.markdown(f'<div class="section-title">{len(filtered)} Results</div>', unsafe_allow_html=True)

    df = build_df(filtered)
    st.dataframe(df, column_config={
        'Probability %': st.column_config.ProgressColumn('Probability %', min_value=0, max_value=100, format="%d%%"),
        'Price': st.column_config.NumberColumn('Price', format="$%.2f"),
        'Vol Ratio': st.column_config.NumberColumn('Vol Ratio', format="%.1fx"),
        'Z-Score': st.column_config.NumberColumn('Z-Score', format="%.2f"),
        'RSI': st.column_config.NumberColumn('RSI', format="%.0f"),
        'CMF': st.column_config.NumberColumn('CMF', format="%.3f"),
        '1D %': st.column_config.NumberColumn('1D %', format="%+.1f%%"),
        '5D %': st.column_config.NumberColumn('5D %', format="%+.1f%%"),
    }, use_container_width=True, height=500, hide_index=True)

    if filtered:
        csv = df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("Download CSV", csv, "predictions.csv")


def page_alerts(preds):
    st.markdown(f"""<div class="dash-header">
        <div><h1>Alerts</h1><div class="meta">Stocks ranked by urgency</div></div>
    </div>""", unsafe_allow_html=True)

    if not preds:
        st.info("No alerts.")
        return

    critical = [p for p in preds if p.get('explosion_probability', 0) >= 60]
    warning = [p for p in preds if 40 <= p.get('explosion_probability', 0) < 60]
    watchlist = [p for p in preds if 25 <= p.get('explosion_probability', 0) < 40]

    if critical:
        st.markdown(f'<div class="section-title" style="color:#ef4444;">Critical — {len(critical)} stocks (60%+)</div>', unsafe_allow_html=True)
        html = ""
        for p in critical:
            prob = p['explosion_probability']
            chg = p.get('change_1d', 0)
            cc = "#34d399" if chg > 0 else "#f87171" if chg < 0 else "#94a3b8"
            arrow = "+" if chg > 0 else ""
            tags = ""
            if p.get('bollinger_squeeze'): tags += '<span class="tag b">Squeeze</span>'
            if p.get('obv_above_sma'): tags += '<span class="tag g">OBV</span>'
            if p.get('cmf', 0) > 0.15: tags += '<span class="tag g">Accum</span>'
            html += f"""<div class="pred-card alert-critical">
                <div class="left">
                    <div class="prob" style="color:#ef4444;">{prob}%</div>
                    <div class="info"><div class="sym">{p['symbol']}</div><div class="price">${p['price']:.2f}</div></div>
                    <div class="tags">{tags}</div>
                </div>
                <div class="change" style="color:{cc};">{arrow}{chg:.1f}%</div>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)

    if warning:
        st.markdown(f'<div class="section-title" style="color:#f59e0b;">Warning — {len(warning)} stocks (40-60%)</div>', unsafe_allow_html=True)
        html = ""
        for p in warning:
            prob = p['explosion_probability']
            chg = p.get('change_1d', 0)
            cc = "#34d399" if chg > 0 else "#f87171" if chg < 0 else "#94a3b8"
            html += f"""<div class="pred-card alert-warning">
                <div class="left">
                    <div class="prob" style="color:#f59e0b;">{prob}%</div>
                    <div class="info"><div class="sym">{p['symbol']}</div><div class="price">${p['price']:.2f}</div></div>
                </div>
                <div class="change" style="color:{cc};">{chg:+.1f}%</div>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)

    if watchlist:
        st.markdown(f'<div class="section-title">Watchlist — {len(watchlist)} stocks (25-40%)</div>', unsafe_allow_html=True)
        html = ""
        for p in watchlist[:10]:
            prob = p['explosion_probability']
            chg = p.get('change_1d', 0)
            cc = "#34d399" if chg > 0 else "#f87171" if chg < 0 else "#94a3b8"
            html += f"""<div class="pred-card alert-info">
                <div class="left">
                    <div class="prob" style="color:#3b82f6;">{prob}%</div>
                    <div class="info"><div class="sym">{p['symbol']}</div><div class="price">${p['price']:.2f}</div></div>
                </div>
                <div class="change" style="color:{cc};">{chg:+.1f}%</div>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)


def page_analytics(preds):
    st.markdown(f"""<div class="dash-header">
        <div><h1>Analytics</h1><div class="meta">Distribution and correlation analysis</div></div>
    </div>""", unsafe_allow_html=True)

    if not preds:
        st.info("No data.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-title">Probability Distribution</div>', unsafe_allow_html=True)
        probs = [p.get('explosion_probability', 0) for p in preds]
        fig = go.Figure(data=[go.Histogram(x=probs, nbinsx=12, marker_color='#3b82f6', marker_line=dict(width=1, color='#1e293b'))])
        fig.update_layout(height=300, template="plotly_dark", margin=dict(l=40,r=10,t=10,b=40),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#111827', xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b'))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown('<div class="section-title">Volume vs Probability</div>', unsafe_allow_html=True)
        fig = go.Figure(data=[go.Scatter(
            x=[p.get('volume_ratio', 0) for p in preds], y=[p.get('explosion_probability', 0) for p in preds],
            text=[p.get('symbol', '') for p in preds], mode='markers+text', textposition='top center',
            textfont=dict(size=10, color='#94a3b8'),
            marker=dict(color=[p.get('explosion_probability', 0) for p in preds],
            colorscale=[[0,'#1e293b'],[0.3,'#f59e0b'],[0.6,'#3b82f6'],[1,'#10b981']], size=10))])
        fig.update_layout(height=300, template="plotly_dark", margin=dict(l=40,r=10,t=10,b=40),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#111827', xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b'))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">Top 10 by Volume Ratio</div>', unsafe_allow_html=True)
    top_vol = sorted(preds, key=lambda x: x.get('volume_ratio', 0), reverse=True)[:10]
    fig = go.Figure(data=[go.Bar(y=[p.get('symbol','') for p in top_vol], x=[p.get('volume_ratio',0) for p in top_vol],
        orientation='h', marker_color='#8b5cf6', marker_line=dict(width=0))])
    fig.update_layout(height=350, template="plotly_dark", margin=dict(l=80,r=10,t=10,b=40),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#111827', xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b'))
    st.plotly_chart(fig, use_container_width=True)


def page_history():
    st.markdown(f"""<div class="dash-header">
        <div><h1>Scan History</h1><div class="meta">Previous scan results from database</div></div>
    </div>""", unsafe_allow_html=True)

    db_path = "scanner_history.db"
    if not os.path.exists(db_path):
        st.info("No database yet. Created after first scan.")
        return
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            "SELECT scan_time as Time, symbol as Symbol, price as Price, volume_ratio as Vol, rsi as RSI, round(cmf,3) as CMF, change_pct as Change FROM session_data ORDER BY id DESC LIMIT 200", conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=500, hide_index=True)
        else:
            st.info("No history yet.")
    except Exception as e:
        st.error(f"Error: {e}")


def main():
    data = load_predictions()
    preds = data.get('predictions', [])
    code_now, session_name = get_session()
    is_live = code_now != "closed"

    with st.sidebar:
        st.markdown("### Whale Scanner")
        if is_live:
            st.success(f"● {session_name} — LIVE")
        else:
            st.info(f"● {session_name}")
        st.caption(f"Scan: {data.get('scan_time', 'N/A')[:16]}")
        st.caption(f"Analyzed: {data.get('total_analyzed', 0)}")
        st.markdown("---")

        if "page" not in st.session_state:
            st.session_state.page = "Overview"

        pages = ["Overview", "All Predictions", "Sessions", "Scanner", "Alerts", "Analytics", "History"]
        for p_name in pages:
            if st.button(p_name, key=f"nav_{p_name}", use_container_width=True):
                st.session_state.page = p_name

    page = st.session_state.page

    if page == "Overview": page_overview(preds, data, session_name)
    elif page == "All Predictions": page_all_preds(preds)
    elif page == "Sessions": page_sessions(preds, data)
    elif page == "Scanner": page_scanner(preds)
    elif page == "Alerts": page_alerts(preds)
    elif page == "Analytics": page_analytics(preds)
    elif page == "History": page_history()


if __name__ == "__main__":
    main()
