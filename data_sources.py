"""
data_sources.py — طبقة مصادر البيانات المتعددة
===============================================
كل مصدر له دوره. عندك مصدر مجاني + تقدر تضيف مدفوع.

المصادر الحالية:
1. TradingView  — مجاني: قائمة الأسهم + سعر حي (LIVE)
2. yfinance     — مجاني: بيانات تاريخية + مؤشرات فنية
3. Finnhub      — مجاني 60 دقيقة: سعر حي + أخبار + شراء داخلي
4. Alpha Vantage— مجاني 25/يوم: أسعار + أساسيات
5. Polygon      — مدفوع $29/شهر: كل شي حي

كيف يشتغل:
- كل مصدر يطبق الدوال نفسها
- الماسح يسألك أي مصدر تبي وتستخدمه
- تقدر تدمج أكثر من مصدر — كل مصدر يكمل نقص الثاني
"""
import requests
import yfinance as yf
import pandas as pd
import time
import os
import json


# ─── الإعدادات ─────────────────────────────────────────────────

CONFIG_FILE = "data_sources_config.json"

DEFAULT_CONFIG = {
    "active_sources": ["tradingview", "yfinance"],
    "finnhub_api_key": "",
    "alpha_vantage_api_key": "",
    "polygon_api_key": "",
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  المصدر 1: TradingView — مجاني — سعر حي + قائمة
# ═══════════════════════════════════════════════════════════════

class TradingViewSource:
    """مصدر أساسي — يجلب قائمة الأسهم بأحجامها وأسعارها الحية"""
    NAME = "TradingView"
    COST = "مجاني"
    SPEED = "سريع (ثانية واحدة)"
    DATA = "سعر حي + حجم + تغيير + عوامة"

    def __init__(self):
        self.url = "https://scanner.tradingview.com/america/scan"
        self.headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

    def get_stock_list(self, min_volume=50000, limit=6000):
        """جلب كل الأسهم مع أحجامها الحية"""
        payload = {
            "filter": [
                {"left": "close", "operation": "greater", "right": 0.5},
                {"left": "volume", "operation": "greater", "right": min_volume}
            ],
            "markets": ["america"],
            "symbols": {"query": {"types": ["stock"]}, "tickers": []},
            "columns": ["name", "close", "volume", "change", "float_shares_outstanding",
                         "high", "low", "open", "average_volume_10d_calc"],
            "sort": {"sortBy": "volume", "sortOrder": "desc"},
            "range": [0, limit]
        }
        try:
            resp = requests.post(self.url, json=payload, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                stocks = []
                for item in resp.json().get("data", []):
                    sym = item.get("s", "").split(":")[-1]
                    d = item.get("d", [])
                    if sym and len(d) >= 9:
                        if '/' in sym or '.U' in sym or '.W' in sym:
                            continue
                        stocks.append({
                            'symbol': sym,
                            'price': float(d[1] or 0),
                            'volume': float(d[2] or 0),
                            'change': float(d[3] or 0),
                            'float': float(d[4] or 0),
                            'high': float(d[5] or 0),
                            'low': float(d[6] or 0),
                            'open': float(d[7] or 0),
                            'avg_volume_10d': float(d[8] or 0),
                            'source': 'tradingview',
                        })
                return stocks
        except Exception as e:
            print(f"[-] TradingView: {e}")
        return []

    def get_realtime_price(self, symbol):
        """سعر حي — من نفس القائمة"""
        stocks = self.get_stock_list(min_volume=0, limit=6000)
        for s in stocks:
            if s['symbol'] == symbol:
                return {'price': s['price'], 'volume': s['volume'], 'change': s['change']}
        return None

    def supports_historical(self): return False
    def supports_news(self): return False
    def supports_insider(self): return False
    def supports_options(self): return False


# ═══════════════════════════════════════════════════════════════
#  المصدر 2: yfinance — مجاني — بيانات تاريخية + مؤشرات
# ═══════════════════════════════════════════════════════════════

class YFinanceSource:
    """مصدر تاريخي — بيانات OHLCV + مؤشرات فنية + خيارات + بيع عَمَي"""
    NAME = "yfinance"
    COST = "مجاني"
    SPEED = "متوسط (1-3 ثانية per stock)"
    DATA = "بيانات تاريخية + RSI + Bollinger + CMF + OBV + خيارات + بيع عَمَي"

    def get_historical_data(self, symbol, period="3mo"):
        """بيانات تاريخية OHLCV"""
        try:
            df = yf.download(symbol, period=period, progress=False)
            if df is None or len(df) == 0:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except:
            return None

    def get_realtime_price(self, symbol):
        """سعر من yfinance (متأخر 15 دقيقة)"""
        try:
            h = yf.Ticker(symbol).history(period="1d")
            if len(h) > 0:
                return {
                    'price': float(h['Close'].iloc[-1]),
                    'volume': float(h['Volume'].iloc[-1]),
                    'change': float(h['Close'].iloc[-1] - h['Open'].iloc[0]) / float(h['Open'].iloc[0]) * 100,
                }
        except:
            pass
        return None

    def get_options_data(self, symbol):
        """خيارات غير عادية"""
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                return None
            unusual = []
            for exp in expirations[:3]:
                try:
                    chain = ticker.option_chain(exp)
                    for _, row in chain.calls.iterrows():
                        vol = row.get('volume', 0) or 0
                        oi = row.get('openInterest', 0) or 0
                        if oi > 0 and vol > oi * 3:
                            unusual.append({
                                'type': 'CALL', 'contract': row.get('contractSymbol', ''),
                                'expiry': exp, 'strike': row.get('strike', 0),
                                'volume': int(vol), 'open_interest': int(oi),
                                'ratio': round(vol / oi, 1),
                            })
                    for _, row in chain.puts.iterrows():
                        vol = row.get('volume', 0) or 0
                        oi = row.get('openInterest', 0) or 0
                        if oi > 0 and vol > oi * 3:
                            unusual.append({
                                'type': 'PUT', 'contract': row.get('contractSymbol', ''),
                                'expiry': exp, 'strike': row.get('strike', 0),
                                'volume': int(vol), 'open_interest': int(oi),
                                'ratio': round(vol / oi, 1),
                            })
                except:
                    continue
            if unusual:
                call_vol = sum(u['volume'] for u in unusual if u['type'] == 'CALL')
                put_vol = sum(u['volume'] for u in unusual if u['type'] == 'PUT')
                return {
                    'contracts': unusual, 'count': len(unusual),
                    'bias': 'صعودي' if call_vol > put_vol * 2 else 'هبوطي' if put_vol > call_vol * 2 else 'محايد',
                }
        except:
            pass
        return None

    def get_short_data(self, symbol):
        """بيانات بيع العَمَي"""
        try:
            info = yf.Ticker(symbol).info
            sp = info.get('shortPercentOfFloat', None)
            if sp and sp > 0:
                return {
                    'short_percent': sp,
                    'days_to_cover': info.get('shortRatio', 0),
                    'float_shares': info.get('floatShares', 0),
                }
        except:
            pass
        return None

    def get_insider_activity(self, symbol):
        """شراء المسؤولين الداخليين"""
        try:
            insider = yf.Ticker(symbol).insider_transactions
            if insider is not None and len(insider) > 0:
                buys = []
                for _, row in insider.iterrows():
                    text = str(row.get('Text', '')).lower()
                    if 'purchase' in text or 'buy' in text:
                        buys.append({
                            'insider': row.get('Insider Name', ''),
                            'title': row.get('Title', ''),
                            'date': str(row.get('Start Date', '')),
                            'shares': row.get('Shares', 0),
                            'price': row.get('Price', 0),
                            'value': row.get('Value', 0),
                        })
                if buys:
                    return {'count': len(buys), 'transactions': buys[:10],
                            'total_value': sum(b.get('value', 0) or 0 for b in buys)}
        except:
            pass
        return None

    def get_news(self, symbol):
        """أخبار"""
        try:
            news = yf.Ticker(symbol).news
            if news:
                headlines = []
                for item in news[:5]:
                    title = item.get('title', '')
                    if title:
                        headlines.append({
                            'title': title,
                            'publisher': item.get('publisher', ''),
                            'date': '',
                            'link': item.get('link', ''),
                        })
                if headlines:
                    return {'count': len(headlines), 'headlines': headlines,
                            'is_news_heavy': len(headlines) >= 3}
        except:
            pass
        return None

    def supports_historical(self): return True
    def supports_news(self): return True
    def supports_insider(self): return True
    def supports_options(self): return True


# ═══════════════════════════════════════════════════════════════
#  المصدر 3: Finnhub — مجاني 60/دقيقة — سعر حي + أخبار
# ═══════════════════════════════════════════════════════════════

class FinnhubSource:
    """مصدر ثانوي — سعر حي + أخبار + شراء داخلي"""
    NAME = "Finnhub"
    COST = "مجاني (60 طلب/دقيقة)"
    SPEED = "سريع"
    DATA = "سعر حي + أخبار + شراء داخلي + مؤسسات"

    def __init__(self, api_key=""):
        self.api_key = api_key
        self.base = "https://finnhub.io/api/v1"

    def _get(self, endpoint, params=None):
        if not self.api_key:
            return None
        try:
            p = params or {}
            p['token'] = self.api_key
            resp = requests.get(f"{self.base}{endpoint}", params=p, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return None

    def get_realtime_price(self, symbol):
        """سعر حي — من Finnhub (مجاناً)"""
        data = self._get("/quote", {"symbol": symbol})
        if data and data.get('c', 0) > 0:
            return {
                'price': data['c'],  # current price
                'change': data.get('dp', 0),  # percent change
                'open': data.get('o', 0),
                'high': data.get('h', 0),
                'low': data.get('l', 0),
                'prev_close': data.get('pc', 0),
            }
        return None

    def get_news(self, symbol):
        """أخبار من Finnhub"""
        from datetime import timedelta
        today = pd.Timestamp.now().strftime('%Y-%m-%d')
        week_ago = (pd.Timestamp.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        data = self._get("/company-news", {"symbol": symbol, "from": week_ago, "to": today})
        if data:
            headlines = []
            for item in data[:5]:
                if item.get('headline'):
                    headlines.append({
                        'title': item['headline'],
                        'publisher': item.get('source', ''),
                        'date': item.get('datetime', ''),
                        'link': item.get('url', ''),
                    })
            if headlines:
                return {'count': len(headlines), 'headlines': headlines,
                        'is_news_heavy': len(headlines) >= 3}
        return None

    def get_insider_activity(self, symbol):
        """شراء داخلي من Finnhub"""
        data = self._get("/stock/insider-transactions", {"symbol": symbol, "limit": 30})
        if data and 'data' in data:
            buys = []
            for t in data['data']:
                if t.get('transactionPrice', 0) > 0 and t.get('transactionShares', 0) > 0:
                    buys.append({
                        'insider': t.get('name', ''),
                        'title': t.get('transactionCode', ''),
                        'date': t.get('transactionDate', ''),
                        'shares': t.get('transactionShares', 0),
                        'price': t.get('transactionPrice', 0),
                        'value': t.get('transactionShares', 0) * t.get('transactionPrice', 0),
                    })
            if buys:
                return {'count': len(buys), 'transactions': buys[:10],
                        'total_value': sum(b['value'] for b in buys)}
        return None

    def get_stock_list(self, min_volume=50000, limit=6000):
        """Finnhub ما يدعم سكرينر — نرجع قائمة فاضية"""
        return []

    def supports_historical(self): return False
    def supports_news(self): return True
    def supports_insider(self): return True
    def supports_options(self): return False


# ═══════════════════════════════════════════════════════════════
#  المصدر 4: Polygon — مدفوع $29/شهر — كل شي حي
# ═══════════════════════════════════════════════════════════════

class PolygonSource:
    """مصدر متقدم — بيانات حية لكل شي"""
    NAME = "Polygon.io"
    COST = "$29/شهر (Starter)"
    SPEED = "سريع جداً"
    DATA = "سعر حي + تاريخي + خيارات + أخبار + سكرينر"

    def __init__(self, api_key=""):
        self.api_key = api_key
        self.base = "https://api.polygon.io"

    def _get(self, endpoint, params=None):
        if not self.api_key:
            return None
        try:
            p = params or {}
            p['apiKey'] = self.api_key
            resp = requests.get(f"{self.base}{endpoint}", params=p, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return None

    def get_realtime_price(self, symbol):
        """سعر حي من Polygon"""
        data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        if data and data.get('ticker'):
            t = data['ticker']
            day = t.get('day', {})
            return {
                'price': t.get('lastTrade', {}).get('p', 0),
                'volume': day.get('v', 0),
                'change': day.get('c', 0),
                'high': day.get('h', 0),
                'low': day.get('l', 0),
                'open': day.get('o', 0),
            }
        return None

    def get_historical_data(self, symbol, period="3mo"):
        """بيانات تاريخية من Polygon"""
        from datetime import datetime, timedelta
        end = datetime.now()
        if period == "1mo":
            start = end - timedelta(days=30)
        elif period == "3mo":
            start = end - timedelta(days=90)
        elif period == "6mo":
            start = end - timedelta(days=180)
        else:
            start = end - timedelta(days=30)

        data = self._get(f"/v2/aggs/ticker/{symbol}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}")
        if data and data.get('results'):
            rows = []
            for r in data['results']:
                rows.append({
                    'Date': pd.Timestamp(r['t'], unit='ms'),
                    'Open': r['o'], 'High': r['h'], 'Low': r['l'],
                    'Close': r['c'], 'Volume': r['v']
                })
            df = pd.DataFrame(rows).set_index('Date')
            return df
        return None

    def get_stock_list(self, min_volume=50000, limit=6000):
        """Polygon سكرينر"""
        data = self._get("/v3/snapshot", {
            "ticker.any_of": "",
            "market": "stocks",
            "limit": min(limit, 250),
        })
        stocks = []
        if data and 'results' in data:
            for item in data['results']:
                t = item.get('ticker', '')
                day = item.get('day', {})
                if day.get('v', 0) >= min_volume:
                    stocks.append({
                        'symbol': t,
                        'price': item.get('lastTrade', {}).get('p', 0),
                        'volume': day.get('v', 0),
                        'change': day.get('c', 0),
                        'float': 0,
                        'high': day.get('h', 0),
                        'low': day.get('l', 0),
                        'open': day.get('o', 0),
                        'avg_volume_10d': 0,
                        'source': 'polygon',
                    })
        return stocks

    def supports_historical(self): return True
    def supports_news(self): return True
    def supports_insider(self): return False
    def supports_options(self): return True


# ═══════════════════════════════════════════════════════════════
#  المنسّق — يجمع المصادر
# ═══════════════════════════════════════════════════════════════

class DataSourceManager:
    """يدير المصادر ويختار الأفضل لكل مهمة"""

    def __init__(self, config=None):
        self.config = config or load_config()
        self.sources = {}

        # مجاني — دائماً متاح
        self.sources['tradingview'] = TradingViewSource()
        self.sources['yfinance'] = YFinanceSource()

        # مدفوع — يحتاج API key
        if self.config.get('finnhub_api_key'):
            self.sources['finnhub'] = FinnhubSource(self.config['finnhub_api_key'])
        if self.config.get('polygon_api_key'):
            self.sources['polygon'] = PolygonSource(self.config['polygon_api_key'])

    def get_stock_list(self, min_volume=50000, limit=6000):
        """جلب قائمة الأسهم — يجمع من كل المصادر المتاحة"""
        all_stocks = {}

        # TradingView أولاً (الأسرع والأكبر)
        if 'tradingview' in self.sources:
            stocks = self.sources['tradingview'].get_stock_list(min_volume, limit)
            for s in stocks:
                all_stocks[s['symbol']] = s

        # Polygon يكمل القائمة
        if 'polygon' in self.sources:
            stocks = self.sources['polygon'].get_stock_list(min_volume, limit)
            for s in stocks:
                if s['symbol'] not in all_stocks:
                    all_stocks[s['symbol']] = s

        return list(all_stocks.values())

    def get_realtime_price(self, symbol):
        """سعر حي — يجرب المصادر بالترتيب"""
        # Polygon أولاً (أدق)
        if 'polygon' in self.sources:
            data = self.sources['polygon'].get_realtime_price(symbol)
            if data:
                data['source'] = 'polygon'
                return data

        # Finnhub ثاني
        if 'finnhub' in self.sources:
            data = self.sources['finnhub'].get_realtime_price(symbol)
            if data:
                data['source'] = 'finnhub'
                return data

        # TradingView ثالث
        if 'tradingview' in self.sources:
            data = self.sources['tradingview'].get_realtime_price(symbol)
            if data:
                data['source'] = 'tradingview'
                return data

        # yfinance أخيراً (متأخر)
        if 'yfinance' in self.sources:
            data = self.sources['yfinance'].get_realtime_price(symbol)
            if data:
                data['source'] = 'yfinance'
                return data

        return None

    def get_historical_data(self, symbol, period="3mo"):
        """بيانات تاريخية — Polygon أولاً ثم yfinance"""
        if 'polygon' in self.sources:
            data = self.sources['polygon'].get_historical_data(symbol, period)
            if data is not None:
                return data

        if 'yfinance' in self.sources:
            return self.sources['yfinance'].get_historical_data(symbol, period)

        return None

    def get_news(self, symbol):
        """أخبار — Finnhub أولاً ثم yfinance"""
        if 'finnhub' in self.sources:
            data = self.sources['finnhub'].get_news(symbol)
            if data:
                return data

        if 'yfinance' in self.sources:
            return self.sources['yfinance'].get_news(symbol)

        return None

    def get_insider_activity(self, symbol):
        """شراء داخلي — Finnhub أولاً ثم yfinance"""
        if 'finnhub' in self.sources:
            data = self.sources['finnhub'].get_insider_activity(symbol)
            if data:
                return data

        if 'yfinance' in self.sources:
            return self.sources['yfinance'].get_insider_activity(symbol)

        return None

    def get_options_data(self, symbol):
        """خيارات — yfinance أو Polygon"""
        if 'yfinance' in self.sources:
            return self.sources['yfinance'].get_options_data(symbol)
        return None

    def get_short_data(self, symbol):
        """بيع عَمَي — yfinance"""
        if 'yfinance' in self.sources:
            return self.sources['yfinance'].get_short_data(symbol)
        return None

    def status(self):
        """حالة المصادر"""
        result = []
        for name, source in self.sources.items():
            result.append({
                'name': source.NAME,
                'cost': source.COST,
                'speed': source.SPEED,
                'data': source.DATA,
                'active': True,
            })
        return result


# ═══════════════════════════════════════════════════════════════
#  تشغيل
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    manager = DataSourceManager()

    print("=" * 60)
    print("  مصادر البيانات — حالة")
    print("=" * 60)
    for s in manager.status():
        print(f"\n  {s['name']}")
        print(f"    التكلفة: {s['cost']}")
        print(f"    السرعة: {s['speed']}")
        print(f"    البيانات: {s['data']}")

    print("\n" + "=" * 60)
    print("  اختبار: سعر NVDA من كل المصادر")
    print("=" * 60)

    price = manager.get_realtime_price("NVDA")
    if price:
        print(f"  السعر: ${price['price']}")
        print(f"  المصدر: {price.get('source', '?')}")
    else:
        print("  فشل")

    print("\n" + "=" * 60)
    print("  اختبار: قائمة الأسهم")
    print("=" * 60)
    stocks = manager.get_stock_list(min_volume=1000000, limit=5)
    print(f"  {len(stocks)} أسهم:")
    for s in stocks[:5]:
        print(f"    {s['symbol']}: ${s['price']:.2f} حجم={int(s['volume']):,}")
