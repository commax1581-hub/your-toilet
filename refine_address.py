"""주소 정제 — 도로명주소 API로 화장실 주소를 검증·표준화하고 건물관리번호를 붙인다.
1) 개방자치단체코드 → 시도·시군구 표(주소가 온전한 행에서 가장 많은 값) — 결과 지역 검증과 주소 앞 보충에 쓴다
2) 도로명주소로 조회 → 정상이 아니면 지번주소로 조회 → 더 나은 결과 채택
3) 결과: data/processed/toilets_addr.csv (화장실 1행 = 1줄), 요약은 화면에
실행: python refine_address.py [--limit N]   (N: 시험용으로 앞 N곳만)
"""
import argparse, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import addr_util as au

ROOT = Path(__file__).parent
WORKERS = 6
RANK = {'정상': 0, '모호': 1, '지역불일치': 2, '주소없음': 3, '조회실패': 4, '': 5}
SIDO = ['서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시', '대전광역시', '울산광역시', '세종특별자치시', '경기도',
        '강원특별자치도', '충청북도', '충청남도', '전북특별자치도', '전남광주통합특별시', '경상북도', '경상남도', '제주특별자치도']
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def region_of(addr):
    """온전한 주소에서 (시도, 시군구). '창원시 성산구'처럼 시+구는 둘 다"""
    t = str(addr).split()
    if len(t) < 2 or t[0] not in SIDO:
        return None
    sgg = t[1]
    if sgg.endswith('시') and len(t) > 2 and t[2].endswith('구'):
        sgg += ' ' + t[2]
    return t[0], (sgg if sgg[-1] in '시군구' else '')


def code_regions(df, addr):
    """자치단체코드 → (시도, 시군구). 시군구가 80% 미만으로 갈리면(시도 본청 등) 시군구는 비운다"""
    out = {}
    for code, g in addr.groupby(df['개방자치단체코드']):
        regs = [r for r in g.map(region_of) if r]
        if not regs:
            out[code] = ('', '')
            continue
        (sd, sg), n = Counter(regs).most_common(1)[0]
        sido_n = Counter(r[0] for r in regs).most_common(1)[0]
        out[code] = (sido_n[0] if sido_n[1] / len(regs) >= 0.8 else '', sg if n / len(regs) >= 0.8 else '')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    src = max((ROOT / 'data' / 'raw').glob('toilets_*.csv'))
    df = pd.read_csv(src, dtype=str, encoding='utf-8-sig').fillna('')
    road, lot = df['소재지도로명주소'].str.strip(), df['소재지지번주소'].str.strip()
    regions = code_regions(df, road.where(road != '', lot))
    if a.limit:
        df, road, lot = df.head(a.limit), road.head(a.limit), lot.head(a.limit)
    df['코드시도'] = df['개방자치단체코드'].map(lambda c: regions[c][0])
    df['코드시군구'] = df['개방자치단체코드'].map(lambda c: regions[c][1])

    # 1차: 도로명(없으면 지번) / 2차: 1차가 정상이 아니고 지번이 따로 있으면 지번
    first = road.where(road != '', lot)
    jobs = set(zip(df['코드시도'], df['코드시군구'], first))
    print(f'{src.name} {len(df):,}곳, 1차 조회 주소 {len(jobs):,}개')

    def run(jobs):
        res, done = {}, 0
        with ThreadPoolExecutor(WORKERS) as ex:
            for k, r in zip(jobs, ex.map(lambda j: au.lookup(j[2], j[0], j[1]), jobs)):
                res[k] = r
                done += 1
                if done % 2000 == 0:
                    au.save_cache()
                    print(f'  {done:,}/{len(jobs):,}', flush=True)
        au.save_cache()
        return res

    jobs = list(jobs)
    r1 = run(jobs)
    k1 = list(zip(df['코드시도'], df['코드시군구'], first))
    need2 = [(i, (s, g, l)) for i, (k, s, g, l, rd) in enumerate(zip(k1, df['코드시도'], df['코드시군구'], lot, road))
             if r1[k]['검증결과'] != '정상' and rd and l]
    jobs2 = list({k for _, k in need2})
    print(f'2차(지번) 조회 주소 {len(jobs2):,}개')
    r2 = run(jobs2)

    rows = []
    second = dict(need2)
    for i, k in enumerate(k1):
        best, used = r1[k], '도로명' if road.iloc[i] else '지번'
        if i in second:
            alt = r2[second[i]]
            if RANK[alt['검증결과']] < RANK[best['검증결과']]:
                best, used = alt, '지번(2차)'
        rows.append({**{c: df[c].iloc[i] for c in ['개방자치단체코드', '관리번호', '구분명', '화장실명', '소재지도로명주소',
                                                  '소재지지번주소', '코드시도', '코드시군구']},
                     '조회주소종류': used, **{c: v for c, v in best.items() if c != '조회'}})
    out = pd.DataFrame(rows)
    dst = ROOT / 'data' / 'processed' / 'toilets_addr.csv'
    out.to_csv(dst, index=False, encoding='utf-8-sig')

    kind = (df['소재지도로명주소'].str.strip() != '').map({True: '도로명 있음', False: '지번만'}).values
    print('\n검증결과 × 원본 주소 종류')
    print(pd.crosstab(out['검증결과'], kind, margins=True))
    print('\n채택 경로', out['조회주소종류'].value_counts().to_dict())
    print(f'건물관리번호 있음 {(out["건물관리번호"] != "").sum():,} / {len(out):,}')
    print(f'저장: {dst.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
