"""골든 표본 — 대표 화장실 100곳의 좌표·등급·표시 여부를 기대값으로 고정해 두고, 규칙을 고칠 때마다 확인한다.
착한가격의 "회귀 확인 문장"을 좌표판으로 옮긴 것. 규칙(주소 정제·좌표 등급·시설 매칭·개방시간·분류)을 손대면 여기서 티가 난다.
  python golden.py --make    지금 앱 데이터에서 표본 100곳을 골라 기대값 저장(data/golden.json) — 사람이 한 번 확인한 뒤 고정
  python golden.py           지금 앱 데이터와 기대값 비교 → 다른 곳이 있으면 종료코드 1
표본 구성: 등급(A·B·P) · 종류 · 넓은 곳·시설 위치·추정 · 시간 유형(항상/시각/확인 필요) · 도시/군을 고루 담는다.
좌표는 10m까지 같으면 통과(반올림·캐시 차이 허용), 그보다 움직이면 실패.
"""
import argparse, glob, json, sys
from pathlib import Path
import pandas as pd
from geocode_toilets import dist_m

ROOT = Path(__file__).parent
GOLD = ROOT / 'data' / 'golden.json'
TOL_M = 10
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


def snap(r):
    return {'이름': r['n'], 'la': r['la'], 'lo': r['lo'], 'g': r['g'], 'w': r.get('w', ''), 'pc': r.get('pc', ''),
            'ft': r['ft'], 't': r['t'], 'h': r['h']['k'], '주소': r['a']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--make', action='store_true')
    a = ap.parse_args()
    app = load_app()
    if a.make:
        ids = pick(app)
        GOLD.write_text(json.dumps({'설명': '골든 표본 — 규칙을 고친 뒤 python golden.py 로 확인. 기대값을 바꿀 때는 왜 바꾸는지 버그이력에 남긴다.',
                                    '만든날': pd.Timestamp.today().strftime('%Y-%m-%d'),
                                    '표본': {i: snap(app[i]) for i in ids}}, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'골든 표본 {len(ids)}곳 저장: {GOLD.relative_to(ROOT)}')
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
    for x in gone + diffs:
        print('다름:', x)
    print(f'골든 표본 {len(gold)}곳 · 사라짐 {len(gone)} · 달라짐 {len(diffs)}')
    sys.exit(1 if gone or diffs else 0)


if __name__ == '__main__':
    main()
