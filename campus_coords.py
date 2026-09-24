"""캠퍼스·단지 좌표 보정 — 여러 건물의 화장실이 정문 주소 하나(같은 좌표)에 몰린 곳을 건물 좌표로 나눈다.
몰린 곳(표시 대상, 한 좌표에 4곳 이상)을 둘로 나눈다:
  같은 건물 — 이름의 차이가 층·방향뿐(스타필드하남 3층 동측) → 핀 정확, 그대로 묶어 보여 준다
  캠퍼스·단지 — 이름이 건물마다 다름(부경대학교 한미르관, 노천극장) → 건물명 장소검색(묶음 좌표 반경 1km)
채택 조건: 장소명에 이 화장실을 가르는 부분(공통 앞부분·층·방향을 뺀 나머지, 예 '자연학습장')이 들어 있음,
          주차장·충전소 등은 이름에 그 말이 없으면 제외, 묶음 좌표에서 700m 안, 묶음 좌표와 20m 넘게 떨어짐(같은 점이면 보정 아님)
결과: data/coord_overrides.csv (영구번호 기준 — 갱신 때마다 다시 적용), 요약은 화면에
실행: python campus_coords.py
"""
import re, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd
from geocode_toilets import kakao, dist_m, save_cache

ROOT = Path(__file__).parent
OUT = ROOT / 'data' / 'coord_overrides.csv'
MIN_GROUP, RADIUS, MAX_DIST, MIN_MOVE = 4, 1000, 700, 20
# 가르는 말로 쓰기엔 너무 흔한 말(선유도공원 '야외'화장실 → 야외씨름장 오답)
WEAK = {'야외', '실내', '옥외', '외부', '내부', '간이', '임시', '공용', '고객', '직원', '신축', '구관', '별관동'}
FLOOR = re.compile(r'지상|옥상|로비|중앙|지하|\d+\s*층|[Bb]\d|[동서남북]\s*측|[동서남북]쪽|남자|여자|남녀|장애인|\d+\s*호|[\d\s()\-·,~]+')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def prefix(names):
    """이름들의 공통 앞부분"""
    p = names[0]
    for n in names[1:]:
        while not n.startswith(p):
            p = p[:-1]
    return p


def kind(names):
    """같은 건물(층·방향 말을 빼면 이름이 같음) / 캠퍼스·단지.
    공통 앞부분으로 자르면 '별내도서관지|하1층'처럼 층 말이 반으로 잘려 틀린다 → 이름마다 층 말을 먼저 뺀 뒤 비교"""
    core_names = [FLOOR.sub('', re.sub(r'\s', '', n)).replace('화장실', '') for n in names]
    top = Counter(core_names).most_common(1)[0][1]
    return '같은 건물' if top / len(names) >= 0.7 else '캠퍼스·단지'


GENERIC = re.compile(r'주차장|충전소|정류장|정류소|입구|출구|ATM|편의점|카페')


def ns(s):
    return re.sub(r'[\s()\[\]·,]', '', str(s))


def distinct(name, common):
    """묶음 안에서 이 화장실을 가르는 부분 — 공통 앞부분·층·방향·'화장실'을 뺀 나머지(괄호 안 포함)"""
    rest = ns(name)[len(common):] if ns(name).startswith(common) else ns(name)
    rest = re.sub(r'공중|개방|화장실', '', rest)
    return FLOOR.sub('', rest)


def find(row, lat, lng, key):
    """건물명 장소검색 — 장소명에 이 화장실을 가르는 부분(key)이 들어 있어야 채택"""
    if len(key) < 2 or key in WEAK:
        return None
    q = re.sub(r'\s+', ' ', re.sub(r'[()]', ' ', re.sub(r'공중|개방|화장실|\d+\s*층|지하', ' ', row['화장실명']))).strip()
    docs = kakao('keyword', q, x=f'{lng:.6f}', y=f'{lat:.6f}', radius=RADIUS, sort='accuracy', size=5) or []
    for d in docs:
        pn = d['place_name']
        if key not in ns(pn):
            continue
        if GENERIC.search(pn) and not GENERIC.search(key):
            continue
        pt = (float(d['y']), float(d['x']))
        dd = dist_m(pt, (lat, lng))
        if dd > MAX_DIST or dd < MIN_MOVE:
            continue
        sim = SequenceMatcher(None, ns(q), ns(pn)).ratio()
        return {'위도': pt[0], '경도': pt[1], '장소명': pn, '장소ID': d['id'], '이름유사도': round(sim, 2), '이동m': round(dd), '구분어': key}
    return None


def main():
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    g = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('')
    g = g[g['좌표정확도'].isin(['A', 'B'])].copy()
    g['k'] = g['위도'].astype(float).round(5).astype(str) + ',' + g['경도'].astype(float).round(5).astype(str)
    size = g['k'].map(g['k'].value_counts())
    groups = g[size >= MIN_GROUP].groupby('k')
    kinds = {k: kind(list(s['화장실명'])) for k, s in groups}
    c = Counter(kinds.values())
    n_by = Counter()
    for k, s in groups:
        n_by[kinds[k]] += len(s)
    print(f'몰린 좌표(4곳 이상) {len(kinds):,}개: ' + ', '.join(f'{t} {c[t]:,}개({n_by[t]:,}곳)' for t in c))

    targets = []
    for k, s in groups:
        if kinds[k] != '캠퍼스·단지':
            continue
        common = prefix([ns(n) for n in s['화장실명']])
        for _, r in s.iterrows():
            targets.append((r, float(r['위도']), float(r['경도']), distinct(r['화장실명'], common)))
    with ThreadPoolExecutor(6) as ex:
        found = list(ex.map(lambda t: find(*t), targets))
    save_cache()
    rows = [{'영구번호': r['영구번호'], '화장실명': r['화장실명'], '위도': f['위도'], '경도': f['경도'], '좌표정확도': 'A',
             '좌표출처': 'kakao_place_bldg', '카카오장소ID': f['장소ID'], '카카오장소명': f['장소명'], '이름유사도': f['이름유사도'],
             '사유': f'캠퍼스·단지 건물 좌표(구분어 {f["구분어"]}, 묶음 좌표에서 {f["이동m"]}m)'} for (r, _, _, _), f in zip(targets, found) if f]
    pd.DataFrame(rows).to_csv(OUT, index=False, encoding='utf-8-sig')
    print(f'캠퍼스·단지 {len(targets):,}곳 중 건물 좌표 찾음 {len(rows):,}곳 ({len(rows) / max(len(targets), 1) * 100:.1f}%)')
    print('표본:')
    for r in pd.DataFrame(rows).sample(min(15, len(rows)), random_state=1).itertuples():
        print(f'  {r.화장실명} → {r.카카오장소명} ({r.사유}, 유사도 {r.이름유사도})')
    print(f'저장: {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
