import json
f = open('predictions.json', 'r', encoding='utf-8')
d = json.load(f)
f.close()
preds = d['predictions']
print("Top 10 predictions:")
for p in preds[:10]:
    sym = p.get('symbol', '?')
    prob = p.get('explosion_probability', 0)
    c1 = p.get('change_1d', 0)
    c5 = p.get('change_5d', 0)
    price = p.get('price', 0)
    vol = p.get('volume_ratio', 0)
    print(f"  {sym}: prob={prob}% 1d={c1:+.1f}% 5d={c5:+.1f}% price=${price:.2f} vol={vol}x")
print(f"\nAll {len(preds)} predictions")
probs = [p.get('explosion_probability', 0) for p in preds]
print(f"  Min prob: {min(probs)}%  Max: {max(probs)}%  Avg: {sum(probs)/len(probs):.1f}%")
changes = [p.get('change_1d', 0) for p in preds]
print(f"  Change 1d range: {min(changes):+.1f}% to {max(changes):+.1f}%")
print(f"\nHow many already moved >10% today?")
big_movers = [p for p in preds if abs(p.get('change_1d', 0)) > 10]
for p in big_movers:
    print(f"  {p['symbol']}: {p.get('change_1d', 0):+.1f}% 1d, prob={p.get('explosion_probability', 0)}%")
