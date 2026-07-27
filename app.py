import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import yfinance as yf
import numpy as np

st.set_page_config(
    page_title="ماسح الحيتان - السوق الأمريكي",
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

@st.cache_data(ttl=60)
def load_results():
    import os, urllib.request
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

def main():
    st.title("🐋 ماسح الحيتان")
    st.caption("فحص نشاط الحيتان والاستثمارات الكبيرة في السوق الأمريكي بالوقت الحقيقي")

    data = load_results()
    if data is None:
        st.error("لا توجد نتائج مسح. شغّل الماسح أولاً.")
        return

    signals = data.get('signals', [])
    scan_time = data.get('scan_time', 'غير معروف')

    st.markdown(f"**آخر مسح:** {scan_time}  |  **إجمالي الإشارات:** {len(signals)}")

    st.divider()

    st.sidebar.header("🔍 الفلاتر")

    signal_types = list(set(s['type'] for s in signals))
    type_labels = {
        'SHORT_SQUEEZE': '🔥 سكвиз (اختصار)',
        'WHALE_ACCUMULATION': '🐋 تجميع حيتان',
        'VOLUME_SPIKE': '📊 ارتفاع حجم التداول',
        'PRICE_SPIKE': '🚀 ارتفاع سعر حاد',
        'PRICE_CRASH': '📉 انهيار سعر',
        'INSIDER_CLUSTER': '👤 شراء مسؤولين داخلي',
    }

    selected_types = st.sidebar.multiselect(
        "نوع الإشارة",
        options=signal_types,
        default=signal_types,
        format_func=lambda x: type_labels.get(x, x)
    )

    min_score = st.sidebar.slider("الحد الأدنى للنقاط", 0, 100, 0)
    max_price = st.sidebar.number_input("أعلى سعر ($)", value=1000, step=10)
    min_price = st.sidebar.number_input("أقل سعر ($)", value=0, step=1)
    sort_by = st.sidebar.selectbox("ترتيب حسب", [
        "النقاط (الأعلى أولاً)",
        "السعر (الأقل أولاً)",
        "السعر (الأعلى أولاً)",
        "الرمز"
    ])

    filtered = [s for s in signals
                if s['type'] in selected_types
                and s.get('price', 0) >= min_price
                and s.get('price', 0) <= max_price
                and s.get('score', 0) >= min_score]

    if sort_by == "النقاط (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('score', 0), reverse=True)
    elif sort_by == "السعر (الأقل أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0))
    elif sort_by == "السعر (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0), reverse=True)
    elif sort_by == "الرمز":
        filtered.sort(key=lambda x: x.get('symbol', ''))

    col1, col2, col3, col4 = st.columns(4)
    squeeze_count = len([s for s in filtered if s['type'] == 'SHORT_SQUEEZE'])
    whale_count = len([s for s in filtered if s['type'] == 'WHALE_ACCUMULATION'])
    vol_count = len([s for s in filtered if s['type'] in ('VOLUME_SPIKE', 'PRICE_SPIKE')])
    crash_count = len([s for s in filtered if s['type'] == 'PRICE_CRASH'])

    col1.metric("🔥 سكвиз", squeeze_count)
    col2.metric("🐋 تجميع حيتان", whale_count)
    col3.metric("📊 ارتفاع/حجم", vol_count)
    col4.metric("📉 انهيار", crash_count)

    st.divider()

    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("توزيع الإشارات")
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
            fig.update_yaxes(title="العدد")
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("توزيع النقاط")
        scores = [s.get('score', 0) for s in filtered]
        if scores:
            fig2 = px.histogram(x=scores, nbins=10, color_discrete_sequence=['#00cc96'])
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
            fig2.update_xaxes(title="النقاط")
            fig2.update_yaxes(title="العدد")
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    st.subheader(f"📋 كل الإشارات ({len(filtered)} سهم)")

    if not filtered:
        st.warning("لا توجد إشارات تطابق فلاترك.")
        return

    table_data = []
    for s in filtered:
        table_data.append({
            'الرمز': s['symbol'],
            'النوع': type_labels.get(s['type'], s['type']),
            'النقاط': s.get('score', 0),
            'السعر ($)': f"${s.get('price', 0):.2f}",
            'التفاصيل': s.get('detail', ''),
        })

    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, height=400)

    st.divider()

    st.subheader("🔎 تفاصيل سهم")
    symbols_list = [s['symbol'] for s in filtered]
    selected_symbol = st.selectbox("اختر سهم", symbols_list)

    if selected_symbol:
        signal = next((s for s in filtered if s['symbol'] == selected_symbol), None)
        if signal:
            col_a, col_b = st.columns([1, 1])

            with col_a:
                st.markdown(f"### {signal['symbol']}")
                st.markdown(f"**النوع:** {type_labels.get(signal['type'], signal['type'])}")
                st.markdown(f"**النقاط:** {signal.get('score', 0)} / 100")
                st.markdown(f"**السعر:** ${signal.get('price', 0):.2f}")
                st.markdown(f"**التفاصيل:** {signal.get('detail', '')}")

                if 'short_percent' in signal:
                    st.markdown(f"**نسبة البيع للshort:** {signal['short_percent']*100:.1f}%")
                if 'zscore' in signal:
                    st.markdown(f"**Z-Score:** {signal['zscore']:.1f}")
                if 'rvol' in signal:
                    st.markdown(f"**الحجم النسبي:** {signal['rvol']:.1f}x")

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
                    st.info("الرسم البياني غير متاح")

    st.divider()
    st.caption(f"ماسح الحيتان v1.0 | آخر مسح: {scan_time} | {len(signals)} إشارة إجمالية")

if __name__ == "__main__":
    main()
