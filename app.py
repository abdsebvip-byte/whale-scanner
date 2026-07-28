"""
Whale Scanner v6.0
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
.stApp { background-color: #0d1117; }
[data-testid="stSidebar"] { background-color: #161b22; }
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
    if 240 <= t < 570:
        return "premarket", "Pre-Market"
    elif 570 <= t < 960:
        return "regular", "Regular"
    elif 960 <= t < 1200:
        return "afterhours", "After-Hours"
    else:
        return "closed", "Market Closed"


def build_df(preds):
    rows = []
    for p in preds:
        signals = []
        if p.get('bollinger_squeeze'): signals.append("Squeeze")
        if p.get('obv_above_sma'): signals.append("OBV Up")
        if p.get('cmf', 0) > 0.15: signals.append("Accum")
        if p.get('volume_ratio', 0) > 2: signals.append("Vol Spike")
        rows.append({
            'Symbol': p.get('symbol', ''),
            'Price': p.get('price', 0),
            'Probability %': p.get('explosion_probability', 0),
            'Vol Ratio': p.get('volume_ratio', 0),
            'Z-Score': p.get('z_score', 0),
            'RSI': p.get('rsi', 50),
            'CMF': p.get('cmf', 0),
            '1D Change %': p.get('change_1d', 0),
            '5D Change %': p.get('change_5d', 0),
            'Squeeze': 'Yes' if p.get('bollinger_squeeze') else '',
            'OBV': 'Up' if p.get('obv_above_sma') else '',
            'Signals': ', '.join(signals) if signals else '-',
        })
    return pd.DataFrame(rows)


def main():
    data = load_predictions()
    preds = data.get('predictions', [])
    code_now, session_name = get_session()
    scan_time = data.get('scan_time', '')
    total_analyzed = data.get('total_analyzed', 0)

    is_live = code_now != "closed"

    st.sidebar.markdown("## Whale Scanner")
    if is_live:
        st.sidebar.success(f"● {session_name} - LIVE")
    else:
        st.sidebar.info(f"● {session_name}")
    st.sidebar.caption(f"Scan: {scan_time[:16] if scan_time else 'N/A'}")
    st.sidebar.caption(f"Analyzed: {total_analyzed} stocks")

    st.sidebar.markdown("---")
    pages = ["Overview", "All Predictions", "Sessions", "Scanner", "Alerts", "Analytics", "History"]
    if "page" not in st.session_state:
        st.session_state.page = "Overview"

    for p_name in pages:
        if st.sidebar.button(p_name, key=f"btn_{p_name}", use_container_width=True):
            st.session_state.page = p_name

    page = st.session_state.page

    if page == "Overview":
        page_overview(preds, data, session_name)
    elif page == "All Predictions":
        page_all_preds(preds)
    elif page == "Sessions":
        page_sessions(preds, data)
    elif page == "Scanner":
        page_scanner(preds)
    elif page == "Alerts":
        page_alerts(preds)
    elif page == "Analytics":
        page_analytics(preds)
    elif page == "History":
        page_history()


def page_overview(preds, data, session_name):
    st.title("Overview")

    high = len([p for p in preds if p.get('explosion_probability', 0) >= 50])
    critical = len([p for p in preds if p.get('explosion_probability', 0) >= 60])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Analyzed", data.get('total_analyzed', 0))
    c2.metric("Predictions", len(preds))
    c3.metric("High (50%+)", high)
    c4.metric("Critical (60%+)", critical)

    st.markdown("---")
    st.subheader("Top Predictions - Next Session")

    if not preds:
        st.warning("No predictions. Run the scanner.")
        return

    for p in preds[:10]:
        prob = p.get('explosion_probability', 0)
        chg = p.get('change_1d', 0)

        col1, col2, col3 = st.columns([1, 3, 1])
        with col1:
            color = "green" if prob >= 60 else "blue" if prob >= 40 else "orange"
            st.metric(p.get('symbol', ''), f"{prob}%", f"{chg:+.1f}% 1D")
        with col2:
            tags = []
            if p.get('bollinger_squeeze'): tags.append("Squeeze")
            if p.get('obv_above_sma'): tags.append("OBV Up")
            if p.get('cmf', 0) > 0.15: tags.append("Accumulation")
            if p.get('volume_ratio', 0) > 2: tags.append(f"Vol {p['volume_ratio']:.1f}x")
            st.write(" | ".join(tags) if tags else "-")
        with col3:
            st.write(f"${p.get('price', 0):.2f}")


def page_all_preds(preds):
    st.title("All Predictions")

    if not preds:
        st.warning("No predictions available.")
        return

    df = build_df(preds)

    st.dataframe(
        df,
        column_config={
            'Probability %': st.column_config.ProgressColumn('Probability %', min_value=0, max_value=100, format="%d%%"),
            'Price': st.column_config.NumberColumn('Price', format="$%.2f"),
            'Vol Ratio': st.column_config.NumberColumn('Vol Ratio', format="%.1fx"),
            'Z-Score': st.column_config.NumberColumn('Z-Score', format="%.2f"),
            'RSI': st.column_config.NumberColumn('RSI', format="%.0f"),
            'CMF': st.column_config.NumberColumn('CMF', format="%.3f"),
            '1D Change %': st.column_config.NumberColumn('1D Change %', format="%+.1f%%"),
            '5D Change %': st.column_config.NumberColumn('5D Change %', format="%+.1f%%"),
        },
        use_container_width=True,
        height=500,
        hide_index=True,
    )

    st.markdown("---")
    st.subheader("Chart")

    syms = [p['symbol'] for p in preds]
    selected = st.selectbox("Select stock", syms)
    if selected:
        p = next((x for x in preds if x['symbol'] == selected), None)
        chart = get_chart(selected)
        if chart is not None and p:
            col_a, col_b = st.columns([1, 2])
            with col_a:
                st.write(f"**{p['symbol']}** - ${p['price']:.2f}")
                st.write(f"Probability: **{p['explosion_probability']}%**")
                st.write(f"Volume: {p['volume_ratio']:.1f}x average")
                st.write(f"RSI: {p['rsi']:.0f}")
                st.write(f"CMF: {p['cmf']:.3f}")
                st.write(f"Squeeze: {'Yes' if p.get('bollinger_squeeze') else 'No'}")
                st.write(f"OBV: {'Above SMA' if p.get('obv_above_sma') else 'Below'}")
            with col_b:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=chart.index, open=chart['Open'], high=chart['High'],
                    low=chart['Low'], close=chart['Close'], name='Price'), row=1, col=1)
                if len(chart) > 20:
                    sma20 = chart['Close'].rolling(20).mean()
                    fig.add_trace(go.Scatter(x=chart.index, y=sma20, name='SMA 20',
                        line=dict(color='orange', width=1)), row=1, col=1)
                fig.add_trace(go.Bar(x=chart.index, y=chart['Volume'], name='Volume',
                    marker_color='rgba(88,166,255,0.3)'), row=2, col=1)
                fig.update_layout(height=450, template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0),
                    xaxis_rangeslider_visible=False, paper_bgcolor='#0d1117', plot_bgcolor='#161b22')
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

    st.title("Market Sessions")
    st.info(f"Eastern Time: {now.strftime('%I:%M %p')} | Current Session: {name_now}")

    sessions = [
        {"name": "Pre-Market", "hours": "4:00 AM - 9:30 AM ET", "start": 240, "end": 570, "code": "premarket", "icon": "sunrise"},
        {"name": "Regular", "hours": "9:30 AM - 4:00 PM ET", "start": 570, "end": 960, "code": "regular", "icon": "chart"},
        {"name": "After-Hours", "hours": "4:00 PM - 8:00 PM ET", "start": 960, "end": 1200, "code": "afterhours", "icon": "moon"},
    ]

    cols = st.columns(3)
    for i, (col, sess) in enumerate(zip(cols, sessions)):
        with col:
            is_active = sess['code'] == code_now
            if is_active:
                remaining = sess['end'] - current_min
                st.success(f"**{sess['name']}** - LIVE ({remaining//60}h {remaining%60}m left)\n\n{sess['hours']}")
            else:
                if current_min < sess['start']:
                    to_go = sess['start'] - current_min
                    st.info(f"**{sess['name']}** - Starts in {to_go//60}h {to_go%60}m\n\n{sess['hours']}")
                else:
                    st.warning(f"**{sess['name']}** - Closed\n\n{sess['hours']}")

    st.markdown("---")
    st.subheader(f"Last Scan Results ({data.get('session_name', 'N/A')})")

    if not preds:
        st.info("No scan data.")
        return

    df = build_df(preds)
    st.dataframe(df, use_container_width=True, height=400, hide_index=True)


def page_scanner(preds):
    st.title("Scanner & Filters")

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

    st.write(f"**{len(filtered)} results**")

    if filtered:
        df = build_df(filtered)
        st.dataframe(df, use_container_width=True, height=500, hide_index=True)

        csv = df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("Download CSV", csv, "predictions.csv")


def page_alerts(preds):
    st.title("Alerts")

    if not preds:
        st.info("No alerts.")
        return

    critical = [p for p in preds if p.get('explosion_probability', 0) >= 60]
    warning = [p for p in preds if 40 <= p.get('explosion_probability', 0) < 60]
    watchlist = [p for p in preds if 25 <= p.get('explosion_probability', 0) < 40]

    if critical:
        st.error(f"**Critical ({len(critical)} stocks) - 60%+**")
        for p in critical:
            st.write(f"**{p['symbol']}** - {p['explosion_probability']}% - ${p['price']:.2f} | Vol {p['volume_ratio']:.1f}x | RSI {p['rsi']:.0f}")

    if warning:
        st.warning(f"**Warning ({len(warning)} stocks) - 40-60%**")
        for p in warning:
            st.write(f"**{p['symbol']}** - {p['explosion_probability']}% - ${p['price']:.2f}")

    if watchlist:
        st.info(f"**Watchlist ({len(watchlist)} stocks) - 25-40%**")
        for p in watchlist[:10]:
            st.write(f"{p['symbol']} - {p['explosion_probability']}% - ${p['price']:.2f}")


def page_analytics(preds):
    st.title("Analytics")

    if not preds:
        st.info("No data.")
        return

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Probability Distribution")
        probs = [p.get('explosion_probability', 0) for p in preds]
        fig = go.Figure(data=[go.Histogram(x=probs, nbinsx=15, marker_color='#58a6ff')])
        fig.update_layout(height=300, template="plotly_dark", margin=dict(l=40, r=10, t=10, b=40),
            paper_bgcolor='#0d1117', plot_bgcolor='#161b22')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Volume vs Probability")
        fig = go.Figure(data=[go.Scatter(
            x=[p.get('volume_ratio', 0) for p in preds],
            y=[p.get('explosion_probability', 0) for p in preds],
            text=[p.get('symbol', '') for p in preds],
            mode='markers+text', textposition='top center',
            marker=dict(color=[p.get('explosion_probability', 0) for p in preds],
            colorscale='RdYlGn', size=10))])
        fig.update_layout(height=300, template="plotly_dark", margin=dict(l=40, r=10, t=10, b=40),
            paper_bgcolor='#0d1117', plot_bgcolor='#161b22')
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 10 by Volume Ratio")
    top_vol = sorted(preds, key=lambda x: x.get('volume_ratio', 0), reverse=True)[:10]
    fig = go.Figure(data=[go.Bar(
        y=[p.get('symbol', '') for p in top_vol],
        x=[p.get('volume_ratio', 0) for p in top_vol],
        orientation='h', marker_color='#8b5cf6')])
    fig.update_layout(height=350, template="plotly_dark", margin=dict(l=80, r=10, t=10, b=40),
        paper_bgcolor='#0d1117', plot_bgcolor='#161b22')
    st.plotly_chart(fig, use_container_width=True)


def page_history():
    st.title("Scan History")
    db_path = "scanner_history.db"
    if not os.path.exists(db_path):
        st.info("No database yet. Created after first scan.")
        return
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            "SELECT scan_time as Time, symbol as Symbol, price as Price, volume_ratio as Vol, rsi as RSI, round(cmf,3) as CMF FROM session_data ORDER BY id DESC LIMIT 200", conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=500, hide_index=True)
        else:
            st.info("No history yet.")
    except Exception as e:
        st.error(f"Error: {e}")


if __name__ == "__main__":
    main()
