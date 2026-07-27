from full_market_whale_scanner import FullMarketWhaleScanner
import json
from datetime import datetime

scanner = FullMarketWhaleScanner()
signals = scanner.full_market_scan(include_insider=False)

output = {
    'scan_time': datetime.now().isoformat(),
    'total_signals': len(signals),
    'signals': [{k: v for k, v in sig.items() if k != 'purchases'} for sig in signals]
}
with open('scan_results.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"DONE: {len(signals)} signals")
