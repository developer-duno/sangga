"""구별 상권 바깥 상자(km)·면적 가운데값 — 결정 0039 §1 의 수치 재현.

    python docs/research/screen-redesign-2026-10-17/measure_bbox.py

읽기만 한다(public/districts.geojson). 경도 1도 ≈ 89.7km(위도 36~37.6도) · 위도 1도 ≈ 111km.
"""
import json
import statistics
from collections import defaultdict

g = json.load(open('public/districts.geojson', encoding='utf-8'))


def bbox(coords, out):
    if isinstance(coords[0], (int, float)):
        out.append(coords)
        return
    for c in coords:
        bbox(c, out)


by = defaultdict(list)
areas = []
for f in g['features']:
    pts = []
    bbox(f['geometry']['coordinates'], pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    by[f['properties']['sigungu_code']].append((min(xs), min(ys), max(xs), max(ys)))
    if f['properties'].get('area_m2') is not None:
        areas.append(f['properties']['area_m2'])

print(f'상권 {len(areas)}개 · 면적 가운데값 {statistics.median(areas):,.0f}㎡')
rows = []
for code, bs in by.items():
    w = (max(b[2] for b in bs) - min(b[0] for b in bs)) * 89.7
    h = (max(b[3] for b in bs) - min(b[1] for b in bs)) * 111
    rows.append((code, len(bs), round(w, 1), round(h, 1)))
for code, n, w, h in sorted(rows, key=lambda r: -max(r[2], r[3])):
    print(f'{code} 상권 {n:3d}개 가로 {w:5.1f}km 세로 {h:5.1f}km')
