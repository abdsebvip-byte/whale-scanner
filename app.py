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
    .signal-badge {display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin: 2px;}
    .badge-volume {background: #1a3d5c; color: #63b3ed;}
    .badge-squeeze {background: #5c3d1a; color: #ed8936;}
    .badge-accum {background: #1a5c3d; color: #48bb78;}
    .badge-options {background: #3d1a5c; color: #9f7aea;}
    .badge-short {background: #5c1a1a; color: #fc8181;}
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


SIGNAL_TYPE_LABELS = {
    'VOLUME_ANOMALY': '📊 حجم غير عادي',
    'BOLLINGER_SQUEEZE': '🔴 انكماش Bollinger',
    'ACCUMULATION': '🐋 تجميع أموال',
    'MULTI_DAY_VOLUME': '📈 حجم عالي متعدد الأيام',
    'UNUSUAL_OPTIONS': '🔥 خيارات غير عادية',
    'HIGH_SHORT_INTEREST': '⬆️ بيع عَمَي مرتفع',
    'ANOMALY_DETECTED': '🤖 شذوذ ذكاء اصطناعي',
}


def main():
    st.title("🐋 ماسح الحيتان — السوق الأمريكي")

    st.markdown("""
    <div class="warning-box">
    <b>تنبيه:</b> بيانات حقيقية فقط. لا توصيات شراء أو بيع.
    هذه إشارات إحصائية — ليست تنبؤات. قراراتك المالية مسؤوليتك.
    </div>
    """, unsafe_allow_html=True)

    data = load_results()
    if data is None:
        st.error("لا توجد نتائج. شغّل الماسح أولاً.")
        return

    signals = data.get('signals', [])
    scan_time = data.get('scan_time', 'غير معروف')
    scan_session = data.get('session_name', 'غير معروف')

    st.markdown(f"**آخر مسح:** {scan_time}  |  **الجلسة:** {scan_session}")

    st.divider()

    # Sidebar
    st.sidebar.header("🔍 الفلاتر")

    min_zscore = st.sidebar.slider("Z-Score الأدنى", 0.0, 10.0, 2.0, 0.5)
    min_signals = st.sidebar.slider("الحد الأدنى لعدد الإشارات", 1, 6, 1)
    max_price = st.sidebar.number_input("أعلى سعر ($)", value=1000, step=10)
    min_price = st.sidebar.number_input("أقل سعر ($)", value=0, step=1)

    signal_filter = st.sidebar.multiselect(
        "نوع الإشارة",
        options=list(SIGNAL_TYPE_LABELS.keys()),
        default=list(SIGNAL_TYPE_LABELS.keys()),
        format_func=lambda x: SIGNAL_TYPE_LABELS.get(x, x)
    )

    sort_by = st.sidebar.selectbox("ترتيب حسب", [
        "عدد الإشارات (الأكثر أولاً)",
        "Z-Score (الأعلى أولاً)",
        "CMF (الأعلى أولاً)",
        "السعر (الأقل أولاً)",
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
        sigs = s.get('signals', [])
        if len(sigs) < min_signals:
            continue
        sig_types = [sig['type'] for sig in sigs]
        if not any(st in signal_filter for st in sig_types):
            continue
        filtered.append(s)

    # Sort
    if sort_by == "عدد الإشارات (الأكثر أولاً)":
        filtered.sort(key=lambda x: len(x.get('signals', [])), reverse=True)
    elif sort_by == "Z-Score (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('volume_data', {}).get('z_score', 0), reverse=True)
    elif sort_by == "CMF (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('accumulation', {}).get('cmf', 0), reverse=True)
    elif sort_by == "السعر (الأقل أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0))
    elif sort_by == "الرمز":
        filtered.sort(key=lambda x: x.get('symbol', ''))

    # Stats
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("📊 حجم", len([s for s in filtered if any(sig['type'] == 'VOLUME_ANOMALY' for sig in s.get('signals', []))]))
    col2.metric("🔴 انكماش", len([s for s in filtered if any(sig['type'] == 'BOLLINGER_SQUEEZE' for sig in s.get('signals', []))]))
    col3.metric("🐋 تجميع", len([s for s in filtered if any(sig['type'] == 'ACCUMULATION' for sig in s.get('signals', []))]))
    col4.metric("🔥 خيارات", len([s for s in filtered if any(sig['type'] == 'UNUSUAL_OPTIONS' for sig in s.get('signals', []))]))
    col5.metric("🤖 شذوذ", len([s for s in filtered if any(sig['type'] == 'ANOMALY_DETECTED' for sig in s.get('signals', []))]))
    col6.metric("📋 الإجمالي", len(filtered))

    st.divider()

    # Explanation
    st.subheader("📖 شرح الإشارات")
    st.markdown("""
    <div class="info-box">
    <b>📊 حجم غير عادي (Z-Score > 2):</b> حجم التداول اليوم أكبر بكثير من المتوسط. قد يشير لتجميع أو خبر قادم.<br><br>
    <b>🔴 انكماش Bollinger:</b> عرض شريط Bollinger انضغط — السعر يتقلص ويجهز لحركة قوية. "الهدوء قبل العاصفة".<br><br>
    <b>🐋 تجميع أموال (CMF > 0.15 + OBV صاعد):</b> الأموال الذكية تدخل السهم — السعر ثابت لكن الأموال تزيد.<br><br>
    <b>📈 حجم عالي متعدد الأيام:</b> 3+ أيام حجم مرتفع — تجميع مستمر وليس حركة عشوائية.<br><br>
    <b>🔥 خيارات غير عادية:</b> حجم تداول خيارات يتجاوز 3 مرات Open Interest — شخص يعرف شي.<br><br>
    <b>⬆️ بيع عَمَي مرتفع (>15%):</b> نسبة عالية من الأسهم تباع بيع عَمَي — إذا صعد السعر، البائعون سيُضطرون للشراء.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Main table
    st.subheader(f"📋 الأسهم ({len(filtered)} سهم)")

    if not filtered:
        st.warning("لا توجد نتائج.")
        return

    table_data = []
    for s in filtered:
        vd = s.get('volume_data', {})
        acc = s.get('accumulation', {})
        bb = s.get('bollinger', {})

        sigs = s.get('signals', [])
        sig_names = [SIGNAL_TYPE_LABELS.get(sig['type'], sig['type']) for sig in sigs]

        row = {
            'الرمز': s['symbol'],
            'السعر ($)': f"${s.get('price', 0):.2f}",
            'عدد الإشارات': len(sigs),
            'الإشارات': ' + '.join(sig_names),
            'Z-Score': vd.get('z_score', '-'),
            'الحجم النسبي': f"{vd.get('relative_volume', 0)}x",
            'CMF': acc.get('cmf', '-'),
            'OBV': acc.get('obv_trend', '-'),
            'RSI': s.get('rsi', '-'),
            'تغيير 5 أيام': f"{s.get('change_5d', 0):+.1f}%",
        }

        # Options data
        for sig in sigs:
            if sig['type'] == 'UNUSUAL_OPTIONS':
                opt = sig.get('options_data', {})
                row['خيارات'] = f"{opt.get('count', 0)} عقود — {opt.get('bias', '')}"

        # Short data
        for sig in sigs:
            if sig['type'] == 'HIGH_SHORT_INTEREST':
                sd = sig.get('short_data', {})
                row['بيع عَمَي'] = f"{sd.get('short_percent', 0)*100:.1f}%"

        table_data.append(row)

    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, height=600)

    st.divider()

    # Detail view
    st.subheader("🔎 تفاصيل سهم")
    if filtered:
        selected = st.selectbox("اختر سهم", [s['symbol'] for s in filtered])
        if selected:
            sig = next((s for s in filtered if s['symbol'] == selected), None)
            if sig:
                vd = sig.get('volume_data', {})
                acc = sig.get('accumulation', {})
                bb = sig.get('bollinger', {})

                col_a, col_b = st.columns([1, 1])

                with col_a:
                    st.markdown(f"### {sig['symbol']}")
                    st.markdown(f"**السعر:** ${sig.get('price', 0):.2f}")

                    st.divider()
                    st.markdown("**📊 الحجم:**")
                    z = vd.get('z_score', 0)
                    level = 'استثنائي' if z > 3 else 'مرتفع جداً' if z > 2 else 'مرتفع'
                    st.markdown(f"- Z-Score: **{z}** ({level})")
                    st.markdown(f"- الحجم النسبي: **{vd.get('relative_volume', 0)}x**")
                    st.markdown(f"- حجم اليوم: **{vd.get('today_volume', 0):,}**")
                    st.markdown(f"- المتوسط 20 يوم: **{vd.get('avg_volume_20d', 0):,}**")
                    st.markdown(f"- أيام حجم عالي: **{vd.get('high_volume_days_5', 0)}/5**")

                    st.divider()
                    st.markdown("**📈 المؤشرات:**")
                    st.markdown(f"- CMF: **{acc.get('cmf', 0)}** — {'تجميع' if acc.get('cmf', 0) > 0.15 else 'محايد' if acc.get('cmf', 0) > 0 else 'توزيع'}")
                    st.markdown(f"- OBV: **{acc.get('obv_trend', '')}** — {'فوق المتوسط' if acc.get('obv_above_sma') else 'تحت المتوسط'}")
                    st.markdown(f"- RSI: **{s.get('rsi', 50)}**")
                    st.markdown(f"- Bollinger: **{'انكماش' if bb.get('squeeze') else 'عادي'}** (عرض={bb.get('width', 0)})")
                    st.markdown(f"- تغيّر 5 أيام: **{sig.get('change_5d', 0):+.1f}%**")
                    st.markdown(f"- شذوذ AI: **{sig.get('anomaly_score', 0)}** {'⚠️' if sig.get('is_anomaly') else '✅'}")

                    # Signals details
                    for signal in sig.get('signals', []):
                        st.divider()
                        label = SIGNAL_TYPE_LABELS.get(signal['type'], signal['type'])
                        st.markdown(f"**{label}:**")
                        st.markdown(signal['detail'])

                        if signal['type'] == 'UNUSUAL_OPTIONS':
                            opt = signal.get('options_data', {})
                            for c in opt.get('contracts', [])[:5]:
                                st.markdown(f"  - {c['contract']}: حجم={c['volume']}, OI={c['open_interest']}, نسبة={c['ratio']}x")

                        if signal['type'] == 'HIGH_SHORT_INTEREST':
                            sd = signal.get('short_data', {})
                            st.markdown(f"  - نسبة بيع العَمَي: {sd.get('short_percent', 0)*100:.1f}%")
                            st.markdown(f"  - أيام التغطية: {sd.get('days_to_cover', 0)}")
                            st.markdown(f"  - العوامة: {sd.get('float_shares', 0)/1e6:.1f}M")

                    st.divider()
                    st.markdown("""
                    <div class="warning-box">
                    بيانات فقط — لا توصيات. قراراتك المالية مسؤوليتك.
                    </div>
                    """, unsafe_allow_html=True)

                with col_b:
                    chart_df = get_stock_chart(selected)
                    if chart_df is not None:
                        fig = go.Figure(data=[go.Candlestick(
                            x=chart_df.index,
                            open=chart_df['Open'],
                            high=chart_df['High'],
                            low=chart_df['Low'],
                            close=chart_df['Close'],
                        )])
                        fig.update_layout(
                            height=400, margin=dict(l=0, r=0, t=0, b=0),
                            xaxis_rangeslider_visible=False, template="plotly_dark",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("الرسم البياني غير متاح")

    st.divider()
    st.subheader("🧠 التعلم الذاتي")
    st.markdown("""
    <div class="info-box">
    الماسح يتعلم من أخطائه — عندما يفوّت سهم صعد، يحلل السبب ويُحسّن الكشف في المرة القادمة.
    </div>
    """, unsafe_allow_html=True)

    import os
    memory_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_memory.json")
    if os.path.exists(memory_path):
        with open(memory_path, 'r', encoding='utf-8') as f:
            mem = json.load(f)
        lessons = mem.get('lessons', [])
        if lessons:
            reason_counts = {}
            for l in lessons:
                for r in l.get('reason_we_missed', []):
                    reason_counts[r] = reason_counts.get(r, 0) + 1
            st.markdown(f"**عدد الدروس المُتعلّمة:** {len(lessons)}")
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                st.markdown(f"- {reason}: {count} مرة")
        else:
            st.info("لا توجد دروس بعد — الماسح سيبدأ بالتعلم بعد أول جلسة.")
    else:
        st.info("الذاكرة غير موجودة — سيُنشأ تلقائياً بعد أول مسح.")

    st.divider()
    st.caption(f"ماسح الحيتان v4.0 | بيانات حقيقية فقط | لا توصيات")


if __name__ == "__main__":
    main()
