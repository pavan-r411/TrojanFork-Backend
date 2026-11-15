#!/usr/bin/env python3
"""Map dish photos from usc_restaurants_dataset_bundle to dishes, without touching the shared dataset.

Reads the bundle's restaurants_usc_complete_local.json and images/, keeps only photos we can stand behind, resizes them
into the frontend's assets/dishes/ folder, and writes dish_images.json (dish_id -> file, source, match). The engine
reads that file and puts `image_url` on each recommendation.

A photo is used only when ALL of these hold:
  * it is the dish itself (image_match exact_dish) or the same item from another branch of the same chain,
    never a "representative" stand-in for a different dish;
  * it came from the restaurant's own material: its official site, its own page, or its delivery-platform menu.
    User-contributed Yelp and Google Maps photos and a personal blog are left out (unclear rights, sometimes people in frame);
  * it is at least 200 px on its short side, and does not have a solid black cut-out background.

Usage: python scripts/build_dish_images.py BUNDLE_DIR [--frontend ../TrojanFork-Frontend] [--include-user-photos]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

OWN_SOURCES = {'official_chain_site', 'restaurant_site', 'delivery_menu'}
USER_SOURCES = {'yelp', 'google_maps'}
SAME_DISH = {'exact_dish', 'same_dish_other_branch'}
MIN_SIDE, MAX_SIDE, QUALITY = 200, 640, 78


def file_name(dish_id: str) -> str:
    stem = re.sub(r'[^a-z0-9]+', '-', dish_id.lower()).strip('-')[:56]
    return f'{stem}-{hashlib.md5(dish_id.encode()).hexdigest()[:6]}.jpg'


def solid_black_corners(im: Image.Image) -> bool:
    w, h = im.size
    corners = [im.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    return all(max(c) < 30 for c in corners)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('bundle', type=Path, help='unzipped usc_restaurants_dataset_bundle folder')
    ap.add_argument('--frontend', type=Path, default=Path(__file__).resolve().parents[2] / 'TrojanFork-Frontend')
    ap.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / 'dish_images.json')
    ap.add_argument('--include-user-photos', action='store_true', help='also use Yelp and Google Maps photos')
    args = ap.parse_args()

    allowed = OWN_SOURCES | (USER_SOURCES if args.include_user_photos else set())
    data = json.loads((args.bundle / 'restaurants_usc_complete_local.json').read_text(encoding='utf-8'))
    dest = args.frontend / 'assets' / 'dishes'
    dest.mkdir(parents=True, exist_ok=True)

    images: dict[str, dict] = {}
    skipped: Counter = Counter()
    for category in ('usc_dining', 'off_campus'):
        for venue in data.get(category) or []:
            for dish in venue.get('dishes') or []:
                local = str(dish.get('image_url') or '')
                if not local.startswith('images/'):
                    skipped['no local photo (placeholder or failed download)'] += 1
                    continue
                if dish.get('image_match') not in SAME_DISH:
                    skipped['stand-in photo, not this dish'] += 1
                    continue
                if dish.get('image_source') not in allowed:
                    skipped['user-contributed or personal-blog photo'] += 1
                    continue
                src = args.bundle / local
                if not src.exists():
                    skipped['file missing'] += 1
                    continue
                im = Image.open(src).convert('RGB')
                if min(im.size) < MIN_SIDE:
                    skipped['too small (under 200 px)'] += 1
                    continue
                if solid_black_corners(im):
                    skipped['solid black cut-out background'] += 1
                    continue
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
                name = file_name(dish['dish_id'])
                im.save(dest / name, 'JPEG', quality=QUALITY, optimize=True, progressive=True)
                images[dish['dish_id']] = {
                    'file': f'assets/dishes/{name}', 'source': dish['image_source'], 'match': dish['image_match'],
                    'page': dish.get('image_source_page'), 'venue': venue['restaurant_name'], 'width': im.width, 'height': im.height,
                }

    out = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'bundle': 'usc_restaurants_dataset_bundle.zip',
        'policy': 'Same-dish photos from the restaurant\'s own site or delivery menu only. See scripts/build_dish_images.py.',
        'counts': {'mapped': len(images), 'skipped': dict(skipped)},
        'images': images,
    }
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
    total = sum(f.stat().st_size for f in dest.glob('*.jpg'))
    print(f'mapped {len(images)} dishes, {total / 1e6:.1f} MB in {dest}')
    for reason, n in skipped.most_common():
        print(f'  skipped {n:4d}  {reason}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
