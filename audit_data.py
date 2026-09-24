"""앱 데이터 정밀 점검 — check_data.py(형식 불변조건)가 못 잡는 '내용' 문제를 숫자와 표본으로 본다. 고치지 않고 보고만.
1 건수 흐름(원본 → 표시) 검산, 시도별 표시율
2 위치: 좌표의 실제 지역(카카오 좌표→주소 표본)이 원본 시군구와 같은가 / 서로 다른 주소가 같은 좌표에 몰렸나
3 이용 가능성: 이름·시간에 폐쇄·철거·공사·사용중지 / 학교(매뉴얼: 개방 대상 아님이 많음) / 오래된 기준일
4 시설 수: 모두 0, 너무 큼, 장애인·어린이 수가 전체보다 큼
5 개방시간: 여는 시각 = 닫는 시각, 자정 넘김 표본, 아주 짧음, 확인 필요 이유
6 중복: 같은 이름 + 30m 안의 다른 번호
7 이름·주소·전화·장소 링크 형식
실행: python audit_data.py [--sample 300]   결과: data/processed/audit_<날짜>.md
"""
import argparse, glob, json, math, random, re, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import pandas as pd
from geocode_toilets import kakao, dist_m, save_cache

ROOT = Path(__file__).parent
SHORT = {'서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시', '인천': '인천광역시', '광주': '광주광역시', '대전': '대전광역시',
         '울산': '울산광역시', '세종특별자치시': '세종특별자치시', '경기': '경기도', '강원특별자치도': '강원특별자치도', '충북': '충청북도',
         '충남': '충청남도', '전북특별자치도': '전북특별자치도', '전남광주통합특별시': '전남광주통합특별시', '경북': '경상북도', '경남': '경상남도',
         '제주특별자치도': '제주특별자치도'}
CLOSED_WORDS = re.compile(r'폐쇄|철거|공사\s*중|공사로|사용\s*(중지|불가|금지)|이용\s*(중지|불가)|미운영|운영\s*중지|휴업|폐업|임시\s*폐|잠정\s*폐')
SCHOOL = re.compile(r'(초등|중|고등|특수|대안)학교|초교|중교|고교|유치원|어린이집')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def pct(n, d):
    return f'{n:,} ({n / d:.1%})' if d else '0'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', type=int, default=300)
    a = ap.parse_args()
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    raw = pd.read_csv(snap / 'toilets_raw.csv', dtype=str, encoding='utf-8-sig').fillna('')
    geo = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('')
    recs = [r for f in glob.glob(str(ROOT / 'app' / 'data' / 't' / '*.json')) for r in json.loads(Path(f).read_text(encoding='utf-8'))]
    app = pd.DataFrame(recs)
    info = geo.merge(raw[['관리번호', '데이터기준일자', '최종수정시점', '개방시간', '개방시간상세', '관리기관명']], on='관리번호').set_index('영구번호')
    app = app.join(info[['코드시도', '코드시군구', '소재지도로명주소', '소재지지번주소', '데이터기준일자', '최종수정시점', '좌표정확도', '구분명', '관리기관명']], on='id')
    n = len(app)
    out = [f'# 앱 데이터 정밀 점검 — 기준본 {snap.name}, 점검일 {date.today()}', '', f'표시 {n:,}곳 / 원본 {len(raw):,}곳', '']

    # 1 시도별 표시율
    sd_all = geo['코드시도'].replace('', '(시도 모름)').value_counts()
    sd_app = app['코드시도'].replace('', '(시도 모름)').value_counts()
    t = pd.DataFrame({'원본': sd_all, '표시': sd_app}).fillna(0).astype(int)
    t['표시율'] = (t['표시'] / t['원본']).map('{:.1%}'.format)
    out += ['## 1. 시도별 표시율', t.sort_values('원본', ascending=False).to_markdown(), '']

    # 2-1 좌표 → 주소(표본): 좌표가 원본 시군구 안에 있나
    random.seed(7)
    samp = app.sample(min(a.sample, n), random_state=7)
    mism, checked = [], 0
    for r in samp.itertuples():
        res = kakao_region(r.la, r.lo)
        if not res:
            continue
        checked += 1
        sido, sgg = res
        want_sido, want_sgg = r.코드시도, r.코드시군구
        ok_sido = not want_sido or SHORT.get(sido, sido) == want_sido or sido == want_sido
        ok_sgg = not want_sgg or want_sgg.split()[0] in sgg or sgg.split()[0] in want_sgg
        if not (ok_sido and ok_sgg):
            mism.append((r.id, r.n, f'{want_sido} {want_sgg}', f'{sido} {sgg}', r.g, r.a))
    save_cache()
    out += ['## 2. 위치', f'### 2-1. 좌표의 실제 지역 = 원본 시군구? (무작위 {checked}곳, 카카오 좌표→행정구역)',
            f'- 다른 지역: {pct(len(mism), checked)}'] + [f'  - {m[0]} {m[1]} | 원본 {m[2]} → 좌표 {m[3]} | 등급 {m[4]} | {m[5]}' for m in mism[:15]] + ['']

    # 2-2 서로 다른 주소가 같은 좌표에 몰림(같은 건물 묶음 제외: 건물관리번호·주소가 다를 때만)
    app['k'] = app['la'].astype(str) + ',' + app['lo'].astype(str)
    multi = []
    for k, s in app.groupby('k'):
        if len(s) < 2:
            continue
        addrs = set(re.sub(r'\s|\(.*?\)', '', x) for x in s['a'])
        if len(addrs) >= 3:
            multi.append((len(s), len(addrs), s['a'].iloc[0], list(s['n'][:3])))
    multi.sort(reverse=True)
    out += [f'### 2-2. 주소가 3개 이상 다른데 같은 좌표: {len(multi)}개 좌표, {sum(m[0] for m in multi):,}곳'] + \
           [f'- {m[0]}곳·주소 {m[1]}개 | {m[2]} | {", ".join(m[3])}' for m in multi[:12]] + ['']

    # 3 이용 가능성
    closed_name = app[app['n'].str.contains(CLOSED_WORDS) | app['ht'].str.contains(CLOSED_WORDS)]
    school = app[app['n'].str.contains(SCHOOL)]
    old = app[app['데이터기준일자'].str[:4] < '2022']
    out += ['## 3. 실제로 쓸 수 있나',
            f'- 이름·시간에 폐쇄·철거·공사·사용중지 등: {pct(len(closed_name), n)}'] + \
           [f'  - {r.id} {r.n} | {r.ht}' for r in closed_name.head(15).itertuples()] + \
           [f'- 학교·유치원·어린이집 이름: {pct(len(school), n)} — 구분 ' + ', '.join(f'{k} {v:,}' for k, v in school['구분명'].value_counts().items()),
            '  - 표본: ' + ', '.join(school['n'].sample(min(12, len(school)), random_state=1)),
            f'- 데이터 기준일 2022년 이전: {pct(len(old), n)} (연도별 ' + ', '.join(f'{k} {v:,}' for k, v in old['데이터기준일자'].str[:4].value_counts().sort_index().items()) + ')', '']

    # 4 시설 수
    m_t = app['m'].map(lambda v: v[0]); m_u = app['m'].map(lambda v: v[1]); f_t = app['f']
    x_m = app['x'].map(lambda v: v[0]); x_f = app['x'].map(lambda v: v[1]); c_m = app['c'].map(lambda v: v[0]); c_f = app['c'].map(lambda v: v[1])
    total = m_t + m_u + f_t
    zero = app[total == 0]
    huge = app[(m_t > 50) | (m_u > 50) | (f_t > 80)]
    acc_over = app[(x_m > m_t + m_u) | (x_f > f_t)]
    child_over = app[(c_m > m_t + m_u) | (c_f > f_t)]
    male_only = app[(f_t == 0) & (m_t + m_u > 0)]
    female_only = app[(m_t + m_u == 0) & (f_t > 0)]
    out += ['## 4. 시설 수',
            f'- 변기 수가 모두 0(정보 없음일 가능성): {pct(len(zero), n)} — 구분 ' + ', '.join(f'{k} {v:,}' for k, v in zero['구분명'].value_counts().items()),
            f'- 여성 0·남성만 있음: {pct(len(male_only), n)} / 남성 0·여성만: {pct(len(female_only), n)} (남녀 공용 1칸일 수 있음)',
            f'- 아주 큰 값(남 대·소 50 넘음 또는 여 80 넘음): {len(huge):,}곳'] + [f'  - {r.id} {r.n} 남{r.m} 여{r.f}' for r in huge.head(8).itertuples()] + \
           [f'- 장애인용이 전체보다 많음: {len(acc_over):,}곳 · 어린이용이 전체보다 많음: {len(child_over):,}곳 (장애인·어린이 칸을 따로 센 입력일 수 있음)', '']

    # 5 개방시간
    H = app['h']
    kinds = Counter(h['k'] for h in H)
    same, short, over, days0 = [], [], [], 0
    for r, h in zip(app.itertuples(), H):
        if h['k'] != 'h':
            continue
        for mask, o, c in h['r']:
            om, cm = int(o[:2]) * 60 + int(o[2:]), int(c[:2]) * 60 + int(c[2:])
            if om == cm:
                same.append((r.id, r.n, r.ht))
            dur = (cm - om) % 1440
            if 0 < dur < 120:
                short.append((r.id, r.n, r.ht))
            if cm < om:
                over.append((r.id, r.n, r.ht))
    out += ['## 5. 개방시간', f'- 항상 {kinds["a"]:,} · 시각 {kinds["h"]:,} · 확인 필요 {kinds["u"]:,}',
            f'- 여는 시각 = 닫는 시각: {len(same)}'] + [f'  - {x[0]} {x[1]} | {x[2]}' for x in same[:6]] + \
           [f'- 2시간 미만: {len(short)}'] + [f'  - {x[0]} {x[1]} | {x[2]}' for x in short[:8]] + \
           [f'- 자정 넘김(닫는 시각 < 여는 시각): {len(over)} — 표본(거꾸로 입력 의심 확인용)'] + [f'  - {x[0]} {x[1]} | {x[2]}' for x in over[:10]] + ['']

    # 6 중복: 같은 이름 + 30m 안
    by_name = defaultdict(list)
    for r in app.itertuples():
        by_name[re.sub(r'\s', '', r.n)].append(r)
    dup = []
    for nm, rs in by_name.items():
        if len(rs) < 2:
            continue
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                d = dist_m((rs[i].la, rs[i].lo), (rs[j].la, rs[j].lo))
                if d <= 30:
                    dup.append((rs[i].id, rs[j].id, rs[i].n, round(d), rs[i].a == rs[j].a))
    out += ['## 6. 중복 의심(같은 이름 + 30m 안의 다른 번호)', f'- {len(dup):,}쌍 (주소까지 같은 쌍 {sum(1 for x in dup if x[4]):,})'] + \
           [f'  - {x[0]}·{x[1]} {x[2]} {x[3]}m {"주소 같음" if x[4] else ""}' for x in dup[:12]] + ['']

    # 7 형식
    generic = app[app['n'].str.replace(r'\s', '', regex=True).str.fullmatch(r'(공중|개방|간이)?화장실\d*|공중화장실\(?\d*\)?|화장실')]
    longn = app[app['n'].str.len() > 30]
    tel_bad = app[(app['tel'] != '') & ~app['tel'].str.fullmatch(r'[\d\-\s()]{7,20}')]
    place_bad = app[app.get('p', pd.Series('', index=app.index)).fillna('').astype(str).str.fullmatch(r'\d+|') == False]
    out += ['## 7. 이름·주소·전화·링크 형식',
            f'- 이름이 "화장실"뿐이라 알아보기 어려움: {pct(len(generic), n)} — 표본: ' + ', '.join(generic['a'].head(5)),
            f'- 이름 30자 넘음: {len(longn):,} — 예: ' + ' / '.join(longn['n'].head(3)),
            f'- 전화 형식 이상: {len(tel_bad):,} — 예: ' + ', '.join(tel_bad['tel'].head(6)),
            f'- 카카오 장소 ID 형식 이상: {len(place_bad):,}', '']

    dst = ROOT / 'data' / 'processed' / f'audit_{date.today():%Y%m%d}.md'
    dst.write_text('\n'.join(out), encoding='utf-8')
    print('\n'.join(out))
    print(f'\n저장: {dst.relative_to(ROOT)}')


def kakao_region(la, lo):
    """좌표 → (시도, 시군구) — 카카오 좌표→행정구역(캐시)"""
    import requests
    from geocode_toilets import H, _cache, _lock, CACHE_PATH
    ck = f'coord2region|{la:.5f},{lo:.5f}'
    with _lock:
        if ck in _cache:
            return _cache[ck]
    try:
        r = requests.get('https://dapi.kakao.com/v2/local/geo/coord2regioncode.json', headers=H, params={'x': lo, 'y': la}, timeout=10)
        docs = r.json().get('documents', [])
        b = next((d for d in docs if d.get('region_type') == 'B'), docs[0] if docs else None)
        res = (b['region_1depth_name'], b['region_2depth_name']) if b else None
    except Exception:
        return None
    with _lock:
        _cache[ck] = res
    return res


if __name__ == '__main__':
    main()
