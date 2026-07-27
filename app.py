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
    div[data-testid="stMetricValue"] {font-size: 28px;}
    .block-container {padding-top: 1rem;}
    .buy-now {background: #1a3d1a; border: 2px solid #00cc96; border-radius: 8px; padding: 12px; text-align: center; font-size: 20px; font-weight: bold; color: #00cc96;}
    .buy-watch {background: #3d3d1a; border: 2px solid #cccc00; border-radius: 8px; padding: 12px; text-align: center; font-size: 20px; font-weight: bold; color: #cccc00;}
    .wait {background: #3d2d1a; border: 2px solid #ff8c00; border-radius: 8px; padding: 12px; text-align: center; font-size: 20px; font-weight: bold; color: #ff8c00;}
    .no-buy {background: #3d1a1a; border: 2px solid #ff4b4b; border-radius: 8px; padding: 12px; text-align: center; font-size: 20px; font-weight: bold; color: #ff4b4b;}
    .session-info {background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 16px;}
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


TYPE_LABELS = {
    'SHORT_SQUEEZE': '🔥 سكвиз (اختصار)',
    'WHALE_ACCUMULATION': '🐋 تجميع حيتان',
    'VOLUME_SPIKE': '📊 ارتفاع حجم التداول',
    'PRICE_SPIKE': '🚀 ارتفاع سعر حاد',
    'PRICE_CRASH': '📉 انهيار سعر',
    'INSIDER_CLUSTER': '👤 شراء مسؤولين داخلي',
}

ACTION_LABELS = {
    'شراء فوري': '🟢 شراء فوري',
    'شراء بمراقبة': '🟡 شراء بمراقبة',
    'انتظار': '🟠 انتظار',
    'لا تشتري': '🔴 لا تشتري',
}

ACTION_CSS = {
    'شراء فوري': 'buy-now',
    'شراء بمراقبة': 'buy-watch',
    'انتظار': 'wait',
    'لا تشتري': 'no-buy',
}


def main():
    st.title("🐋 ماسح الحيتان - السوق الأمريكي")
    st.caption("فحص نشاط الحيتان والاستثمارات الكبيرة في السوق الأمريكي بالوقت الحقيقي")

    data = load_results()
    if data is None:
        st.error("لا توجد نتائج مسح. شغّل الماسح أولاً.")
        return

    signals = data.get('signals', [])
    scan_time = data.get('scan_time', 'غير معروف')
    scan_session = data.get('session', 'unknown')
    scan_session_name = data.get('session_name', 'غير معروف')

    st.markdown(f"""
    <div class="session-info">
        <b>آخر مسح:</b> {scan_time} &nbsp; | &nbsp;
        <b>الجلسة:</b> {scan_session_name} &nbsp; | &nbsp;
        <b>إجمالي الإشارات:</b> {len(signals)}
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.sidebar.header("🔍 الفلاتر")

    signal_types = list(set(s['type'] for s in signals))

    selected_types = st.sidebar.multiselect(
        "نوع الإشارة",
        options=signal_types,
        default=signal_types,
        format_func=lambda x: TYPE_LABELS.get(x, x)
    )

    min_score = st.sidebar.slider("الحد الأدنى لنقاط الاستراتيجية", 0, 100, 0)
    max_price = st.sidebar.number_input("أعلى سعر ($)", value=1000, step=10)
    min_price = st.sidebar.number_input("أقل سعر ($)", value=0, step=1)

    action_filter = st.sidebar.multiselect(
        "فترة الشراء",
        options=['شراء فوري', 'شراء بمراقبة', 'انتظار', 'لا تشتري'],
        default=['شراء فوري', 'شراء بمراقبة']
    )

    sort_by = st.sidebar.selectbox("ترتيب حسب", [
        "نسبة التطابق (الأعلى أولاً)",
        "النقاط (الأعلى أولاً)",
        "السعر (الأقل أولاً)",
        "السعر (الأعلى أولاً)",
        "الرمز"
    ])

    filtered = [s for s in signals
                if s['type'] in selected_types
                and s.get('price', 0) >= min_price
                and s.get('price', 0) <= max_price
                and s.get('strategy_score', 0) >= min_score
                and s.get('strategy_action', '') in action_filter]

    if sort_by == "نسبة التطابق (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('strategy_score', 0), reverse=True)
    elif sort_by == "النقاط (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('score', 0), reverse=True)
    elif sort_by == "السعر (الأقل أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0))
    elif sort_by == "السعر (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0), reverse=True)
    elif sort_by == "الرمز":
        filtered.sort(key=lambda x: x.get('symbol', ''))

    # Stats
    col1, col2, col3, col4, col5 = st.columns(5)
    buy_now_count = len([s for s in filtered if s.get('strategy_action') == 'شراء فوري'])
    buy_watch_count = len([s for s in filtered if s.get('strategy_action') == 'شراء بمراقبة'])
    wait_count = len([s for s in filtered if s.get('strategy_action') == 'انتظار'])
    no_buy_count = len([s for s in filtered if s.get('strategy_action') == 'لا تشتري'])

    col1.metric("🟢 شراء فوري", buy_now_count)
    col2.metric("🟡 شراء بمراقبة", buy_watch_count)
    col3.metric("🟠 انتظار", wait_count)
    col4.metric("🔴 لا تشتري", no_buy_count)
    col5.metric("📋 الإجمالي", len(filtered))

    st.divider()

    # Tabs for sessions
    tab_all, tab_pre, tab_reg, tab_after = st.tabs([
        "📋 الكل",
        "🌅 ماقبل التداول",
        "☀️ الجلسة الرسمية",
        "🌙 الجلسة المسائية"
    ])

    def render_signals_table(sig_list, show_session=False):
        if not sig_list:
            st.warning("لا توجد إشارات في هذا القسم.")
            return

        table_data = []
        for s in sig_list:
            action = s.get('strategy_action', 'لا تشتري')
            action_display = ACTION_LABELS.get(action, action)
            strategy_score = s.get('strategy_score', 0)
            reasons = s.get('strategy_reasons', [])
            reasons_text = ' + '.join(reasons) if reasons else '-'

            row = {
                'الإشارة': TYPE_LABELS.get(s['type'], s['type']),
                'الرمز': s['symbol'],
                'السعر ($)': f"${s.get('price', 0):.2f}",
                'نسبة التطابق': f"{strategy_score}%",
                'أمر الشراء': action_display,
                'الأسباب': reasons_text,
                'التفاصيل': s.get('detail', ''),
            }

            if 'short_percent' in s:
                row['نسبة الشورت'] = f"{s['short_percent']*100:.1f}%"
            if 'short_ratio' in s:
                row['أيام التغطية'] = f"{s.get('short_ratio', 0):.1f}"
            if 'float_shares' in s:
                row['العوامة'] = f"{s.get('float_shares', 0)/1e6:.1f}M"
            if 'zscore' in s:
                row['Z-Score'] = f"{s.get('zscore', 0):.1f}"
            if 'rvol' in s:
                row['الحجم النسبي'] = f"{s.get('rvol', 1):.1f}x"

            table_data.append(row)

        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, height=400)

    with tab_all:
        render_signals_table(filtered)

    with tab_pre:
        pre_signals = [s for s in filtered if s.get('session') == 'premarket']
        st.markdown(f"**{len(pre_signals)} إشارة في جلسة ماقبل التداول** (الأكثر احتمالاً للانفجارات)")
        render_signals_table(pre_signals)

    with tab_reg:
        reg_signals = [s for s in filtered if s.get('session') == 'regular']
        st.markdown(f"**{len(reg_signals)} إشارة في الجلسة الرسمية**")
        render_signals_table(reg_signals)

    with tab_after:
        after_signals = [s for s in filtered if s.get('session') == 'afterhours']
        st.markdown(f"**{len(after_signals)} إشارة في الجلسة المسائية**")
        render_signals_table(after_signals)

    st.divider()

    # Charts
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("توزيع الإشارات")
        type_counts = {}
        for s in filtered:
            t = TYPE_LABELS.get(s['type'], s['type'])
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
        st.subheader("توزيع أمر الشراء")
        action_counts = {}
        for s in filtered:
            a = ACTION_LABELS.get(s.get('strategy_action', ''), s.get('strategy_action', ''))
            action_counts[a] = action_counts.get(a, 0) + 1
        if action_counts:
            fig2 = px.pie(values=list(action_counts.values()), names=list(action_counts.keys()),
                          color_discrete_map={
                              '🟢 شراء فوري': '#00cc96',
                              '🟡 شراء بمراقبة': '#cccc00',
                              '🟠 انتظار': '#ff8c00',
                              '🔴 لا تشتري': '#ff4b4b',
                          })
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Detail view
    st.subheader("🔎 تفاصيل سهم")
    if filtered:
        symbols_list = [s['symbol'] for s in filtered]
        selected_symbol = st.selectbox("اختر سهم", symbols_list)

        if selected_symbol:
            signal = next((s for s in filtered if s['symbol'] == selected_symbol), None)
            if signal:
                action = signal.get('strategy_action', 'لا تشتري')
                action_display = ACTION_LABELS.get(action, action)
                css_class = ACTION_CSS.get(action, 'no-buy')
                strategy_score = signal.get('strategy_score', 0)
                reasons = signal.get('strategy_reasons', [])

                st.markdown(f'<div class="{css_class}">{action_display} | نسبة التطابق: {strategy_score}%</div>', unsafe_allow_html=True)

                col_a, col_b = st.columns([1, 1])

                with col_a:
                    st.markdown(f"### {signal['symbol']}")
                    st.markdown(f"**النوع:** {TYPE_LABELS.get(signal['type'], signal['type'])}")
                    st.markdown(f"**النقاط:** {signal.get('score', 0)} / 100")
                    st.markdown(f"**السعر:** ${signal.get('price', 0):.2f}")
                    st.markdown(f"**التفاصيل:** {signal.get('detail', '')}")

                    if 'short_percent' in signal:
                        sp = signal['short_percent'] * 100
                        st.markdown(f"**نسبة البيع للشورت:** {sp:.1f}%")
                        st.caption("النسبة المئوية من الأسهم المتداولة التي تم بيعها شورت (بيع عَمَي)")
                    if 'short_ratio' in signal:
                        st.markdown(f"**أيام التغطية:** {signal['short_ratio']:.1f}")
                        st.caption("عدد الأيام المطلوبة لتغطية جميع صفقات الشورت")
                    if 'float_shares' in signal:
                        st.markdown(f"**العوامة (Float):** {signal['float_shares']/1e6:.1f}M")
                        st.caption("عدد الأسهم المتداولة فعلياً في السوق")
                    if 'zscore' in signal:
                        st.markdown(f"**Z-Score:** {signal['zscore']:.1f}")
                    if 'rvol' in signal:
                        st.markdown(f"**الحجم النسبي:** {signal['rvol']:.1f}x")

                    if reasons:
                        st.markdown("**أسباب التوصية:**")
                        for r in reasons:
                            st.markdown(f"- {r}")

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
    st.caption(f"ماسح الحيتان v2.0 | آخر مسح: {scan_time} | الجلسة: {scan_session_name} | {len(signals)} إشارة إجمالية")


if __name__ == "__main__":
    main()
