"""위치 검증 — 좌표가 틀렸을 수 있는 곳을 찾아 단서(이름의 읍면동·카카오 장소·네이버 지역검색)로 바로잡거나 숨긴다.
대상(표시 등급 A·B·B산만):
  T11-2 필지(B) 좌표인데 카카오가 돌려준 번지가 원본 지번과 다름(`대조동 1` → `대조동 14-1`)
  T12   도로명과 지번이 300m 넘게 다른 곳을 가리킴 — 도로명이 관청 주소(부산 동구청)이거나 지번이 본국 주소(화순우체국)일 수 있어 한쪽을 늘 믿을 수 없다
판단 순서(T12): ① 이름 속 읍·면·동이 한쪽 주소에만 있으면 그쪽 ② 카카오·네이버 장소검색(이름 + 시군구) 결과가 한쪽에서 300m 안이면 그쪽
               — 두 서비스가 서로 다른 쪽을 가리키면 숨김
               ③ 단서가 없으면: 도로명을 이름이 다른 3곳 이상이 같이 쓰면(관청·대표 주소를 기본값으로 쓴 의심) 지번,
                  건물 하나를 가리키는 도로명이면 도로명 유지 + 확인 목록(action check) — 네이버 교차 확인에서 A등급 90%가 150m 안이라
                  단서 없음만으로 도심 역·지하상가까지 숨기지 않는다
판단(T11-2): 카카오·네이버 장소가 서로 150m 안에서 일치하면 그 좌표, 아니면 숨김
네이버: API HUB 지역검색(착한가격과 같은 키, 무료 월 77.5만 건) — 좌표 mapx·mapy ÷ 10^7. 구글은 결제 계정이 필요해 쓰지 않음.
검증 표본(--naver-sample N): 이름이 뚜렷한 A등급 N곳을 네이버로 찾아 우리 좌표와의 거리 분포(품질 지표)
시설 이름 기준(사용자 결정 2026-09-23): 주소가 엇갈려 판단이 안 되거나(확인 목록) 좌표를 못 구한 곳(C·X)은 화장실명·시설명으로
  카카오·네이버를 찾아 시설 좌표를 쓴다. 둘 다 일치하면 '확인', 한 곳(네이버가 더 방대)에서만 찾으면 '추정'
  → 앱에서 "시설 위치 기준(입구·안내판 확인)" / "이름으로 찾은 위치 — 정확하지 않을 수 있어요"로 고지하고 포털 장소로 연결
결과: data/location_fixes.csv (영구번호, 조치 move/hide/place, 위도, 경도, 등급, 장소명, 장소ID, 근거) — build_app_data.py가 적용
실행: python verify_locations.py [--naver-sample 300]
"""
import argparse, json, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd
import requests
from addr_util import clean, env
from geocode_toilets import by_address, dist_m, core, kakao, save_cache as save_kakao

ROOT = Path(__file__).parent
P = ROOT / 'data' / 'processed'
OUT = ROOT / 'data' / 'location_fixes.csv'
NCACHE = P / 'naver_cache.json'
NURL = 'https://naverapihub.apigw.ntruss.com/search/v1/local'
NH = {'X-NCP-APIGW-API-KEY-ID': env('NAVER_CLIENT_ID'), 'X-NCP-APIGW-API-KEY': env('NAVER_CLIENT_SECRET')}
NEAR, AGREE, CONFLICT = 300, 150, 300
_lock = threading.Lock()
_nc = json.loads(NCACHE.read_text(encoding='utf-8')) if NCACHE.exists() else {}
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def naver(q):
    """네이버 지역검색 → [(이름, 주소, 위도, 경도)]"""
    with _lock:
        if q in _nc:
            return _nc[q]
    for attempt in range(3):
        try:
            r = requests.get(NURL, headers=NH, params={'query': q, 'display': 5}, timeout=10)
            if r.status_code == 200:
                out = [(re.sub(r'<[^>]+>', '', it['title']), it.get('roadAddress') or it.get('address', ''),
                        int(it['mapy']) / 1e7, int(it['mapx']) / 1e7) for it in r.json().get('items', [])]
                with _lock:
                    _nc[q] = out
                return out
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1)); continue
            return []
        except (requests.RequestException, ValueError, KeyError):
            time.sleep(1)
    return []


def save_naver():
    with _lock:
        NCACHE.write_text(json.dumps(_nc, ensure_ascii=False), encoding='utf-8')


def sim(a, b):
    return SequenceMatcher(None, core(a), core(b)).ratio()


def place_points(name, sgg, min_sim=0.6):
    """이름으로 찾은 장소(카카오·네이버) — 이름이 비슷하고 시군구 안인 것만. [(이름, 위도, 경도, 유사도, 장소ID)]"""
    cn = re.sub(r'\d+\s*호선', '', core(name))            # '2호선 잠실역' → '잠실역'
    if len(cn) < 2:
        return [], []
    q = f'{sgg} {cn}'.strip()
    region = sgg.split()[-1] if sgg else ''
    k = [(d['place_name'], float(d['y']), float(d['x']), sim(name, d['place_name']), d['id']) for d in (kakao('keyword', q, size=5) or [])
         if sim(name, d['place_name']) >= min_sim and region in (d.get('road_address_name') or d.get('address_name') or '')]
    n = [(t, la, lo, sim(name, t), '') for t, a, la, lo in naver(q) if sim(name, t) >= min_sim and region in a]
    return k, n


TOKEN = re.compile(r'([가-힣]{2,})(?:면|읍|동)(?=[가-힣\s(]|$)')


def name_side(name, r_addr, l_addr):
    """이름 속 읍·면·동 이름(이서우체국 → 이서)이 한쪽 주소에만 있으면 그쪽"""
    toks = {m.group(1) for m in TOKEN.finditer(name)} | {m.group(1)[:-2] for m in re.finditer(r'([가-힣]{2,4}우체국|[가-힣]{2,4}파출소|[가-힣]{2,4}지구대|[가-힣]{2,4}보건진료소|[가-힣]{2,4}보건지소)', name)}
    toks = {t for t in toks if len(t) >= 2}
    in_r = any(t in r_addr for t in toks)
    in_l = any(t in l_addr for t in toks)
    return 'R' if in_r and not in_l else 'L' if in_l and not in_r else None


def side_by_places(pts, R, L):
    near_r = any(dist_m((la, lo), R) <= NEAR for _, la, lo, _, _ in pts)
    near_l = any(dist_m((la, lo), L) <= NEAR for _, la, lo, _, _ in pts)
    return 'R' if near_r and not near_l else 'L' if near_l and not near_r else None


SHARED = {}          # 도로명(괄호 뒤 제외, 공백 없앰) → 그 도로명을 쓰는 화장실 이름 수


def road_key(a):
    return re.sub(r'\s', '', re.sub(r'\([^)]*\).*$', '', a))


def check_conflict(r):
    """T12 한 곳 판단 → (조치, 위도, 경도, 근거) 또는 None(문제 없음)"""
    L = by_address(clean(r['소재지지번주소']))
    if not L or L['좌표정확도'] not in ('A', 'B', 'B산'):
        return None
    R = (float(r['위도']), float(r['경도']))
    Lp = (L['위도'], L['경도'])
    d = dist_m(R, Lp)
    if d <= CONFLICT:
        return None
    sgg = ' '.join(x for x in (r['코드시도'], r['코드시군구']) if x)
    side = name_side(r['화장실명'], r['카카오주소'] + ' ' + r['소재지도로명주소'], L['카카오주소'] + ' ' + r['소재지지번주소'])
    why = f'도로명·지번 {round(d)}m 차이'
    if side:
        why += f', 이름의 읍면동 → {"도로명" if side == "R" else "지번"}'
    else:
        k, n = place_points(r['화장실명'], sgg)
        ks, ns = side_by_places(k, R, Lp), side_by_places(n, R, Lp)
        if ks and ns and ks != ns:
            return ('hide', '', '', why + ', 카카오·네이버가 서로 다른 쪽 → 숨김')
        side = ks or ns
        if side:
            why += f', 장소검색({"카카오" if ks else ""}{"·" if ks and ns else ""}{"네이버" if ns else ""}) → {"도로명" if side == "R" else "지번"}'
    if not side:
        if SHARED.get(road_key(r['소재지도로명주소']), 1) >= 3:
            return ('move', L['위도'], L['경도'], why + f', 도로명을 {SHARED[road_key(r["소재지도로명주소"])]}곳이 같이 씀(관청·대표 주소 의심) → 지번')
        return ('check', '', '', why + ', 단서 없음 → 도로명 유지(확인 목록)')
    if side == 'R':
        return ('keep', '', '', why)
    return ('move', L['위도'], L['경도'], why)


def check_lotnum(r):
    """T11-2: 필지 좌표의 번지가 원본 지번과 다름 → 카카오·네이버 장소가 일치하면 그 좌표, 아니면 숨김"""
    m = re.search(r'(?:동|리|가)\s*(산\s*)?(\d+(?:-\d+)?)\s*$', clean(r['소재지지번주소']))
    g = re.search(r'(\d+(?:-\d+)?)\s*$', r['카카오주소'])
    if not (m and g) or m.group(2) == g.group(1):
        return None
    sgg = ' '.join(x for x in (r['코드시도'], r['코드시군구']) if x)
    k, n = place_points(r['화장실명'], sgg)
    for _, kla, klo, _, _ in k:
        for _, nla, nlo, _, _ in n:
            if dist_m((kla, klo), (nla, nlo)) <= AGREE:
                return ('move', kla, klo, f'번지 불일치({m.group(2)}→{g.group(1)}), 카카오·네이버 장소 일치')
    return ('hide', '', '', f'번지 불일치({m.group(2)}→{g.group(1)}), 장소로 확인 안 됨 → 숨김')


FAR_LIMIT, SOLO_SIM, CONTAIN_SIM = 5000, 0.7, 0.55
# 이름이 통째로 들어 있어도 '다른 종류'가 덧붙으면 다른 곳이다: 계산역 → 계산역아파트(X), 경마공원 → 경마공원역(X)
KIND_DIFF = re.compile(r'아파트|빌라|오피스텔|공인중개|부동산|학원|교습소|노인정|경로당|어린이집|유치원|약국|의원|병원|교회|성당|마트|편의점|치킨|카페|식당|분식|모텔|여관|펜션|민박|호선|정류장|정류소|터미널|역(?=\s|\d|$)')


ABBR = {'아이씨': 'IC', '제이씨': 'JC', '케이티': 'KT', '에스케이': 'SK', '지에스': 'GS', '엘지': 'LG', '씨유': 'CU'}


def contains_ok(name, place):
    """우리 이름이 상대 이름에 통째로 들어 있고(또는 그 반대), 덧붙은 말이 다른 종류가 아니면 같은 곳으로 본다
    (S-OIL 대흥주유소 = 대흥주유소, 오성IC주유소 ~ 오성아이씨주유소)"""
    a, b = core(name), core(place)
    for ko, en in ABBR.items():
        a, b = a.replace(ko, en), b.replace(ko, en)
    if not a or not b:
        return False
    if a in b:
        extra = b.replace(a, '')
    elif b in a:
        extra = a.replace(b, '')
    else:
        return False
    m = KIND_DIFF.search(extra)
    if not m:
        return True
    t = m.group(0).strip()
    return t in a or (t in ('호선', '역') and a.endswith('역'))    # 우리 이름이 이미 같은 종류면 허용(부천역 → 부천역 1호선)


ADDR_TAIL = re.compile(r'(?:\d+(?:-\d+)?)\s*(?:번지)?\s*[,(]\s*([가-힣A-Za-z0-9·\s]{2,30})$')
TAIL_JUNK = re.compile(r'^(일원|일대|인근|부근|앞|옆|뒤|번지|호|지하|층|산|외\s*\d+필지|근처)$|^[\d\s\-]+$|^[가-힣]{1,2}\s*\d+$')


def addr_facility(addr):
    """주소 끝에 붙은 시설명 — '하늘길 지하77, 김포공항역 (방화동)' → '김포공항역'"""
    a = re.sub(r'\([^)]*\)\s*$', '', str(addr or '')).strip()
    m = ADDR_TAIL.search(a)
    if not m:
        return ''
    w = re.sub(r'\s+', ' ', m.group(1)).strip()
    return '' if TAIL_JUNK.match(w) or len(w) < 3 else w


def search_terms(r):
    """찾을 이름 후보: 화장실명 → 주소에 붙은 시설명 → 도로명주소 API가 준 건물명"""
    out = [r['화장실명']]
    for a in (r['소재지도로명주소'], r['소재지지번주소']):
        w = addr_facility(a)
        if w:
            out.append(w)
    if r.get('건물명'):
        out.append(r['건물명'])
    seen, terms = set(), []
    for t in out:
        k = re.sub(r'\s', '', t)
        if k and k not in seen:
            seen.add(k)
            terms.append(t)
    return terms


def by_facility(r, anchors):
    """시설 이름으로 찾기 — 주소가 엇갈리거나 좌표를 못 구한 곳.
    카카오·네이버가 150m 안에서 일치하면 '확인', 한 곳에서만 찾으면 '추정'(앱에서 '정확하지 않을 수 있어요' 표시).
    엉뚱한 동명이소를 막으려고 원본 주소에서 5km 안(anchors)일 때만 받는다."""
    sgg = ' '.join(x for x in (r['코드시도'], r['코드시군구']) if x)
    near = lambda pt: not anchors or min(dist_m(pt, a) for a in anchors) <= FAR_LIMIT
    best_solo = None
    for ti, term in enumerate(search_terms(r)):
        if len(re.sub(r'\d+\s*호선', '', core(term))) < 3:
            continue
        where = '화장실명' if ti == 0 else '주소·건물명'
        k, n = place_points(term, sgg, min_sim=CONTAIN_SIM)
        for kt, kla, klo, ks, kid in k:
            for nt, nla, nlo, ns, _ in n:
                if ks < 0.6 or ns < 0.6:
                    continue                               # 두 곳 일치로 인정하려면 둘 다 이름이 충분히 비슷해야
                if dist_m((kla, klo), (nla, nlo)) <= AGREE and near((kla, klo)):
                    return ('place', kla, klo, '확인', kt, kid,
                            f'{where}"{term}" — 카카오·네이버가 같은 시설로 확인({round(dist_m((kla, klo), (nla, nlo)))}m 차이)')
        solo = [(t, la, lo, s, pid) for t, la, lo, s, pid in (n + k)
                if near((la, lo)) and (s >= SOLO_SIM or (s >= CONTAIN_SIM and contains_ok(term, t)))]
        if solo and best_solo is None:
            t, la, lo, s, pid = max(solo, key=lambda x: x[3])
            src = '네이버' if any(t == x[0] for x in n) else '카카오'
            best_solo = ('place', la, lo, '추정', t, pid, f'{where}"{term}" — {src}에서만 찾음(이름 유사 {s:.2f}) — 정확하지 않을 수 있음')
    return best_solo


def naver_sample(g, n):
    """품질 지표: 이름이 뚜렷한 A등급을 네이버로 찾아 거리 분포"""
    a = g[(g['좌표정확도'] == 'A') & (g['화장실명'].map(lambda x: len(core(x)) >= 4))].sample(n, random_state=11)
    def one(r):
        sgg = ' '.join(x for x in (r['코드시도'], r['코드시군구']) if x)
        hits = [(t, la, lo) for t, ad, la, lo in naver(f'{sgg} {core(r["화장실명"])}') if sim(r['화장실명'], t) >= 0.6]
        return min((dist_m((float(r['위도']), float(r['경도'])), (la, lo)) for _, la, lo in hits), default=None)

    ds = list(ThreadPoolExecutor(5).map(one, [r for _, r in a.iterrows()]))
    found = [d for d in ds if d is not None]
    b = lambda lo, hi: sum(1 for d in found if lo < d <= hi)
    print(f'\n네이버 교차 확인(A등급 무작위 {n}곳): 네이버에서 찾음 {len(found)}곳 — 50m 안 {b(-1, 50)} · 50~150m {b(50, 150)} · 150~500m {b(150, 500)} · 500m 넘음 {b(500, 1e9)}')
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--naver-sample', type=int, default=0)
    a = ap.parse_args()
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    g = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('')
    shown = g[g['좌표정확도'].isin(['A', 'B', 'B산'])]
    t12 = shown[(shown['소재지도로명주소'] != '') & (shown['소재지지번주소'] != '') & shown['조회주소종류'].eq('도로명')]
    t112 = shown[shown['좌표정확도'].isin(['B', 'B산']) & (shown['카카오주소종류'] == 'REGION_ADDR') & (shown['소재지지번주소'] != '')
                 & ~shown['조회주소종류'].eq('도로명')]
    for k, v in g[g['소재지도로명주소'] != ''].assign(rk=lambda x: x['소재지도로명주소'].map(road_key)).groupby('rk')['화장실명'].nunique().items():
        SHARED[k] = v
    print(f'검사: 도로명·지번 둘 다 있는 곳 {len(t12):,} (T12), 필지 좌표 {len(t112):,} (T11-2)')
    with ThreadPoolExecutor(6) as ex:
        r12 = list(ex.map(check_conflict, [r for _, r in t12.iterrows()]))
        r112 = list(ex.map(check_lotnum, [r for _, r in t112.iterrows()]))
    save_kakao(); save_naver()
    rows, need_place = [], []
    for src, res, kind in ((t12, r12, 'T12'), (t112, r112, 'T11-2')):
        for (_, r), x in zip(src.iterrows(), res):
            if x and x[0] == 'check':
                need_place.append((r, kind))          # 주소로 판단 못 함 → 시설 이름으로
            elif x and x[0] != 'keep':
                rows.append({'영구번호': r['영구번호'], '화장실명': r['화장실명'], '종류': kind, '조치': x[0], '위도': x[1], '경도': x[2],
                             '등급': '', '장소명': '', '장소ID': '', '근거': x[3]})
    lost = g[~g['좌표정확도'].isin(['A', 'B', 'B산'])]      # 좌표를 못 구했거나 대략인 곳(C·P·X)
    need_place += [(r, '좌표없음') for _, r in lost.iterrows()]
    print(f'시설 이름으로 찾기: 확인 목록 {sum(1 for _, k in need_place if k != "좌표없음"):,} + 좌표 없음·대략 {len(lost):,}')

    def anchors_of(r):
        pts = []
        if r['좌표정확도'] in ('A', 'B', 'B산', 'C'):
            pts.append((float(r['위도']), float(r['경도'])))
        for a in (r['소재지도로명주소'], r['소재지지번주소']):
            x = by_address(clean(a)) if a else None
            if x and x['좌표정확도'] in ('A', 'B', 'B산', 'C'):
                pts.append((x['위도'], x['경도']))
        return pts

    with ThreadPoolExecutor(6) as ex:
        found = list(ex.map(lambda t: by_facility(t[0], anchors_of(t[0])), need_place))
    save_kakao(); save_naver()
    for (r, kind), x in zip(need_place, found):
        if x:
            rows.append({'영구번호': r['영구번호'], '화장실명': r['화장실명'], '종류': kind, '조치': 'place', '위도': x[1], '경도': x[2],
                         '등급': x[3], '장소명': x[4], '장소ID': x[5], '근거': x[6]})
        elif kind != '좌표없음':
            rows.append({'영구번호': r['영구번호'], '화장실명': r['화장실명'], '종류': kind, '조치': 'check', '위도': '', '경도': '',
                         '등급': '', '장소명': '', '장소ID': '', '근거': '주소로도 시설 이름으로도 판단 못 함 → 도로명 유지(확인 목록)'})
    keep = sum(1 for x in r12 if x and x[0] == 'keep')
    out = pd.DataFrame(rows, columns=['영구번호', '화장실명', '종류', '조치', '위도', '경도', '등급', '장소명', '장소ID', '근거'])
    out.to_csv(OUT, index=False, encoding='utf-8-sig')
    check = int(((out.종류 == 'T12') & (out.조치 == 'check')).sum())
    print(f'T12 어긋남 {sum(1 for x in r12 if x):,}곳 → 도로명 유지 {keep:,}(+단서 없이 유지·확인 목록 {check:,}) · 지번으로 옮김 {int(((out.종류 == "T12") & (out.조치 == "move")).sum()):,} · 숨김 {int(((out.종류 == "T12") & (out.조치 == "hide")).sum()):,}')
    print(f'T11-2 번지 불일치 {sum(1 for x in r112 if x):,}곳 → 장소로 옮김 {int(((out.종류 == "T11-2") & (out.조치 == "move")).sum()):,} · 숨김 {int(((out.종류 == "T11-2") & (out.조치 == "hide")).sum()):,}')
    pl = out[out.조치 == 'place']
    print(f'시설 이름으로 찾음 {len(pl):,}곳 — 확인(카카오·네이버 일치) {int((pl.등급 == "확인").sum()):,} · 추정(한 곳에서만) {int((pl.등급 == "추정").sum()):,}'
          f' | 출처별: 확인 목록 {int((pl.종류 != "좌표없음").sum()):,}, 좌표 없음·대략 {int((pl.종류 == "좌표없음").sum()):,}')
    for r in pl.sample(min(6, len(pl)), random_state=5).itertuples():
        print(f'  [{r.등급}] {r.화장실명} → {r.장소명} — {r.근거}')
    for k in ('T12', 'T11-2'):
        s = out[out.종류 == k]
        for r in s.sample(min(6, len(s)), random_state=3).itertuples():
            print(f'  [{k}] {r.조치} {r.화장실명} — {r.근거}')
    if a.naver_sample:
        naver_sample(shown, a.naver_sample)
        save_naver()
    print(f'저장: {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
