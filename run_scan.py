from full_market_whale_scanner import FullMarketWhaleScanner
import json
import requests
import os
from datetime import datetime

def send_telegram(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        print("[!] Telegram not configured (no token/chat_id)")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("[+] Telegram message sent!")
            return True
        else:
            print(f"[-] Telegram error: {r.status_code}")
            return False
    except Exception as e:
        print(f"[-] Telegram error: {e}")
        return False

def format_telegram_message(signals, scan_time):
    if not signals:
        return "🐋 Whale Scanner: No signals found this scan."
    
    msg = f"<b>🐋 WHALE SCANNER - {len(signals)} Signals</b>\n"
    msg += f"<i>{scan_time}</i>\n\n"
    
    # Group by type
    types = {}
    for sig in signals:
        t = sig['type']
        if t not in types:
            types[t] = []
        types[t].append(sig)
    
    type_icons = {
        'INSIDER_CLUSTER': '👤',
        'WHALE_ACCUMULATION': '🐋',
        'VOLUME_SPIKE': '📊',
        'SHORT_SQUEEZE': '🔥',
        'PRICE_SPIKE': '🚀',
        'PRICE_CRASH': '📉',
    }
    
    for sig_type, sigs in types.items():
        icon = type_icons.get(sig_type, '📌')
        msg += f"<b>{icon} {sig_type} ({len(sigs)})</b>\n"
        for sig in sigs[:5]:  # Top 5 per type
            msg += f"  <code>{sig['symbol']}</code> ${sig.get('price', 0):.2f} | {sig['detail']}\n"
        if len(sigs) > 5:
            msg += f"  ... +{len(sigs)-5} more\n"
        msg += "\n"
    
    return msg

def main():
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{scan_time}] Starting whale scanner...")
    
    scanner = FullMarketWhaleScanner()
    signals = scanner.full_market_scan(include_insider=False)
    
    # Save results
    output = {
        'scan_time': scan_time,
        'total_signals': len(signals),
        'signals': [{k: v for k, v in sig.items() if k != 'purchases'} for sig in signals]
    }
    with open('scan_results.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"[+] Results saved to scan_results.json")
    
    # Send to Telegram
    msg = format_telegram_message(signals, scan_time)
    send_telegram(msg)
    
    print(f"[+] Scan complete: {len(signals)} signals from 5700+ stocks")

if __name__ == "__main__":
    main()
