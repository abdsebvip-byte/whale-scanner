import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import yfinance as yf
import numpy as np

st.set_page_config(
    page_title="Whale Scanner - US Market",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stMetric {background: #0e1117; border: 1px solid #262730; border-radius: 8px; padding: 12px;}
    .signal-card {background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 8px;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
    .block-container {padding-top: 1rem;}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_results():
    try:
        with open('scan_results.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
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

def main():
    st.title("🐋 Whale Scanner Dashboard")
    st.caption("Real-time whale activity scanner for the entire US stock market")

    data = load_results()
    if data is None:
        st.error("No scan results found. Run the scanner first.")
        return

    signals = data.get('signals', [])
    scan_time = data.get('scan_time', 'Unknown')

    # Header stats
    st.markdown(f"**Last Scan:** {scan_time}  |  **Total Signals:** {len(signals)}")

    st.divider()

    # Sidebar filters
    st.sidebar.header("🔍 Filters")

    signal_types = list(set(s['type'] for s in signals))
    type_labels = {
        'SHORT_SQUEEZE': '🔥 Short Squeeze',
        'WHALE_ACCUMULATION': '🐋 Whale Accumulation',
        'VOLUME_SPIKE': '📊 Volume Spike',
        'PRICE_SPIKE': '🚀 Price Spike',
        'PRICE_CRASH': '📉 Price Crash',
        'INSIDER_CLUSTER': '👤 Insider Buying',
    }

    selected_types = st.sidebar.multiselect(
        "Signal Type",
        options=signal_types,
        default=signal_types,
        format_func=lambda x: type_labels.get(x, x)
    )

    min_score = st.sidebar.slider("Minimum Score", 0, 100, 0)
    max_price = st.sidebar.number_input("Max Price ($)", value=1000, step=10)
    min_price = st.sidebar.number_input("Min Price ($)", value=0, step=1)
    sort_by = st.sidebar.selectbox("Sort By", ["Score (High to Low)", "Price (Low to High)", "Price (High to Low)", "Symbol"])

    # Filter signals
    filtered = [s for s in signals
                if s['type'] in selected_types
                and s.get('price', 0) >= min_price
                and s.get('price', 0) <= max_price
                and s.get('score', 0) >= min_score]

    # Sort
    if sort_by == "Score (High to Low)":
        filtered.sort(key=lambda x: x.get('score', 0), reverse=True)
    elif sort_by == "Price (Low to High)":
        filtered.sort(key=lambda x: x.get('price', 0))
    elif sort_by == "Price (High to Low)":
        filtered.sort(key=lambda x: x.get('price', 0), reverse=True)
    elif sort_by == "Symbol":
        filtered.sort(key=lambda x: x.get('symbol', ''))

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    squeeze_count = len([s for s in filtered if s['type'] == 'SHORT_SQUEEZE'])
    whale_count = len([s for s in filtered if s['type'] == 'WHALE_ACCUMULATION'])
    vol_count = len([s for s in filtered if s['type'] in ('VOLUME_SPIKE', 'PRICE_SPIKE')])
    crash_count = len([s for s in filtered if s['type'] == 'PRICE_CRASH'])

    col1.metric("🔥 Squeeze", squeeze_count)
    col2.metric("🐋 Whale", whale_count)
    col3.metric("📊 Volume/Spike", vol_count)
    col4.metric("📉 Crash", crash_count)

    st.divider()

    # Charts row
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("Signal Distribution")
        type_counts = {}
        for s in filtered:
            t = type_labels.get(s['type'], s['type'])
            type_counts[t] = type_counts.get(t, 0) + 1
        if type_counts:
            fig = px.bar(
                x=list(type_counts.keys()),
                y=list(type_counts.values()),
                color=list(type_counts.keys()),
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=0, t=0, b=0))
            fig.update_xaxes(title="")
            fig.update_yaxes(title="Count")
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Score Distribution")
        scores = [s.get('score', 0) for s in filtered]
        if scores:
            fig2 = px.histogram(x=scores, nbins=10, color_discrete_sequence=['#00cc96'])
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
            fig2.update_xaxes(title="Score")
            fig2.update_yaxes(title="Count")
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Main table
    st.subheader(f"📋 All Signals ({len(filtered)} stocks)")

    if not filtered:
        st.warning("No signals match your filters.")
        return

    table_data = []
    for s in filtered:
        table_data.append({
            'Symbol': s['symbol'],
            'Type': type_labels.get(s['type'], s['type']),
            'Score': s.get('score', 0),
            'Price ($)': f"${s.get('price', 0):.2f}",
            'Detail': s.get('detail', ''),
        })

    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, height=400)

    st.divider()

    # Stock detail view
    st.subheader("🔎 Stock Detail View")
    symbols_list = [s['symbol'] for s in filtered]
    selected_symbol = st.selectbox("Select a stock", symbols_list)

    if selected_symbol:
        signal = next((s for s in filtered if s['symbol'] == selected_symbol), None)
        if signal:
            col_a, col_b = st.columns([1, 1])

            with col_a:
                st.markdown(f"### {signal['symbol']}")
                st.markdown(f"**Type:** {type_labels.get(signal['type'], signal['type'])}")
                st.markdown(f"**Score:** {signal.get('score', 0)} / 100")
                st.markdown(f"**Price:** ${signal.get('price', 0):.2f}")
                st.markdown(f"**Detail:** {signal.get('detail', '')}")

                if 'short_percent' in signal:
                    st.markdown(f"**Short %:** {signal['short_percent']*100:.1f}%")
                if 'zscore' in signal:
                    st.markdown(f"**Z-Score:** {signal['zscore']:.1f}")
                if 'rvol' in signal:
                    st.markdown(f"**RVOL:** {signal['rvol']:.1f}x")

            with col_b:
                chart_df = get_stock_chart(selected_symbol)
                if chart_df is not None:
                    fig3 = go.Figure(data=[go.Candlestick(
                        x=chart_df.index,
                        open=chart_df['Open'],
                        high=chart_df['High'],
                        low=chart_df['Low'],
                        close=chart_df['Close'],
                        name=selected_symbol
                    )])
                    fig3.update_layout(
                        height=350,
                        margin=dict(l=0, r=0, t=0, b=0),
                        xaxis_rangeslider_visible=False,
                        template="plotly_dark",
                    )
                    st.plotly_chart(fig3, use_container_width=True)
                else:
                    st.info("Chart data unavailable")

    # Footer
    st.divider()
    st.caption(f"Whale Scanner v1.0 | Scan: {scan_time} | {len(signals)} total signals")

if __name__ == "__main__":
    main()
