#!/usr/bin/env python3
"""Generate thousands of random student profiles, run the engine on each, and audit every option returned.

    python scripts/flow_accuracy.py --n 3000 [--live]

By default the saved official feed for 2026-11-15 is used (offline, repeatable). --live fetches today's menus.
Exit code 1 if any hard-rule violation is found. Prints the numbers used on the accuracy slide.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from trojanbites_extract.flow import engine, feed, verify  # noqa: E402
from trojanbites_extract.flow.engine import Query  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures' / 'usc_feed_2026-11-15'
FEED_DAY = date(2026, 11, 15)
ALLERGENS = ['peanuts', 'tree nuts', 'dairy', 'eggs', 'gluten', 'soy', 'fish', 'shellfish', 'sesame']
CUISINES = ['indian', 'mexican', 'chinese', 'korean', 'japanese', 'italian', 'thai', 'american', 'mediterranean']


def install_offline_feed() -> None:
    def fake(key, day):
        path = FIXTURES / f'{key}.json'
        if day == FEED_DAY and path.exists():
            return f'fixture://{key}', json.loads(path.read_text()), 'live'
        return '', None, 'unavailable'
    feed.fetch_hall = fake


# None keeps the legacy max_miles path; the rest are the three bands in every combination the app can send.
BAND_SETS = [None, [(0.0, 0.3)], [(0.3, 0.5)], [(0.5, 1.5)], [(0.0, 0.3), (0.3, 0.5)],
             [(0.3, 0.5), (0.5, 1.5)], [(0.0, 0.3), (0.5, 1.5)], [(0.0, 0.3), (0.3, 0.5), (0.5, 1.5)]]


def profile(rng: random.Random, days: list[date]) -> Query:
    mode = rng.choice(['usc_dining', 'off_campus'])
    return Query(
        mode=mode, meal=rng.choice(['breakfast', 'lunch', 'dinner']), day=rng.choice(days),
        diet=rng.choice(['any', 'any', 'vegetarian', 'vegan', 'halal']), allergies=rng.sample(ALLERGENS, rng.choice([0, 0, 1, 1, 2, 3, 4])),
        goal=rng.choice(['balanced', 'lose', 'gain', 'maintain']), lat=34.0224 + rng.uniform(-0.006, 0.006), lng=-118.2851 + rng.uniform(-0.006, 0.006),
        per_meal_usd=rng.choice([None, 6, 9, 12, 18, 25]) if mode == 'off_campus' else None,
        daily_remaining_usd=rng.choice([None, 10, 20, 40]) if mode == 'off_campus' else None, meals_left=rng.choice([1, 2, 3]),
        meal_kcal=rng.choice([450, 600, 750, 900]), meal_protein_g=rng.choice([20, 30, 40, 50]), max_miles=rng.choice([None, 0.2, 0.3, 0.5, 1.0]), bands=rng.choice(BAND_SETS),
        cuisines=rng.sample(CUISINES, rng.choice([0, 0, 1, 2])), rank_by=rng.choice(['fit', 'nearest', 'cheapest', 'protein', 'lighter']),
        swipes_remaining=rng.choice([None, 0, 2, 5]), min_protein_g=rng.choice([None, None, 25]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--live', action='store_true')
    args = ap.parse_args()
    if not args.live:
        install_offline_feed()
    rng = random.Random(args.seed)
    days = [FEED_DAY] if args.live is False and False else [FEED_DAY + timedelta(days=i) for i in range(0, 7)]
    if args.live:
        days = [date.today()]
    totals = Counter()
    bad: list[tuple] = []
    started = time.time()
    for _ in range(args.n):
        q = profile(rng, days)
        result = engine.recommend(q)
        totals['runs'] += 1
        totals['options_checked'] += len(result['options'])
        totals['runs_with_3_options'] += 1 if len(result['options']) >= 3 else 0
        totals['runs_with_none'] += 1 if not result['options'] else 0
        totals['runs_with_allergies'] += 1 if q.allergies else 0
        totals['restricted_diet'] += 1 if q.diet != 'any' else 0
        problems = verify.result_violations(q, result)
        if problems:
            totals['runs_with_violations'] += 1
            bad.append((q, problems[:3]))
    print(json.dumps(dict(totals), indent=2), f'\n{time.time() - started:.1f}s')
    for q, problems in bad[:10]:
        print('VIOLATION', q.mode, q.meal, q.day, q.diet, q.allergies, problems)
    print('\nRESULT:', 'PASS - 0 violations' if not bad else f'FAIL - {len(bad)} runs with violations')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
