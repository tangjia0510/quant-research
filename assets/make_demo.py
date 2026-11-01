#!/usr/bin/env python3
"""Generate deterministic synthetic daily bars; these are not market observations."""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
import random


def create_demo(destination, sessions=460, instruments=8):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    paths = [destination / n for n in ('bars.csv', 'protocol.json', 'demo-origin.json')]
    if any(p.exists() for p in paths):
        raise FileExistsError('Demo output already exists; use a new directory.')
    if sessions < 400 or instruments < 4:
        raise ValueError('Demo requires at least 400 sessions and four instruments.')
    dates = []
    date = dt.date(2019, 1, 2)
    while len(dates) < sessions:
        if date.weekday() < 5:
            dates.append(date.isoformat())
        date += dt.timedelta(days=1)
    rng = random.Random(271828)
    rows = []
    for number in range(instruments):
        price = 20.0 + number * 7.0
        symbol = f'SH{600000 + number:06d}'
        previous_return = 0.0
        for index, day in enumerate(dates):
            opening = price * math.exp(rng.gauss(0.0, 0.002))
            change = 0.0003 + 0.25 * previous_return + 0.002 * math.sin(index / 15.0 + number) + rng.gauss(0.0, 0.008)
            closing = opening * math.exp(change)
            spread = 0.003 + abs(rng.gauss(0.0, 0.002))
            rows.append({'datetime': day, 'instrument': symbol, 'open': round(opening, 6),
                         'high': round(max(opening, closing) * (1 + spread), 6),
                         'low': round(min(opening, closing) * (1 - spread), 6),
                         'close': round(closing, 6), 'volume': int(1_000_000 * (1 + rng.random())), 'factor': 1.0})
            price, previous_return = closing, change
    rows.sort(key=lambda r: (r['datetime'], r['instrument']))
    with paths[0].open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    a = sessions - 240
    config = {
        'schema_version': 1, 'mode': 'factor',
        'objective': 'Synthetic engineering demonstration; no investment validity claim.',
        'data': {'path': str(paths[0]), 'format': 'csv', 'region': 'cn', 'synthetic': True,
                 'price_basis': 'raw', 'volume_unit': 'shares',
                 'limitations': ['Synthetic prices and weekday calendar; no real market evidence.']},
        'splits': {'train': [dates[20], dates[a - 1]], 'valid': [dates[a], dates[a + 59]],
                   'discovery': [dates[a + 60], dates[a + 139]], 'final': [dates[a + 140], dates[-1]]},
        'label': {'price': 'open', 'entry_lag': 1, 'horizon': 5},
        'portfolio': {'top_k': 3, 'rebalance': 5, 'initial_cash': 100000, 'position': 0.95,
                      'buy_cost': 0.0005, 'sell_cost': 0.0015, 'min_cost': 0, 'trade_unit': 100},
        'model': {'kind': 'ridge', 'params': {'alpha': 1.0}},
        'budget': {'max_trials': 6, 'max_repairs': 2, 'timeout_seconds': 300},
        'seed': 42,
    }
    paths[1].write_text(json.dumps(config, indent=2) + '\n')
    paths[2].write_text(json.dumps({'synthetic': True, 'seed': 271828, 'sessions': sessions,
                                   'instruments': instruments, 'purpose': 'Functional verification only'}, indent=2) + '\n')
    return {'synthetic': True, 'protocol': str(paths[1]), 'bars': str(paths[0]), 'rows': len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--sessions', type=int, default=460)
    parser.add_argument('--instruments', type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(create_demo(args.output, args.sessions, args.instruments)))


if __name__ == '__main__':
    main()
