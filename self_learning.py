"""
نظام التعلم الذاتي للماسح
كل يوم يفحص أعلى 20 سهم ارتفاعاً في كل جلسة
يتعلم لماذا ارتفعت ولماذا الماسح لم يكتشفها
يحفظ الدروس ويستخدمها لتحسين الفحص القادم
"""
import json
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import os

MEMORY_FILE = 'scanner_memory.json'
RESULTS_FILE = 'scan_results.json'

EDT = timezone(timedelta(hours=-4))
SESSION_WINDOWS = {
    'premarket': ('06:30', '09:30'),
    'regular': ('09:30', '16:00'),
    'afterhours': ('16:00', '20:00'),
}


def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'lessons': [], 'patterns': {}, 'missed_signals': [], 'scan_history': []}


def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2, ensure_ascii=False, default=str)


def get_top_movers(period='5d', top_n=20):
    """Find top gainers and losers from TradingView data"""
    url = "https://scanner.tradingview.com/america/scan"
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    
    results = {'premarket': [], 'regular': [], 'afterhours': []}
    
    # Fetch top gainers
    payload = {
        "filter": [
            {"left": "close", "operation": "greater", "right": 1},
            {"left": "volume", "operation": "greater", "right": 50000},
            {"left": "change", "operation": "greater", "right": 5}
        ],
        "markets": ["america"],
        "symbols": {"query": {"types": ["stock"]}, "tickers": []},
        "columns": ["name", "close", "volume", "change", "float_shares_outstanding",
                     "high", "low", "open", "prev_close"],
        "sort": {"sortBy": "change", "sortOrder": "desc"},
        "range": [0, top_n * 2]
    }
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return results
        
        data = resp.json()
        rows = data.get('data', [])
        
        for item in rows:
            sym = item.get('s', '').split(':')[-1]
            d = item.get('d', [])
            if not sym or len(d) < 8:
                continue
            if '/' in sym or '.U' in sym:
                continue
            
            price = float(d[1] or 0)
            volume = float(d[2] or 0)
            change = float(d[3] or 0)
            float_shares = float(d[4] or 0)
            high = float(d[5] or 0)
            low = float(d[6] or 0)
            open_p = float(d[7] or 0)
            prev_close = float(d[8] or 0)
            
            if price <= 1 or volume < 50000:
                continue
            
            results['regular'].append({
                'symbol': sym,
                'price': price,
                'change_pct': change,
                'volume': volume,
                'float': float_shares,
                'high': high,
                'low': low,
                'open': open_p,
                'prev_close': prev_close,
            })
    
    except Exception as e:
        print(f"Error fetching top movers: {e}")
    
    # Sort by change and take top N
    for session in results:
        results[session].sort(key=lambda x: x['change_pct'], reverse=True)
        results[session] = results[session][:top_n]
    
    return results


def analyze_why_it_ran(symbol, stock_data):
    """Analyze why a stock ran up - look at volume, price patterns, news signals"""
    reasons = []
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Get 30 day history
        hist = ticker.history(period='1mo')
        if hist is None or len(hist) < 5:
            return ['بيانات غير كافية للتحليل']
        
        # Volume analysis
        avg_vol = hist['Volume'].mean()
        recent_vol = hist['Volume'].iloc[-1]
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 0
        
        if vol_ratio > 5:
            reasons.append(f"ارتفاع حجم تداول كبير جداً ({vol_ratio:.1f}x)")
        elif vol_ratio > 3:
            reasons.append(f"ارتفاع حجم تداول ({vol_ratio:.1f}x)")
        elif vol_ratio > 2:
            reasons.append(f"حجم تداول مرتفع ({vol_ratio:.1f}x)")
        
        # Price pattern
        close = hist['Close']
        if len(close) >= 5:
            change_5d = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]) * 100
            if change_5d > 20:
                reasons.append(f"اتجاه صاعد قوي ({change_5d:.1f}% في 5 أيام)")
            elif change_5d > 10:
                reasons.append(f"اتجاه صاعد ({change_5d:.1f}% في 5 أيام)")
        
        # Gap analysis
        if stock_data.get('open', 0) > 0 and stock_data.get('prev_close', 0) > 0:
            gap = ((stock_data['open'] - stock_data['prev_close']) / stock_data['prev_close']) * 100
            if gap > 10:
                reasons.append(f"فتح بفجوة كبيرة ({gap:.1f}%)")
            elif gap > 5:
                reasons.append(f"فتح بفجوة ({gap:.1f}%)")
        
        # Float analysis
        float_shares = stock_data.get('float', 0)
        if float_shares > 0 and float_shares < 20000000:
            reasons.append(f"عوامة صغيرة ({float_shares/1e6:.1f}M) — سهل التحرك")
        elif float_shares > 0 and float_shares < 50000000:
            reasons.append(f"عوامة متوسطة ({float_shares/1e6:.1f}M)")
        
        # Short squeeze potential
        try:
            info = ticker.info
            short_pct = info.get('shortPercentOfFloat', 0) or 0
            if short_pct > 0.20:
                reasons.append(f"شورت عالي ({short_pct*100:.0f}%) — ضغط شراء")
        except:
            pass
        
        # Price relative to 52w range
        try:
            info = ticker.info
            high_52w = info.get('fiftyTwoWeekHigh', 0) or 0
            low_52w = info.get('fiftyTwoWeekLow', 0) or 0
            current = stock_data.get('price', 0)
            if high_52w > 0 and low_52w > 0:
                position = (current - low_52w) / (high_52w - low_52w) * 100
                if position < 30:
                    reasons.append("قريب من أدنى 52 أسبوع — فرصة صعود")
                elif position > 90:
                    reasons.append("قريب من أعلى 52 أسبوع — حذر")
        except:
            pass
        
        if not reasons:
            reasons.append("حركة سعرية عامة في السوق")
    
    except Exception as e:
        reasons.append(f"خطأ في التحليل: {str(e)[:50]}")
    
    return reasons


def check_if_scanner_missed(symbol, scan_signals):
    """Check if the scanner had this stock in its signals"""
    for sig in scan_signals:
        if sig.get('symbol') == symbol:
            return False, sig.get('strategy_action', '?'), sig.get('strategy_score', 0)
    return True, 'لم يُكتشف', 0


def learn_from_today():
    """Main learning function - analyzes top movers and learns lessons"""
    print("=" * 60)
    print("  نظام التعلم الذاتي — تحليل اليوم")
    print("=" * 60)
    
    # Load current scan results
    scan_data = {}
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            scan_data = json.load(f)
    scan_signals = scan_data.get('signals', [])
    
    # Get top movers
    print("\n[1/3] جلب أعلى الأسهم ارتفاعاً...")
    top_movers = get_top_movers(top_n=20)
    
    memory = load_memory()
    today = datetime.now().strftime('%Y-%m-%d')
    
    lessons = []
    
    for session, stocks in top_movers.items():
        print(f"\n[2/3] تحليل الجلسة: {session} ({len(stocks)} أسهم)")
        
        for stock in stocks:
            sym = stock['symbol']
            change = stock['change_pct']
            
            # Check if scanner caught it
            missed, action, strat_score = check_if_scanner_missed(sym, scan_signals)
            
            # Analyze why it ran
            reasons = analyze_why_it_ran(sym, stock)
            
            lesson = {
                'date': today,
                'session': session,
                'symbol': sym,
                'price': stock['price'],
                'change_pct': change,
                'volume': stock['volume'],
                'float': stock.get('float', 0),
                'missed_by_scanner': missed,
                'scanner_action': action,
                'scanner_score': strat_score,
                'why_it_ran': reasons,
            }
            lessons.append(lesson)
            
            if missed:
                print(f"  [مفقود] {sym} +{change:.1f}% — الأسباب: {', '.join(reasons[:2])}")
            else:
                print(f"  [مكتشف] {sym} +{change:.1f}% — كان: {action} ({strat_score}%)")
    
    # Analyze patterns from missed signals
    print(f"\n[3/3] تحليل الأنماط...")
    
    missed_lessons = [l for l in lessons if l['missed_by_scanner']]
    found_lessons = [l for l in lessons if not l['missed_by_scanner']]
    
    # Find common patterns in missed signals
    missed_patterns = {}
    for lesson in missed_lessons:
        for reason in lesson['why_it_ran']:
            # Normalize reason (remove numbers)
            key = reason.split('(')[0].strip()
            missed_patterns[key] = missed_patterns.get(key, 0) + 1
    
    # Find what the scanner IS good at detecting
    found_patterns = {}
    for lesson in found_lessons:
        for reason in lesson['why_it_ran']:
            key = reason.split('(')[0].strip()
            found_patterns[key] = found_patterns.get(key, 0) + 1
    
    # Save to memory
    memory['lessons'].append({
        'date': today,
        'total_top_movers': len(lessons),
        'missed_count': len(missed_lessons),
        'found_count': len(found_lessons),
        'missed_rate': round(len(missed_lessons) / max(len(lessons), 1) * 100, 1),
        'missed_patterns': missed_patterns,
        'found_patterns': found_patterns,
        'details': lessons,
    })
    
    # Keep only last 30 days
    memory['lessons'] = memory['lessons'][-30:]
    
    # Update global patterns
    all_missed = {}
    all_found = {}
    for entry in memory['lessons']:
        for k, v in entry.get('missed_patterns', {}).items():
            all_missed[k] = all_missed.get(k, 0) + v
        for k, v in entry.get('found_patterns', {}).items():
            all_found[k] = all_found.get(k, 0) + v
    
    memory['patterns'] = {
        'common_missed': dict(sorted(all_missed.items(), key=lambda x: x[1], reverse=True)[:15]),
        'common_found': dict(sorted(all_found.items(), key=lambda x: x[1], reverse=True)[:15]),
    }
    
    # Generate improvement recommendations
    recommendations = []
    if missed_patterns:
        for pattern, count in sorted(missed_patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
            if count >= 2:
                recommendations.append(f"تحسين الكشف عن: {pattern} (لم يُكتشف {count} مرات)")
    
    memory['recommendations'] = recommendations
    
    # Scan history
    memory['scan_history'].append({
        'date': today,
        'total_signals': len(scan_signals),
        'top_movers': len(lessons),
        'missed': len(missed_lessons),
        'found': len(found_lessons),
    })
    memory['scan_history'] = memory['scan_history'][-30:]
    
    save_memory(memory)
    
    # Print summary
    print("\n" + "=" * 60)
    print(f"  ملخص التعلم — {today}")
    print(f"  أعلى 20 سهم ارتفاعاً: {len(lessons)}")
    print(f"  اكتشفها الماسح: {len(found_lessons)} ({len(found_lessons)/max(len(lessons),1)*100:.0f}%)")
    print(f"  فاتها الماسح: {len(missed_lessons)} ({len(missed_lessons)/max(len(lessons),1)*100:.0f}%)")
    print("=" * 60)
    
    if missed_patterns:
        print("\nأنماط الاخفاق:")
        for p, c in sorted(missed_patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {p}: {c} مرة")
    
    if recommendations:
        print("\nتوصيات التحسين:")
        for r in recommendations:
            print(f"  - {r}")
    
    return memory


if __name__ == "__main__":
    learn_from_today()
