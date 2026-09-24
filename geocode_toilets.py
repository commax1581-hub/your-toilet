"""좌표 변환 — 카카오 주소검색(+ 장소검색 보조)으로 화장실마다 위도·경도와 좌표 정확도를 붙인다.
주소 후보 순서: 도로명주소 API 정규주소(정상일 때) → 원본 도로명 → 원본 지번. 가장 정확한 결과를 채택.
좌표 정확도 (카카오 address_type 기준):
  A 건물  ROAD_ADDR — 건물 위치
  B 필지  REGION_ADDR — 번지(필지) 위치. 건물 없는 공원·야외 화장실. '산' 번지는 넓어서 B산으로 따로
  P 장소  주소가 C 이하일 때 장소검색(시군구 + 화장실명)으로 찾은 곳 — 이름 비슷·시군구 안·C 위치 3km 안일 때만
  C 대략  ROAD(도로 가운데)·REGION(동·리 중심) — 수백 m~수 km 오차, 지도에 '위치 대략' 표시
  X 실패
결과: data/processed/toilets_geo.csv, 캐시 data/processed/kakao_cache.json
실행: python geocode_toilets.py [--limit N]
설계: ../착한식당/docs/공공데이터-파이프라인.md 6장(좌표 보정 절차)
"""
import argparse, json, math, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd
import requests
from addr_util import clean, env

ROOT = Path(__file__).parent
P = ROOT / 'data' / 'processed'
CACHE_PATH = P / 'kakao_cache.json'
BASE = 'https://dapi.kakao.com/v2/local/search/'
WORKERS = 6
GRADE = {'ROAD_ADDR': 'A', 'REGION_ADDR': 'B', 'ROAD': 'C', 'REGION': 'C'}
ORDER = {'A': 0, 'B': 1, 'B산': 2, 'P': 3, 'C': 4, 'X': 5}
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

H = {'Authorization': 'KakaoAK ' + env('KAKAO_REST_KEY')}
_lock = threading.Lock()
_cache = json.loads(CACHE_PATH.read_text(encoding='utf-8')) if CACHE_PATH.exists() else {}


def save_cache():
    with _lock:
        CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False), encoding='utf-8')


def kakao(kind, query, **extra):
    ck = f'{kind}|{query}|{json.dumps(extra, sort_keys=True)}'
    with _lock:
        if ck in _cache:
            return _cache[ck]
    for attempt in range(4):
        try:
            r = requests.get(BASE + kind + '.json', headers=H, params={'query': query, **extra}, timeout=10)
            if r.status_code == 200:
                docs = r.json()['documents']
                with _lock:
                    _cache[ck] = docs
                return docs
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1)); continue
            print('카카오 오류', r.status_code, r.text[:120], flush=True)
            return None
        except requests.RequestException:
            time.sleep(2)
    return None


def dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def core(name):
    """이름 비교용 — 화장실·공중·개방 등 흔한 말과 괄호 제거"""
    n = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', str(name))
    n = re.sub(r'공중|개방|간이|이동|화장실|남자|여자|남녀|공용|\s', '', n)
    n = re.sub(r'(입구|앞|옆|내|\d+)$', '', n)        # '○○공원 입구', '한재골 3' → 장소 이름만
    return n.replace('근린공원', '공원')


def by_address(q):
    docs = kakao('address', q, size=1) if q else []
    if not docs:
        return None
    d = docs[0]
    g = GRADE.get(d['address_type'], 'C')
    if g == 'B' and (d.get('address') or {}).get('mountain_yn') == 'Y':
        g = 'B산'
    return {'위도': float(d['y']), '경도': float(d['x']), '좌표정확도': g, '카카오주소': d['address_name'],
            '카카오주소종류': d['address_type'], '좌표출처': 'kakao_addr', '조회주소': q}


def by_place(name, sgg, near):
    cn = core(name)
    if len(cn) < 2 or not sgg:
        return None
    docs = kakao('keyword', f'{sgg} {cn}', size=5) or []
    for d in docs:
        addr = d.get('road_address_name') or d.get('address_name') or ''
        if sgg.split()[0] not in addr:
            continue
        sim = SequenceMatcher(None, cn, core(d['place_name'])).ratio()
        if sim < 0.5 and cn not in d['place_name']:
            continue
        pt = (float(d['y']), float(d['x']))
        if near and dist_m(pt, near) > 3000:
            continue
        return {'위도': pt[0], '경도': pt[1], '좌표정확도': 'P', '카카오주소': addr, '카카오주소종류': 'PLACE',
                '좌표출처': 'kakao_place', '조회주소': f'{sgg} {cn}', '카카오장소ID': d['id'],
                '카카오장소명': d['place_name'], '이름유사도': round(sim, 2)}
    return None


MT_NEAR, MT_FAR = 300, 1000             # 산지 교차 확인: 이 안이면 장소 좌표로 교체, 이보다 멀면 필지가 넓다는 신호


def check_mountain(r, best):
    """임야 필지는 넓어서 중심점이 실제 화장실과 멀 수 있다 → 화장실명 장소검색으로 교차 확인
    산지확인: 장소로 교체(300m 안) / 중간(300m~1km) / 멀리 떨어짐(1km 넘음, 숨김 후보) / 장소 없음"""
    sgg = ' '.join(x for x in (r['코드시도'], r['코드시군구']) if x)
    place = by_place(r['화장실명'], sgg, None)
    if not place:
        return {**best, '산지확인': '장소 없음'}
    d = dist_m((best['위도'], best['경도']), (place['위도'], place['경도']))
    if d <= MT_NEAR:
        return {**place, '좌표정확도': 'B산', '산지확인': '장소로 교체', '산지거리m': round(d),
                '좌표비고': f'임야 필지 {best["카카오주소"]} → 같은 이름 장소({round(d)}m)'}
    return {**best, '산지확인': '중간' if d <= MT_FAR else '멀리 떨어짐', '산지거리m': round(d),
            '카카오장소명': place['카카오장소명'], '카카오장소ID': place['카카오장소ID'],
            '장소위도': place['위도'], '장소경도': place['경도']}      # 앱에서 핀을 장소(입구·주차장 쪽) 좌표로 옮길 수 있게


def locate(r):
    cands = []
    if r['검증결과'] == '정상' and r['정규주소']:
        cands.append(r['정규주소'])
    cands += [clean(r['소재지도로명주소']), clean(r['소재지지번주소'])]
    best = None
    for q in dict.fromkeys(c for c in cands if c):
        res = by_address(q)
        if res and (best is None or ORDER[res['좌표정확도']] < ORDER[best['좌표정확도']]):
            best = res
        if best and best['좌표정확도'] == 'A':
            break
    if best is None or best['좌표정확도'] == 'C':
        sgg = ' '.join(x for x in (r['코드시도'], r['코드시군구']) if x)
        near = (best['위도'], best['경도']) if best else None
        place = by_place(r['화장실명'], sgg, near)
        if place:
            place['좌표비고'] = f'주소 결과 {best["카카오주소"]}(대략)' if best else '주소 검색 실패'
            best = place
    if best and best['좌표정확도'] == 'B산':
        best = check_mountain(r, best)
    if best is None:                     # 필지가 나뉘거나 합쳐져 번지가 없을 때: 본번 → 동·리 (둘 다 대략)
        lot = clean(r['소재지지번주소'])
        for q, note in ((re.sub(r'(\d+)-\d+\s*$', r'\1', lot), '본번 필지로 찾음'),
                        (re.sub(r'\s*(산\s*)?\d+(-\d+)?\s*$', '', lot), '동·리 중심')):
            res = by_address(q) if q != lot else None
            if res:
                return {**res, '좌표정확도': 'C', '좌표비고': note}
    return best or {'좌표정확도': 'X', '좌표출처': '', '좌표비고': '주소·장소 검색 실패'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    df = pd.read_csv(P / 'toilets_addr.csv', dtype=str, encoding='utf-8-sig').fillna('')
    if a.limit:
        df = df.head(a.limit)
    rows = df.to_dict('records')
    print(f'{len(rows):,}곳 좌표 변환', flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for r, g in zip(rows, ex.map(locate, rows)):
            out.append({**r, **g})
            done += 1
            if done % 2000 == 0:
                save_cache()
                print(f'  {done:,}/{len(rows):,}', flush=True)
    save_cache()
    cols = ['위도', '경도', '좌표정확도', '좌표출처', '카카오주소', '카카오주소종류', '조회주소', '카카오장소ID', '카카오장소명', '이름유사도', '산지확인', '산지거리m', '장소위도', '장소경도', '좌표비고']
    geo = pd.DataFrame(out).reindex(columns=list(df.columns) + [c for c in cols if c not in df.columns])
    geo.to_csv(P / 'toilets_geo.csv', index=False, encoding='utf-8-sig')

    kind = (geo['소재지도로명주소'].str.strip() != '').map({True: '도로명 있음', False: '지번만'})
    print('\n좌표 정확도 × 원본 주소 종류')
    print(pd.crosstab(geo['좌표정확도'], kind, margins=True))
    print('\n좌표 정확도 × 구분')
    print(pd.crosstab(geo['좌표정확도'], geo['구분명'], margins=True))
    print('\n산지(B산) 교차 확인', geo.loc[geo['좌표정확도'] == 'B산', '산지확인'].value_counts().to_dict())
    ok = geo[geo['좌표정확도'] != 'X']
    same = ok.groupby([ok['위도'].astype(float).round(5), ok['경도'].astype(float).round(5)]).size()
    print(f'\n같은 좌표에 2곳 이상: 좌표 {int((same > 1).sum()):,}개, 화장실 {int(same[same > 1].sum()):,}곳')
    print('저장: data/processed/toilets_geo.csv')


if __name__ == '__main__':
    main()
