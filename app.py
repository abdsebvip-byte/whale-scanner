import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import yfinance as yf

st.set_page_config(
    page_title="ماسح الحيتان — السوق الأمريكي",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stMetric {background: #0e1117; border: 1px solid #262730; border-radius: 8px; padding: 12px;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
    .block-container {padding-top: 1rem;}
    .info-box {background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px;}
    .warning-box {background: #3d2d1a; border: 1px solid #ff8c00; border-radius: 8px; padding: 16px; margin-bottom: 12px;}
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
    st.title("🐋 ماسح الحيتان — السوق الأمريكي")

    st.markdown("""
    <div class="warning-box">
    <b>تنبيه مهم:</b> هذا الماسح يعرض <b>بيانات حقيقية</b> من البورصة فقط.
    لا يعطي توصيات شراء أو بيع أو نسب أرباح.
    أنت تقرر بناءً على المعلومات المعروضة. قراراتك المالية مسؤوليتك.
    </div>
    """, unsafe_allow_html=True)

    data = load_results()
    if data is None:
        st.error("لا توجد نتائج. شغّل الماسح أولاً.")
        return

    signals = data.get('signals', [])
    scan_time = data.get('scan_time', 'غير معروف')
    scan_session = data.get('session_name', 'غير معروف')

    st.markdown(f"**آخر مسح:** {scan_time}  |  **الجلسة:** {scan_session}  |  **الأسهم المفحوصة:** {len(signals)}")

    st.divider()

    # Sidebar filters
    st.sidebar.header("🔍 الفلاتر")

    min_zscore = st.sidebar.slider(
        "Z-Score الأدنى",
        min_value=0.0, max_value=10.0, value=2.0, step=0.5,
        help="يقيس كم حجم التداول اليوم غير عادي مقارنة بـ 20 يوم"
    )
    min_rvol = st.sidebar.slider(
        "الحجم النسبي الأدنى",
        min_value=0.0, max_value=20.0, value=2.0, step=0.5,
        help="كم مرة الحجم أكبر من المتوسط"
    )
    max_price = st.sidebar.number_input("أعلى سعر ($)", value=1000, step=10)
    min_price = st.sidebar.number_input("أقل سعر ($)", value=0, step=1)
    show_short = st.sidebar.checkbox("بيع عَمَي مرتفع فقط (>15%)", value=False)
    show_insider = st.sidebar.checkbox("شراء مسؤولين فقط", value=False)
    sort_by = st.sidebar.selectbox("ترتيب حسب", [
        "Z-Score (الأعلى أولاً)",
        "الحجم النسبي (الأعلى أولاً)",
        "السعر (الأقل أولاً)",
        "السعر (الأعلى أولاً)",
        "الرمز",
    ])

    # Filter
    filtered = []
    for s in signals:
        price = s.get('price', 0)
        if price < min_price or price > max_price:
            continue
        vd = s.get('volume_data', {})
        if vd.get('z_score', 0) < min_zscore:
            continue
        if vd.get('relative_volume', 0) < min_rvol:
            continue
        if show_short and not s.get('short_data'):
            continue
        if show_insider and not s.get('insider_data'):
            continue
        filtered.append(s)

    # Sort
    if sort_by == "Z-Score (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('volume_data', {}).get('z_score', 0), reverse=True)
    elif sort_by == "الحجم النسبي (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('volume_data', {}).get('relative_volume', 0), reverse=True)
    elif sort_by == "السعر (الأقل أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0))
    elif sort_by == "السعر (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0), reverse=True)
    elif sort_by == "الرمز":
        filtered.sort(key=lambda x: x.get('symbol', ''))

    # Stats
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 حجم غير عادي", len([s for s in filtered if s.get('volume_data', {}).get('z_score', 0) > 2]))
    col2.metric("🔥 بيع عَمَي", len([s for s in filtered if s.get('short_data')]))
    col3.metric("👤 مسؤولين", len([s for s in filtered if s.get('insider_data')]))
    col4.metric("📋 الإجمالي", len(filtered))

    st.divider()

    # Explanation section
    st.subheader("📖 شرح البيانات")
    st.markdown("""
    <div class="info-box">
    <b>Z-Score (الانحراف المعياري):</b><br>
    حساب إحصائي حقيقي يقارن حجم التداول اليوم بـ 20 يوم سابقة.<br>
    • Z = 2.0 → الحجم مرتفع جداً (يحدث في 5% فقط من الأيام)<br>
    • Z = 3.0 → الحجم استثنائي (1%)<br>
    • Z > 4.0 → الحجم نادر جداً — قد يعني تجميع أو خبر قادم<br><br>

    <b>الحجم النسبي (Relative Volume):</b><br>
    كم مرة حجم اليوم أكبر من المتوسط. 3x = ثلاثة أضعاف العادي.<br><br>

    <b>بيع العَمَي (Short Selling):</b><br>
    شخص يبيع أسهم لا يملكها بانتظار هبوط السعر.<br>
    نسبة عالية (>15%) + سعر يصعد = البائعون سيُضطرون للشراء = ضغط شراء إضافي.<br><br>

    <b>شراء المسؤولين الداخليين:</b><br>
    مدير يشتري أسهم بماله الخاص من SEC filings حكومية.<br>
    عادة يشترون قبل أخبار جيدة.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Main table
    st.subheader(f"📋 الأسهم المفحوصة ({len(filtered)} سهم)")

    if not filtered:
        st.warning("لا توجد نتائج تطابق الفلاتر.")
        return

    table_data = []
    for s in filtered:
        vd = s.get('volume_data', {})
        sd = s.get('short_data', {})
        idata = s.get('insider_data', {})

        row = {
            'الرمز': s['symbol'],
            'السعر ($)': f"${s.get('price', 0):.2f}",
            'Z-Score': vd.get('z_score', '-'),
            'الحجم النسبي': f"{vd.get('relative_volume', 0)}x",
            'حجم اليوم': f"{vd.get('today_volume', 0):,}",
            'المتوسط': f"{vd.get('avg_volume_20d', 0):,}",
            'تغيير 5 أيام': f"{vd.get('change_5d', 0):+.1f}%",
        }

        if sd and sd.get('short_percent'):
            row['بيع عَمَي'] = f"{sd['short_percent']*100:.1f}%"
            row['أيام التغطية'] = f"{sd.get('days_to_cover', 0)}"

        if idata:
            row['مسؤولين'] = f"{idata.get('count', 0)} مشتريات"
            row['قيمة الشراء'] = f"${idata.get('total_value', 0):,.0f}"

        table_data.append(row)

    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, height=500)

    st.divider()

    # Charts
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Z-Score")
        z_scores = [s.get('volume_data', {}).get('z_score', 0) for s in filtered]
        if z_scores:
            fig = px.histogram(x=z_scores, nbins=15, color_discrete_sequence=['#00cc96'])
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
            fig.update_xaxes(title="Z-Score")
            fig.update_yaxes(title="عدد")
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("الحجم النسبي")
        rvols = [s.get('volume_data', {}).get('relative_volume', 0) for s in filtered]
        if rvols:
            fig2 = px.histogram(x=rvols, nbins=15, color_discrete_sequence=['#636efa'])
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
            fig2.update_xaxes(title="x")
            fig2.update_yaxes(title="عدد")
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Detail view
    st.subheader("🔎 تفاصيل سهم")
    if filtered:
        selected = st.selectbox("اختر سهم", [s['symbol'] for s in filtered])
        if selected:
            sig = next((s for s in filtered if s['symbol'] == selected), None)
            if sig:
                vd = sig.get('volume_data', {})
                sd = sig.get('short_data', {})

                col_a, col_b = st.columns([1, 1])

                with col_a:
                    st.markdown(f"### {sig['symbol']}")
                    st.markdown(f"**السعر:** ${sig.get('price', 0):.2f}")

                    st.divider()
                    st.markdown("**📊 الحجم:**")
                    z = vd.get('z_score', 0)
                    rvol = vd.get('relative_volume', 0)
                    level = 'استثنائي' if z > 3 else 'مرتفع جداً' if z > 2 else 'مرتفع'
                    st.markdown(f"- Z-Score: **{z}** ({level})")
                    st.markdown(f"- الحجم النسبي: **{rvol}x**")
                    st.markdown(f"- حجم اليوم: **{vd.get('today_volume', 0):,}**")
                    st.markdown(f"- المتوسط 20 يوم: **{vd.get('avg_volume_20d', 0):,}**")
                    st.markdown(f"- تغيّر 5 أيام: **{vd.get('change_5d', 0):+.1f}%**")

                    if sd and sd.get('short_percent'):
                        st.divider()
                        st.markdown("**🔥 بيع العَمَي:**")
                        sp = sd['short_percent'] * 100
                        st.markdown(f"- النسبة: **{sp:.1f}%**")
                        st.caption("النسبة المئوية من الأسهم المتداولة المباعة بيع عَمَي")
                        st.markdown(f"- أيام التغطية: **{sd.get('days_to_cover', 0)}**")
                        st.caption("عدد الأيام لتغطية جميع صفقات بيع العَمَي")
                        st.markdown(f"- العوامة: **{sd.get('float_shares', 0)/1e6:.1f}M**")
                        st.caption("الأسهم المتداولة فعلياً")

                    if sig.get('insider_data'):
                        idata = sig['insider_data']
                        st.divider()
                        st.markdown("**👤 شراء مسؤولين:**")
                        st.markdown(f"- **{idata.get('count', 0)}** مشتريات من **{idata.get('unique_insiders', 0})** مسؤولين")
                        st.markdown(f"- القيمة الإجمالية: **${idata.get('total_value', 0):,.0f}**")

                    st.divider()
                    st.markdown("""
                    <div class="warning-box">
                    هذه بيانات فقط — لا توصيات. قراراتك المالية مسؤوليتك.
                    </div>
                    """, unsafe_allow_html=True)

                with col_b:
                    chart_df = get_stock_chart(selected)
                    if chart_df is not None:
                        fig3 = go.Figure(data=[go.Candlestick(
                            x=chart_df.index,
                            open=chart_df['Open'],
                            high=chart_df['High'],
                            low=chart_df['Low'],
                            close=chart_df['Close'],
                        )])
                        fig3.update_layout(
                            height=400, margin=dict(l=0, r=0, t=0, b=0),
                            xaxis_rangeslider_visible=False, template="plotly_dark",
                        )
                        st.plotly_chart(fig3, use_container_width=True)
                    else:
                        st.info("الرسم البياني غير متاح")

    st.divider()
    st.caption(f"ماسح الحيتان v3.0 | بيانات حقيقية فقط | لا توصيات")


if __name__ == "__main__":
    main()
