import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import yfinance as yf
import sqlite3
import os

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
    .grade-a {color: #48bb78; font-weight: bold; font-size: 24px;}
    .grade-b {color: #63b3ed; font-weight: bold; font-size: 24px;}
    .grade-c {color: #ed8936; font-weight: bold; font-size: 24px;}
    .grade-d {color: #fc8181; font-weight: bold; font-size: 24px;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
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


def main():
    st.title("🐋 ماسح الحيتان — السوق الأمريكي v5.0")

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

    col_header1, col_header2, col_header3 = st.columns(3)
    col_header1.markdown(f"**آخر مسح:** {scan_time[:16]}")
    col_header2.markdown(f"**الجلسة:** {scan_session}")
    col_header3.markdown(f"**الإجمالي:** {len(signals)} سهم")

    st.divider()

    # ─── الفلاتر ───
    st.sidebar.header("🔍 الفلاتر")

    min_grade = st.sidebar.selectbox("الحد الأدنى للدرجة", ['A+', 'A', 'B+', 'B', 'C', 'D'], index=3)
    grade_order = {'A+': 6, 'A': 5, 'B+': 4, 'B': 3, 'C': 2, 'D': 1}
    min_grade_val = grade_order.get(min_grade, 1)

    min_zscore = st.sidebar.slider("Z-Score الأدنى", 0.0, 10.0, 1.5, 0.5)
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
        "درجة الحوت (الأعلى أولاً)",
        "عدد الإشارات (الأكثر أولاً)",
        "Z-Score (الأعلى أولاً)",
        "CMF (الأعلى أولاً)",
        "السعر (الأقل أولاً)",
    ])

    # ─── الفلترة ───
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
        grade_val = grade_order.get(s.get('grade', 'D'), 1)
        if grade_val < min_grade_val:
            continue
        sig_types = [sig['type'] for sig in sigs]
        if not any(st in signal_filter for st in sig_types):
            continue
        filtered.append(s)

    # ─── الترتيب ───
    if sort_by == "درجة الحوت (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('whale_score', 0), reverse=True)
    elif sort_by == "عدد الإشارات (الأكثر أولاً)":
        filtered.sort(key=lambda x: len(x.get('signals', [])), reverse=True)
    elif sort_by == "Z-Score (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('volume_data', {}).get('z_score', 0), reverse=True)
    elif sort_by == "CMF (الأعلى أولاً)":
        filtered.sort(key=lambda x: x.get('accumulation', {}).get('cmf', 0), reverse=True)
    elif sort_by == "السعر (الأقل أولاً)":
        filtered.sort(key=lambda x: x.get('price', 0))

    # ─── الإحصائيات ───
    st.subheader("📊 ملخص")
    stats_cols = st.columns(8)
    stats_cols[0].metric("📋 الإجمالي", len(filtered))
    stats_cols[1].metric("📊 حجم", len([s for s in filtered if any(sig['type'] == 'VOLUME_ANOMALY' for sig in s.get('signals', []))]))
    stats_cols[2].metric("🔴 انكماش", len([s for s in filtered if any(sig['type'] == 'BOLLINGER_SQUEEZE' for sig in s.get('signals', []))]))
    stats_cols[3].metric("🐋 تجميع", len([s for s in filtered if any(sig['type'] == 'ACCUMULATION' for sig in s.get('signals', []))]))
    stats_cols[4].metric("🔥 خيارات", len([s for s in filtered if any(sig['type'] == 'UNUSUAL_OPTIONS' for sig in s.get('signals', []))]))
    stats_cols[5].metric("📐 فجوات", len([s for s in filtered if any(sig['type'] == 'GAP_DETECTED' for sig in s.get('signals', []))]))
    stats_cols[6].metric("📰 أخبار", len([s for s in filtered if any(sig['type'] == 'NEWS_HEAVY' for sig in s.get('signals', []))]))
    stats_cols[7].metric("💰 داخلي", len([s for s in filtered if any(sig['type'] == 'INSIDER_BUYING' for sig in s.get('signals', []))]))

    st.divider()

    # ─── شرح الإشارات ───
    st.subheader("📖 شرح الإشارات")
    with st.expander("اضغط للتوسيع"):
        st.markdown("""
        <div class="info-box">
        <b>📊 حجم غير عادي (Z-Score > 2):</b> حجم التداول أكبر بكثير من المتوسط — يشير لتجميع أو خبر قادم.<br><br>
        <b>🔴 انكماش Bollinger:</b> عرض شريط Bollinger انضغط — السعر يجهز لحركة قوية.<br><br>
        <b>🐋 تجميع أموال (CMF > 0.15 + OBV صاعد):</b> الأموال الذكية تدخل السهم.<br><br>
        <b>📈 حجم عالي متعدد الأيام:</b> 3+ أيام حجم مرتفع — تجميع مستمر.<br><br>
        <b>🔥 خيارات غير عادية:</b> حجم تداول خيارات يتجاوز 3 مرات Open Interest.<br><br>
        <b>⬆️ بيع عَمَي مرتفع (>15%):</b> إذا صعد السعر، البائعون سيُضطرون للشراء (Short Squeeze).<br><br>
        <b>🤖 شذوذ AI (Isolation Forest):</b> ذكاء اصطناعي يكشف الحركات غير الطبيعية.<br><br>
        <b>📐 فجوة سعرية (>2%):</b> فجوة ما قبل/بعد الجلسة — خبر أو توقعات.<br><br>
        <b>📰 أخبار كثيرة:</b> 3+ أخبار في وقت قصير — اهتمام وسائل الإعلام.<br><br>
        <b>💰 شراء داخلي:</b> مسؤولون يشترون أسهم الشركة بأموالهم الخاصة.
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ─── تصدير Excel ───
    if filtered:
        export_data = []
        for s in filtered:
            vd = s.get('volume_data', {})
            acc = s.get('accumulation', {})
            sig_types = [sig['type'] for sig in s.get('signals', [])]
            export_data.append({
                'الرمز': s['symbol'],
                'السعر': round(s.get('price', 0), 2),
                'درجة الحوت': s.get('whale_score', 0),
                'الدرجة': s.get('grade', '?'),
                'عدد الإشارات': len(sig_types),
                'Z-Score': vd.get('z_score', 0),
                'حجم نسبي': f"{vd.get('relative_volume', 0)}x",
                'CMF': acc.get('cmf', 0),
                'OBV': acc.get('obv_trend', ''),
                'RSI': s.get('rsi', 50),
                'Bollinger': 'انكماش' if s.get('bollinger', {}).get('squeeze') else 'عادي',
                'AI شذوذ': 'نعم' if s.get('is_anomaly') else 'لا',
                'تغيير 5 أيام': f"{s.get('change_5d', 0):+.1f}%",
                'الإشارات': ' + '.join(sig_types),
            })
        export_df = pd.DataFrame(export_data)
        csv = export_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 تصدير CSV",
            data=csv,
            file_name=f"whale_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    st.divider()

    # ─── الجدول الرئيسي ───
    st.subheader(f"📋 الأسهم ({len(filtered)} سهم)")

    if not filtered:
        st.warning("لا توجد نتائج.")
        return

    for s in filtered:
        vd = s.get('volume_data', {})
        acc = s.get('accumulation', {})
        bb = s.get('bollinger', {})
        sigs = s.get('signals', [])
        score = s.get('whale_score', 0)
        grade = s.get('grade', '?')

        grade_colors = {'A+': '#48bb78', 'A': '#68d391', 'B+': '#63b3ed', 'B': '#4299e1', 'C': '#ed8936', 'D': '#fc8181'}
        color = grade_colors.get(grade, '#ffffff')

        with st.expander(f"**{s['symbol']}** — ${s.get('price', 0):.2f} | درجة: {score}/100 ({grade}) | {len(sigs)} إشارات", expanded=False):
            col_a, col_b = st.columns([1, 1])

            with col_a:
                st.markdown(f"### {s['symbol']}")
                st.markdown(f"**السعر:** ${s.get('price', 0):.2f}")
                st.markdown(f"**درجة الحوت:** {score}/100")
                st.markdown(f"<span style='color:{color}; font-size:24px; font-weight:bold;'>{grade}</span>", unsafe_allow_html=True)

                st.divider()
                st.markdown("**📊 الحجم:**")
                st.markdown(f"- Z-Score: **{vd.get('z_score', 0)}**")
                st.markdown(f"- الحجم النسبي: **{vd.get('relative_volume', 0)}x**")
                st.markdown(f"- حجم اليوم: **{vd.get('today_volume', 0):,}**")
                st.markdown(f"- الحجم المُسطّح للوقت: **{vd.get('extrapolated_volume', 0):,}**")
                st.markdown(f"- Z المُعدّل للجلسة: **{vd.get('session_adjusted_z', 0)}**")
                st.markdown(f"- حجم 20 يوم: **{vd.get('avg_volume_20d', 0):,}**")
                st.markdown(f"- أيام حجم عالي: **{vd.get('high_volume_days_5', 0)}/5**")

                st.divider()
                st.markdown("**📈 المؤشرات:**")
                st.markdown(f"- CMF: **{acc.get('cmf', 0)}** — {'تجميع' if acc.get('cmf', 0) > 0.15 else 'محايد' if acc.get('cmf', 0) > 0 else 'توزيع'}")
                st.markdown(f"- OBV: **{acc.get('obv_trend', '')}**")
                st.markdown(f"- RSI: **{s.get('rsi', 50)}**")
                st.markdown(f"- Bollinger: **{'انكماش' if bb.get('squeeze') else 'عادي'}**")
                st.markdown(f"- تغيّر 5 أيام: **{s.get('change_5d', 0):+.1f}%**")
                st.markdown(f"- شذوذ AI: **{s.get('anomaly_score', 0)}** {'⚠️' if s.get('is_anomaly') else '✅'}")

                st.divider()
                st.markdown("**📋 الإشارات:**")
                for signal in sigs:
                    label = SIGNAL_TYPE_LABELS.get(signal['type'], signal['type'])
                    st.markdown(f"- {label}: {signal['detail']}")

                # ─── خيارات ───
                for signal in sigs:
                    if signal['type'] == 'UNUSUAL_OPTIONS':
                        st.divider()
                        st.markdown("**🔥 تفاصيل الخيارات:**")
                        opt = signal.get('options_data', {})
                        for c in opt.get('contracts', [])[:5]:
                            st.markdown(f"  - {c['contract']}: حجم={c['volume']}, OI={c['open_interest']}, نسبة={c['ratio']}x")

                # ─── بيع عَمَي ───
                for signal in sigs:
                    if signal['type'] == 'HIGH_SHORT_INTEREST':
                        sd = signal.get('short_data', {})
                        st.divider()
                        st.markdown("**⬆️ تفاصيل بيع العَمَي:**")
                        st.markdown(f"  - النسبة: {sd.get('short_percent', 0)*100:.1f}%")
                        st.markdown(f"  - أيام التغطية: {sd.get('days_to_cover', 0)}")
                        st.markdown(f"  - العوامة: {sd.get('float_shares', 0)/1e6:.1f}M")

                # ─── فجوات ───
                for signal in sigs:
                    if signal['type'] == 'GAP_DETECTED':
                        gap = signal.get('gap_data', {})
                        st.divider()
                        st.markdown("**📐 تفاصيل الفجوة:**")
                        st.markdown(f"  - النوع: {gap.get('type', '')}")
                        st.markdown(f"  - النسبة: {gap.get('percent', 0)}%")
                        st.markdown(f"  - من: ${gap.get('from', 0)} إلى: ${gap.get('to', 0)}")

                # ─── أخبار ───
                for signal in sigs:
                    if signal['type'] == 'NEWS_HEAVY':
                        news = signal.get('news_data', {})
                        st.divider()
                        st.markdown("**📰 العناوين:**")
                        for h in news.get('headlines', [])[:3]:
                            st.markdown(f"  - [{h['title']}]({h['link']}) — {h['publisher']} ({h['date']})")

                # ─── شراء داخلي ───
                for signal in sigs:
                    if signal['type'] == 'INSIDER_BUYING':
                        insider = signal.get('insider_data', {})
                        st.divider()
                        st.markdown("**💰 الشراء الداخلي:**")
                        for t in insider.get('transactions', [])[:3]:
                            st.markdown(f"  - {t['insider']} ({t['title']}): {t['shares']} سهم @ ${t['price']}")

                st.divider()
                st.markdown("""
                <div class="warning-box">
                بيانات فقط — لا توصيات. قراراتك المالية مسؤوليتك.
                </div>
                """, unsafe_allow_html=True)

            with col_b:
                chart_df = get_stock_chart(s['symbol'])
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

    # ─── التعلم الذاتي ───
    st.divider()
    st.subheader("🧠 التعلم الذاتي")
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
            st.markdown(f"**عدد الدروس:** {len(lessons)}")
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                st.markdown(f"- {reason}: {count} مرة")
        else:
            st.info("لا توجد دروس بعد.")

    # ─── التاريخ ───
    st.divider()
    st.subheader("📊 تاريخ الإشارات")
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_history.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            hist_df = pd.read_sql_query(
                "SELECT scan_time, symbol, score, grade FROM scan_history ORDER BY id DESC LIMIT 200",
                conn
            )
            conn.close()
            if not hist_df.empty:
                st.dataframe(hist_df, use_container_width=True)
        except Exception:
            st.info("لا توجد بيانات تاريخية.")
    else:
        st.info("قاعدة البيانات غير موجودة — ستُنشأ تلقائياً بعد أول مسح.")

    st.divider()
    st.caption(f"ماسح الحيتان v5.0 | بيانات حقيقية فقط | لا توصيات")


if __name__ == "__main__":
    main()
