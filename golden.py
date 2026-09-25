"""골든 표본 — 대표 화장실 100곳의 좌표·등급·표시 여부를 기대값으로 고정해 두고, 규칙을 고칠 때마다 확인한다.
착한가격의 "회귀 확인 문장"을 좌표판으로 옮긴 것. 규칙(주소 정제·좌표 등급·시설 매칭·개방시간·분류)을 손대면 여기서 티가 난다.
  python golden.py --make        지금 앱 데이터에서 표본 100곳을 골라 기대값 저장(data/golden.json) — 사람이 한 번 확인한 뒤 고정
  python golden.py --make-rail   역 표본만 다시 만든다(화장실 표본은 그대로 둔다)
  python golden.py           지금 앱 데이터와 기대값 비교 → 다른 곳이 있으면 종료코드 1
표본 구성: 등급(A·B·P) · 종류 · 넓은 곳·시설 위치·추정 · 시간 유형(항상/시각/확인 필요) · 도시/군을 고루 담는다.
좌표는 10m까지 같으면 통과(반올림·캐시 차이 허용), 그보다 움직이면 실패.

**역 표본도 함께 고정한다**(`app/data/rail.json`). 역은 다른 자료·다른 갱신 주기라 조용히 깨지기 쉽다 —
노선 분리(반월당 1·2호선), 기관이 여럿인 역(서울역), 개명(불암산·자양·가정중앙시장·서해구청),
자리가 같아 합친 예외(총신대입구=이수)처럼 **한 번 틀렸던 것**을 골라 둔다.
"""
import argparse, glob, json, sys
from pathlib import Path
import pandas as pd
from geocode_toilets import dist_m

ROOT = Path(__file__).parent
GOLD = ROOT / 'data' / 'golden.json'
RAIL = ROOT / 'app' / 'data' / 'rail.json'
TOL_M = 10

# 한 번씩 틀렸던 역들 — 사례지식 6-29·6-30, 버그이력 T24·T26·T27
RAIL_MUST = [
    ('대구교통공사', '1호선', '반월당'), ('대구교통공사', '2호선', '반월당'),   # 노선이 다르면 다른 화장실
    ('코레일', '경의중앙', '서울'), ('서울교통공사', '1호선', '서울'), ('서울교통공사', '4호선', '서울'),  # 기관 셋·노선 간 332m
    ('서울교통공사', '2호선', '강남'),                                          # 서울교통공사 출처(변기 수까지)
    ('대구교통공사', '1호선', '동대구'), ('대구교통공사', '1호선', '상인'),      # 처음 지적받은 곳 · 지자체와 겹침
    ('서울교통공사', '7호선', '총신대입구'),                                    # 자리가 같아 합친 예외(=이수)
    ('서울교통공사', '4호선', '불암산'), ('서울교통공사', '7호선', '자양'),      # 개명(당고개·뚝섬유원지)
    ('인천교통공사', '인천2호선', '가정중앙시장'), ('인천교통공사', '인천2호선', '서해구청'),  # 개명(가정·서구청)
    ('서울교통공사', '6호선', '태릉입구'), ('부산교통공사', '1호선', '서면'),
]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def load_app():
    recs = [r for f in glob.glob(str(ROOT / 'app' / 'data' / 't' / '*.json'))
            for r in json.loads(Path(f).read_text(encoding='utf-8'))]
    return {r['id']: r for r in recs}


def pick(app, n=100):
    """등급·종류·안내·시간 유형을 고루 섞어 표본을 고른다(같은 씨앗이면 늘 같은 표본)"""
    df = pd.DataFrame(app.values())
    df['층'] = df['g'] + '/' + df.get('w', pd.Series('', index=df.index)).fillna('') + '/' + df['h'].map(lambda h: h['k'])
    out = []
    for _, grp in df.groupby('층'):
        take = max(1, round(n * len(grp) / len(df)))
        out.append(grp.sample(min(take, len(grp)), random_state=42))
    picked = pd.concat(out).drop_duplicates('id')
    if len(picked) > n:
        picked = picked.sample(n, random_state=42)
    return sorted(picked['id'])


def load_rail():
    if not RAIL.exists():
        return {}
    d = json.loads(RAIL.read_text(encoding='utf-8'))
    return {f"{s['op']}|{s['ln']}|{s['n']}": s for s in d['s']}


def rail_snap(s):
    """역 하나의 기대값 — 좌표와 **안내의 뼈대**(층·개찰구·출구·칸 수)를 고정한다.
    상세위치 글은 원본이 다듬어질 수 있어 담지 않고, 몇 칸인지와 어느 층인지만 본다."""
    return {'이름': f"{s['ln']} {s['n']}역", 'la': s['la'], 'lo': s['lo'], 'src': s['src'], '칸': len(s['t']),
            '층': [t['f'] for t in s['t']], '개찰구': [t['g'] for t in s['t']], '출구': [t['x'] for t in s['t']]}


def pick_rail(rail, n=30):
    """한 번 틀렸던 역을 먼저 넣고, 나머지는 기관을 고루 섞어 채운다(같은 씨앗이면 늘 같은 표본)"""
    keys = [f'{o}|{l}|{s}' for o, l, s in RAIL_MUST if f'{o}|{l}|{s}' in rail]
    rest = sorted(k for k in rail if k not in keys)
    by_op = {}
    for k in rest:
        by_op.setdefault(k.split('|')[0], []).append(k)
    while len(keys) < n and any(by_op.values()):
        for op in sorted(by_op):
            if by_op[op] and len(keys) < n:
                keys.append(by_op[op].pop(len(by_op[op]) // 2))
    return keys


def snap(r):
    return {'이름': r['n'], 'la': r['la'], 'lo': r['lo'], 'g': r['g'], 'w': r.get('w', ''), 'pc': r.get('pc', ''),
            'ft': r['ft'], 't': r['t'], 'h': r['h']['k'], '주소': r['a']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--make', action='store_true')
    ap.add_argument('--make-rail', action='store_true')
    a = ap.parse_args()
    app, rail = load_app(), load_rail()
    if a.make_rail:                                   # 화장실 표본은 건드리지 않고 역만
        g = json.loads(GOLD.read_text(encoding='utf-8'))
        rkeys = pick_rail(rail)
        g['역표본'] = {k: rail_snap(rail[k]) for k in rkeys}
        GOLD.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'역 표본 {len(rkeys)}곳 저장: ' + ', '.join(g['역표본'][k]['이름'] for k in rkeys[:6]) + ' …')
        return
    if a.make:
        ids = pick(app)
        rkeys = pick_rail(rail)
        GOLD.write_text(json.dumps({'설명': '골든 표본 — 규칙을 고친 뒤 python golden.py 로 확인. 기대값을 바꿀 때는 왜 바꾸는지 버그이력에 남긴다.',
                                    '만든날': pd.Timestamp.today().strftime('%Y-%m-%d'),
                                    '표본': {i: snap(app[i]) for i in ids},
                                    '역표본': {k: rail_snap(rail[k]) for k in rkeys}}, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'골든 표본 {len(ids)}곳 + 역 {len(rkeys)}곳 저장: {GOLD.relative_to(ROOT)}')
        return
    if not GOLD.exists():
        sys.exit('골든 표본이 없습니다 → python golden.py --make')
    gold = json.loads(GOLD.read_text(encoding='utf-8'))['표본']
    diffs, gone = [], []
    for i, exp in gold.items():
        cur = app.get(i)
        if not cur:
            gone.append(f'{i} {exp["이름"]} — 이번에는 표시되지 않음')
            continue
        now = snap(cur)
        d = dist_m((exp['la'], exp['lo']), (now['la'], now['lo']))
        if d > TOL_M:
            diffs.append(f'{i} {exp["이름"]} — 좌표 {round(d)}m 이동')
        for k in ('g', 'w', 'pc', 'ft', 't', 'h'):
            if exp.get(k, '') != now.get(k, ''):
                diffs.append(f'{i} {exp["이름"]} — {k}: {exp.get(k, "")} → {now.get(k, "")}')
    rgold = json.loads(GOLD.read_text(encoding='utf-8')).get('역표본', {})
    for k, exp in rgold.items():
        cur = rail.get(k)
        if not cur:
            gone.append(f'역 {k} {exp["이름"]} — 이번에는 없음(이름이 바뀌었거나 빠졌다)')
            continue
        now = rail_snap(cur)
        d = dist_m((exp['la'], exp['lo']), (now['la'], now['lo']))
        if d > TOL_M:
            diffs.append(f'역 {exp["이름"]} — 좌표 {round(d)}m 이동')
        for f in ('src', '칸', '층', '개찰구', '출구'):
            if exp.get(f) != now.get(f):
                diffs.append(f'역 {exp["이름"]} — {f}: {exp.get(f)} → {now.get(f)}')
    for x in gone + diffs:
        print('다름:', x)
    print(f'골든 표본 {len(gold)}곳 · 역 {len(rgold)}곳 · 사라짐 {len(gone)} · 달라짐 {len(diffs)}')
    sys.exit(1 if gone or diffs else 0)


if __name__ == '__main__':
    main()
