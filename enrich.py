import json
from datetime import datetime, timezone, timedelta

with open('scan_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

EDT = timezone(timedelta(hours=-4))
now_et = datetime.now(EDT)
t = now_et.hour * 60 + now_et.minute
if 390 <= t < 570:
    session = 'premarket'; sname = 'جلسة ماقبل التداول (Pre-Market)'
elif 570 <= t < 960:
    session = 'regular'; sname = 'الجلسة الرسمية (Regular)'
elif 960 <= t < 1200:
    session = 'afterhours'; sname = 'الجلسة المسائية (After-Hours)'
else:
    session = 'closed'; sname = 'السوق مغلق'

for sig in data.get('signals', []):
    sig['session'] = session
    sig_type = sig.get('type', '')
    price = sig.get('price', 0)
    s_score = sig.get('score', 0)
    
    score = 0
    reasons = []

    if sig_type == 'SHORT_SQUEEZE':
        sp = sig.get('short_percent', 0)
        days_cover = sig.get('short_ratio', 0)
        if sp > 0.30:
            score += 35; reasons.append(f"شورت عالي جداً ({sp*100:.0f}%)")
        elif sp > 0.20:
            score += 30; reasons.append(f"شورت عالي ({sp*100:.0f}%)")
        elif sp > 0.15:
            score += 25; reasons.append(f"شورت مرتفع ({sp*100:.0f}%)")
        elif sp > 0.10:
            score += 15; reasons.append(f"شورت متوسط ({sp*100:.0f}%)")
        if days_cover > 7:
            score += 25; reasons.append(f"أيام تغطية طويلة ({days_cover:.1f} يوم)")
        elif days_cover > 5:
            score += 20; reasons.append(f"أيام تغطية كافية ({days_cover:.1f} يوم)")
        elif days_cover > 3:
            score += 10
        if s_score >= 80:
            score += 20; reasons.append("إشارة سكвиз قوية جداً")
        elif s_score >= 60:
            score += 10

    elif sig_type == 'WHALE_ACCUMULATION':
        z = sig.get('zscore', 0)
        rvol = sig.get('rvol', 1)
        if z > 4.0:
            score += 40; reasons.append(f"تجميع حيتان عالي جداً (Z={z:.1f})")
        elif z > 3.0:
            score += 30; reasons.append(f"تجميع حيتان قوي (Z={z:.1f})")
        elif z > 2.0:
            score += 20; reasons.append(f"تجميع حيتان (Z={z:.1f})")
        if rvol > 5:
            score += 15; reasons.append(f"حجم نسبي عالي ({rvol:.1f}x)")

    elif sig_type == 'VOLUME_SPIKE':
        z = sig.get('zscore', 0)
        rvol = sig.get('rvol', 1)
        if z > 5:
            score += 35; reasons.append(f"ارتفاع حجم استثنائي (Z={z:.1f})")
        elif z > 4:
            score += 25; reasons.append(f"ارتفاع حجم كبير جداً (Z={z:.1f})")
        elif z > 3:
            score += 15; reasons.append(f"ارتفاع حجم (Z={z:.1f})")
        if rvol > 8:
            score += 20; reasons.append(f"الحجم النسبي مرتفع جداً ({rvol:.1f}x)")
        elif rvol > 5:
            score += 10

    elif sig_type == 'PRICE_SPIKE':
        import re
        detail = sig.get('detail', '')
        pct_match = re.search(r'([+-]?\d+\.?\d*)%', detail)
        actual_change = abs(float(pct_match.group(1))) if pct_match else abs(s_score)
        if actual_change >= 50:
            s_score = 50; reasons.append(f"اندفاع سعري ضخم ({actual_change:.0f}%)")
        elif actual_change >= 30:
            s_score = 40; reasons.append(f"اندفاع سعري كبير ({actual_change:.0f}%)")
        elif actual_change >= 20:
            s_score = 30; reasons.append(f"اندفاع سعري ({actual_change:.0f}%)")
        elif actual_change >= 15:
            s_score = 20; reasons.append(f"ارتفاع ملحوظ ({actual_change:.0f}%)")
        else:
            s_score = 10; reasons.append("حركة سعرية")
        score += s_score
        if price < 5:
            score += 15; reasons.append("سهم صغير جداً - حركة قوية")
        elif price < 20:
            score += 10; reasons.append("سهم صغير")
        elif price < 50:
            score += 5

    elif sig_type == 'PRICE_CRASH':
        import re
        detail = sig.get('detail', '')
        pct_match = re.search(r'([+-]?\d+\.?\d*)%', detail)
        actual_change = abs(float(pct_match.group(1))) if pct_match else abs(s_score)
        if actual_change >= 50:
            score += 30; reasons.append(f"انخفاض حاد ({-actual_change:.0f}%) — فرصة شراء قوية")
        elif actual_change >= 30:
            score += 25; reasons.append(f"انخفاض كبير ({-actual_change:.0f}%) — فرصة شراء")
        elif actual_change >= 20:
            score += 20; reasons.append(f"انخفاض ({-actual_change:.0f}%) — فرصة شراء")
        elif actual_change >= 15:
            score += 15; reasons.append(f"انخفاض ({-actual_change:.0f}%) — مراقبة")
        else:
            score += 5; reasons.append("انخفاض طفيف — مراقبة")
        if price < 5:
            score += 5; reasons.append("سهم صغير — تذبذب عالي")

    elif sig_type == 'INSIDER_CLUSTER':
        score += 35; reasons.append("شراء مسؤولين داخلي — إشارة قوية")
        if price < 30:
            score += 10; reasons.append("مسؤولون يشترون بسعر منخفض")

    if 0.5 < price < 2:
        score += 3; reasons.append("سهم بنسات")
    elif 2 <= price < 10:
        score += 5; reasons.append("سهم صغير — فرصة كبيرة")
    elif 10 <= price < 30:
        score += 3
    elif price >= 100:
        score -= 5; reasons.append("سهم كبير — حركة أبطأ")

    score = max(0, min(score, 100))

    if score >= 75:
        action = "شراء فوري"
    elif score >= 55:
        action = "شراء بمراقبة"
    elif score >= 35:
        action = "انتظار"
    else:
        action = "لا تشتري"

    sig['strategy_score'] = score
    sig['strategy_action'] = action
    sig['strategy_reasons'] = reasons

    # Entry levels
    if price > 0:
        if sig_type == 'SHORT_SQUEEZE':
            entry = price; sl = round(price * 0.85, 2); t1 = round(price * 1.20, 2); t2 = round(price * 1.50, 2)
        elif sig_type == 'WHALE_ACCUMULATION':
            entry = price; sl = round(price * 0.90, 2); t1 = round(price * 1.15, 2); t2 = round(price * 1.35, 2)
        elif sig_type == 'VOLUME_SPIKE':
            entry = round(price * 0.98, 2); sl = round(price * 0.92, 2); t1 = round(price * 1.10, 2); t2 = round(price * 1.25, 2)
        elif sig_type == 'PRICE_SPIKE':
            entry = round(price * 0.97, 2); sl = round(price * 0.90, 2); t1 = round(price * 1.08, 2); t2 = round(price * 1.15, 2)
        elif sig_type == 'PRICE_CRASH':
            entry = round(price * 0.95, 2); sl = round(price * 0.88, 2); t1 = round(price * 1.10, 2); t2 = round(price * 1.20, 2)
        elif sig_type == 'INSIDER_CLUSTER':
            entry = price; sl = round(price * 0.88, 2); t1 = round(price * 1.20, 2); t2 = round(price * 1.40, 2)
        else:
            entry = price; sl = round(price * 0.90, 2); t1 = round(price * 1.10, 2); t2 = round(price * 1.20, 2)
        
        rr = round((t1 - entry) / (entry - sl), 1) if entry > sl else 0
        profit_pct = round(((t1 - entry) / entry) * 100, 1) if entry > 0 else 0
        loss_pct = round(((entry - sl) / entry) * 100, 1) if entry > 0 else 0
        sig['entry_price'] = entry
        sig['stop_loss'] = sl
        sig['target1'] = t1
        sig['target2'] = t2
        sig['risk_reward'] = rr
        sig['expected_profit_pct'] = profit_pct
        sig['expected_loss_pct'] = loss_pct

data['session'] = session
data['session_name'] = sname

with open('scan_results.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False, default=str)

total = len(data.get('signals', []))
actions = {}
for s in data.get('signals', []):
    a = s.get('strategy_action', '?')
    actions[a] = actions.get(a, 0) + 1

print(f"Updated {total} signals")
for a, c in sorted(actions.items(), key=lambda x: x[1], reverse=True):
    print(f"  {a}: {c}")

print()
print("Samples:")
for s in data.get('signals', [])[:5]:
    sym = s.get('symbol', '?')
    act = s.get('strategy_action', '?')
    sc = s.get('strategy_score', 0)
    reasons = s.get('strategy_reasons', [])
    entry = s.get('entry_price', 0)
    sl = s.get('stop_loss', 0)
    t1 = s.get('target1', 0)
    print(f"  {sym}: {act} ({sc}%) | دخول=${entry} | وقف=${sl} | هدف=${t1} | {reasons}")
