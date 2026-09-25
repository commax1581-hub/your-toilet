"""앱 데이터 만들기 — 가장 최근 기준본에 표시 기준·보정·개방시간 구조를 적용해, 휴대폰이 필요한 칸만 받는 지도 칸(타일) 파일로 쓴다.
표시 기준(docs/사례지식.md 1-4·1-5·2-2·2-10):
  구분 공중·개방·간이·이동(이동은 '이동식 — 위치가 바뀔 수 있어요' 안내) / 개방시간 미개방 숨김(hours.parse → closed) / 좌표 A·B·B산만(P·C·X 숨김)
  학교·유치원·어린이집 숨김(외부인 출입 제한, 개방 대상 아님) / 폐쇄가 분명한 곳 숨김 / 위치 검증에서 숨김(data/location_fixes.csv)
중복 등록: 이름·좌표·시설 수·시간이 모두 같으면 카드 하나(대표 번호 id, 나머지 번호는 ids)
보정: 캠퍼스·단지 건물 좌표(data/coord_overrides.csv, 영구번호 기준)
시설 이름 기준(P): 주소로 판단 못 하거나 좌표를 못 구한 곳을 화장실명·시설명으로 카카오·네이버에서 찾음 → w='F'(시설 위치 기준),
  pc=1 두 곳 확인 / pc=0 한 곳에서만(앱에 "정확하지 않을 수 있어요"), 포털 장소 링크 p
넓은 곳 표시: B산 → 'M'(산지에 있음), 넓은 이름의 B 필지·건물 좌표를 못 찾은 캠퍼스·단지 → 'W'(넓은 곳) — 카드에 "주차장·입구 쪽 확인" 안내
장소 링크(카카오 장소 ID): 캠퍼스 건물 보정, 산지 300m 안 교체, 산지 중간·멀리는 이름 유사 0.8 이상이고 엉뚱한 종류가 아닐 때만
분류 축(2026-09-23 결정): 시설 종류 ft(역·공원·주유소 등 15종 + 민간시설·공공시설), 안전 bl·cc(비상벨·CCTV → '안심' 필터),
  개찰구 gt(1 안=교통카드 필요 / 0 밖), 정보 기준 연도 dy, 규모는 변기 수로 앱이 계산(1~2칸이면 "한 칸뿐일 수 있어요")
나누기: 약 5km 지도 칸(위도·경도 0.05도) — 앱은 기준점이 든 칸과 둘레 8칸만 받는다(시도 경계 걱정 없음)
결과: app/data/index.json(칸 목록·건수·기준일), app/data/t/<행>_<열>.json
실행: python build_app_data.py
"""
import json, math, re, shutil, sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd
import build_registry as br
from campus_coords import kind, MIN_GROUP
from geocode_toilets import core
from hours import parse as parse_hours
from report_geo import WIDE

ROOT = Path(__file__).parent
OUT = ROOT / 'app' / 'data'
TILE = 0.05
KIND = {'공중화장실': 0, '개방화장실': 1, '간이화장실': 2, '이동화장실': 3}   # 이동식도 표시하되 '위치가 바뀔 수 있어요'(사용자 결정 2026-09-23)
SCHOOL = re.compile(r'(초등|중|고등|특수|대안|여자중|여자고등|공업고등|상업고등)학교|유치원|어린이집')
SCHOOL_NEAR = re.compile(r'(학교|초교|중교|고교|유치원|어린이집)\s*(뒤|앞|옆|인근|부근|입구|사거리|삼거리|건너편|맞은편|주변|방면)')
SCHOOL_ABBR = re.compile(r'[가-힣]{2,}(초|중|고|여중|여고|공고|상고)(\(|\s|$)')
SCHOOL_ORG = re.compile(r'(초등|중|고등|특수)학교|유치원|어린이집|교육청|교육지원청')
SCHOOL_ORG_ONLY = re.compile(r'(초등|중|고등|특수)학교|유치원|어린이집')
# 시설 종류 사전은 data/classify.json 한 곳(착한가격 분류-검색매핑 원칙) — 여기서는 읽기만
CLASSIFY = json.loads((Path(__file__).parent / 'data' / 'classify.json').read_text(encoding='utf-8'))
FTYPES = [(t['이름'], t['규칙']) for t in CLASSIFY['종류']]
FALLBACK = CLASSIFY['대체']
GATE = re.compile(r'개찰구\s*(안|내부)|게이트\s*안')
GATE_OUT = re.compile(r'개찰구\s*(밖|외부)|게이트\s*밖')
OIL = re.compile(r'주유소|충전소|가스충전|셀프주유')   # 법 제3조 제11·12호 설치 의무 대상 — 사무실 안쪽·뒤편인 경우가 많아 카드에 안내
CLOSED = re.compile(r'폐쇄|철거|공사\s*중|사용\s*(중지|불가|금지)|이용\s*(중지|불가)|개방\s*X|운영\s*중지|임시\s*폐|잠정\s*폐')
SEASONAL = re.compile(r'동절기|하절기|\d+\s*~\s*\d+\s*월|겨울|여름|시즌')
GENERIC_PLACE = re.compile(r'사무소|주민센터|행정복지|식당|여관|모텔|펜션|마트|슈퍼|교회|충전소|주유소|정류장|편의점')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def days_mask(days):
    return sum(1 << d for d in days)


def hours_compact(code, detail):
    """앱용 짧은 개방시간: {'k':'a'} 항상 / {'k':'h','r':[[요일비트,'0900','1800'],...],'hd':..,'br':..,'dw':요일비트} / {'k':'u'} 확인 필요
    dw = 원문이 직접 말한 요일(매일·평일·주말·토·일). 앱은 주말·공휴일에 이 말을 시설 종류 규칙보다 먼저 본다."""
    p = parse_hours(code, detail)
    if p['kind'] == 'always':
        return {'k': 'a'}, p
    if p['kind'] == 'hours':
        h = {'k': 'h', 'r': [[days_mask(r['days']), r['open'].replace(':', ''), r['close'].replace(':', '')] for r in p['rules'] if r['days']]}
        if p['holiday'] is not None:
            h['hd'] = [[r['open'].replace(':', ''), r['close'].replace(':', '')] for r in p['holiday']]
        if p['breaks']:
            h['br'] = [[b['from'].replace(':', ''), b['to'].replace(':', '')] for b in p['breaks']]
        if p.get('irregular'):
            h['ir'] = 1                              # 원본 코드는 '불규칙' — 적힌 시각을 따르되 카드에 고지한다
        if p.get('said'):
            h['dw'] = days_mask(p['said'])           # 원문이 직접 말한 요일 — 앱이 주말·공휴일에 이 말을 우선한다
        short = any(((int(c[:2]) * 60 + int(c[2:])) - (int(o[:2]) * 60 + int(o[2:]))) % 1440 in range(1, 5) for _, o, c in h['r'])
        return (h if h['r'] and not short else {'k': 'u'}), p     # '00:00~00:01'처럼 말이 안 되는 짧은 시간은 확인 필요
    return {'k': 'u'}, p


def ftype(name, owner):
    """시설 종류 — 이름으로 찾고, 안 잡히면 소유 구분으로 채운다(민간 건물 개방 등)"""
    for t, rx in FTYPES:
        if re.search(rx, name):
            return t
    return FALLBACK['민간'] if owner == '민간' else FALLBACK['기타']


def is_school(name, org):
    """초·중·고·특수학교·유치원·어린이집(대학교·교육청 청사·학교 근처 화장실은 제외)"""
    if SCHOOL_NEAR.search(name):
        return False
    return bool(SCHOOL.search(name) or (SCHOOL_ABBR.search(name) and SCHOOL_ORG.search(org)) or SCHOOL_ORG_ONLY.search(org))


def is_closed(name, hours_text):
    """이름·시간에 폐쇄가 분명한 곳(계절에 따른 폐쇄는 '시간 확인'으로 두고 숨기지 않음)"""
    text = f'{name} {hours_text}'
    return bool(CLOSED.search(text)) and not SEASONAL.search(text)


def place_ok(r):
    """카카오 장소 링크를 붙여도 되는가"""
    if not r['카카오장소ID']:
        return False
    if r['좌표출처'] == 'kakao_place_bldg' or r['산지확인'] == '장소로 교체':
        return True
    if r['산지확인'] in ('중간', '멀리 떨어짐'):
        sim = SequenceMatcher(None, core(r['화장실명']), core(r['카카오장소명'])).ratio()
        return sim >= 0.8 and not GENERIC_PLACE.search(r['카카오장소명'])
    return False


def main():
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    geo = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('')
    raw = pd.read_csv(snap / 'toilets_raw.csv', dtype=str, encoding='utf-8-sig').fillna('')
    df = geo.merge(raw.drop(columns=['개방자치단체코드', '구분명', '화장실명', '소재지도로명주소', '소재지지번주소']), on='관리번호', how='left')
    n0 = len(df)

    # 캠퍼스·단지 건물 좌표 보정(영구번호 기준)
    ovr_path = ROOT / 'data' / 'coord_overrides.csv'
    ovr = pd.read_csv(ovr_path, dtype=str, encoding='utf-8-sig').fillna('').set_index('영구번호') if ovr_path.exists() else pd.DataFrame()
    fixed = df['영구번호'].isin(ovr.index)
    for c in ['위도', '경도', '좌표출처', '카카오장소ID', '카카오장소명']:
        df.loc[fixed, c] = df.loc[fixed, '영구번호'].map(ovr[c])

    # 위치 검증(verify_locations.py): 옮김 / 숨김
    fx_path = ROOT / 'data' / 'location_fixes.csv'
    fx = pd.read_csv(fx_path, dtype=str, encoding='utf-8-sig').fillna('') if fx_path.exists() else pd.DataFrame(columns=['영구번호', '조치', '위도', '경도'])
    mv = fx[fx['조치'] == 'move'].set_index('영구번호')
    hide_loc = set(fx.loc[fx['조치'] == 'hide', '영구번호'])
    moved = df['영구번호'].isin(mv.index)
    df.loc[moved, '위도'] = df.loc[moved, '영구번호'].map(mv['위도'])
    df.loc[moved, '경도'] = df.loc[moved, '영구번호'].map(mv['경도'])
    # 시설 이름으로 찾은 곳: 주소가 엇갈리거나 좌표를 못 구한 곳 → 시설 좌표(등급 P). 앱에서 "시설 위치 기준"으로 고지
    pl = fx[fx['조치'] == 'place'].set_index('영구번호') if '등급' in fx.columns else pd.DataFrame()
    byfac = df['영구번호'].isin(pl.index)
    if len(pl):
        for c, col in (('위도', '위도'), ('경도', '경도'), ('카카오장소ID', '장소ID'), ('카카오장소명', '장소명')):
            df.loc[byfac, c] = df.loc[byfac, '영구번호'].map(pl[col])
        df.loc[byfac, '좌표정확도'] = 'P'
        df.loc[byfac, '시설확신'] = df.loc[byfac, '영구번호'].map(pl['등급'])

    # 표시 기준
    reasons = Counter()
    keep = []
    hrs = {}
    for i, r in df.iterrows():
        h, p = hours_compact(r['개방시간'], r['개방시간상세'])
        hrs[i] = h
        if r['구분명'] not in KIND:
            reasons['구분 없음'] += 1
        elif p['kind'] == 'closed':
            reasons['미개방'] += 1
        elif r['좌표정확도'] not in ('A', 'B', 'B산', 'P'):
            reasons[f'좌표 {r["좌표정확도"]}'] += 1
        elif r['영구번호'] in hide_loc:
            reasons['위치 검증 숨김'] += 1
        elif is_school(r['화장실명'], r['관리기관명']):
            reasons['학교·유치원·어린이집'] += 1
        elif is_closed(r['화장실명'], r['개방시간상세']):
            reasons['폐쇄'] += 1
        else:
            keep.append(i)
    d = df.loc[keep].copy()

    # 넓은 곳: B산 → M, B 필지 중 넓은 이름 → W, 건물 좌표를 못 찾은 캠퍼스·단지(같은 좌표 4곳 이상, 이름이 건물마다 다름) → W
    d['k5'] = d['위도'].astype(float).round(5).astype(str) + ',' + d['경도'].astype(float).round(5).astype(str)
    size = d['k5'].map(d['k5'].value_counts())
    campus = set()
    for k, s in d[size >= MIN_GROUP].groupby('k5'):
        if kind(list(s['화장실명'])) == '캠퍼스·단지':
            campus |= set(s.index)
    wide = pd.Series('', index=d.index)
    wide[d['좌표정확도'] == 'B산'] = 'M'
    wide[(d['좌표정확도'] == 'B') & d['화장실명'].str.contains(WIDE)] = 'W'
    wide[d.index.isin(campus)] = wide[d.index.isin(campus)].replace('', 'W')
    wide[d['좌표정확도'] == 'P'] = 'F'

    tiles = defaultdict(list)
    for i, r in d.iterrows():
        la, lo = round(float(r['위도']), 5), round(float(r['경도']), 5)   # 저장하는 값으로 칸도 정한다(칸 경계에서 반올림이 옆 칸으로 넘어가지 않게)
        rec = {'id': r['영구번호'], 'n': r['화장실명'], 't': KIND[r['구분명']], 'la': la, 'lo': lo,
               'a': r['정규주소'] or r['소재지도로명주소'] or r['소재지지번주소'], 'h': hrs[i], 'ht': r['개방시간상세'] or r['개방시간'],
               'm': [num(r['남성용-대변기수']), num(r['남성용-소변기수'])], 'f': num(r['여성용-대변기수']),
               'x': [num(r['남성용-장애인용대변기수']) + num(r['남성용-장애인용소변기수']), num(r['여성용-장애인용대변기수'])],
               'c': [num(r['남성용-어린이용대변기수']) + num(r['남성용-어린이용소변기수']), num(r['여성용-어린이용대변기수'])],
               'dp': 1 if r['기저귀교환대유무'] == 'Y' else 0, 'bl': 1 if r['비상벨설치여부'] == 'Y' else 0,
               'cc': 1 if r['화장실입구CCTV설치유무'] == 'Y' else 0, 'o': r['관리기관명'], 'tel': r['전화번호'],
               'g': 'P' if r['좌표정확도'] == 'P' else r['좌표정확도'].replace('B산', 'B')}
        if wide[i]:
            rec['w'] = wide[i]
        if r['좌표정확도'] == 'P':
            rec['w'] = 'F'                                  # 시설 위치 기준(입구·안내판 확인)
            rec['pc'] = 1 if r.get('시설확신') == '확인' else 0   # 0 = 한 곳에서만 찾음 → "정확하지 않을 수 있어요"
            if r['카카오장소명']:
                rec['pn'] = r['카카오장소명']
        rec['ft'] = ftype(r['화장실명'], r['화장실소유구분명'])          # 시설 종류(필터·아이콘)
        if r['데이터기준일자'][:4].isdigit():
            rec['dy'] = int(r['데이터기준일자'][:4])                      # 정보 기준 연도(오래된 정보 안내)
        if GATE.search(r['화장실명']):
            rec['gt'] = 1                                               # 지하철 개찰구 안 — 교통카드 필요
        elif GATE_OUT.search(r['화장실명']):
            rec['gt'] = 0                                               # 개찰구 밖 — 표 없이 이용
        if OIL.search(r['화장실명']):
            rec['gs'] = 1                                   # 주유소·충전소 → "직원에게 문의" 안내
        if place_ok(r) or (r['좌표정확도'] == 'P' and r['카카오장소ID']):
            rec['p'] = r['카카오장소ID']
        tot_m, tot_f = sum(rec['m']), rec['f']
        if tot_m + tot_f == 0:
            rec['ni'] = 1                                 # 변기 수가 모두 0 → "시설 정보 없음"(없음으로 단정하지 않음)
        elif tot_f == 0:
            rec['fq'] = 1                                 # 여성 0 → "?"(남녀 공용 1칸일 수 있음)
        tiles[(math.floor(la / TILE), math.floor(lo / TILE))].append(rec)

    # 중복 등록 합치기: 이름·좌표·시설·시간·종류가 모두 같으면 카드 하나(대표 = 가장 작은 영구번호)
    merged = 0
    for key, recs in tiles.items():
        seen = {}
        for rec in sorted(recs, key=lambda x: x['id']):
            sig = json.dumps([re.sub(r'\s', '', rec['n']), rec['la'], rec['lo'], rec['t'], rec['m'], rec['f'], rec['x'], rec['c'], rec['dp'], rec['h']], ensure_ascii=False, sort_keys=True)
            if sig in seen:
                seen[sig].setdefault('ids', []).append(rec['id'])
                merged += 1
            else:
                seen[sig] = rec
        tiles[key] = list(seen.values())

    gov = ROOT / 'data' / 'gov_sites.json'                    # 오류 신고 안내용 시군구 홈페이지 — 앱이 읽는다
    if gov.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gov, OUT / 'gov_sites.json')
    if (OUT / 't').exists():
        shutil.rmtree(OUT / 't')                              # 칸 파일만 새로 쓴다 — holidays.json 등 다른 앱 파일은 둔다(T15)
    (OUT / 't').mkdir(parents=True, exist_ok=True)
    sizes = []
    for (ty, tx), recs in tiles.items():
        recs.sort(key=lambda x: x['id'])                      # 파일 내용이 매번 같게(줄 순서 아님, 영구번호 순)
        p = OUT / 't' / f'{ty}_{tx}.json'
        p.write_text(json.dumps(recs, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        sizes.append(p.stat().st_size)
    stamp = snap.name
    shown_n = sum(len(v) for v in tiles.values())
    index = {'date': f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}', 'tile': TILE, 'count': shown_n, 'toilets': len(d),
             # 폐기된 영구번호 — 같은 관리번호에 다른 시설이 들어와 번호를 끊은 것(사례지식 6-33).
             # 앱은 이 번호로 저장해 둔 곳을 "없어진 곳"으로 알려 준다(작은 목록이라 색인에 함께 싣는다).
             'retired': sorted(br.load().get('retired', {})),
             'tiles': {f'{ty}_{tx}': len(v) for (ty, tx), v in sorted(tiles.items())}}
    (OUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    s = pd.Series(sizes)
    per = pd.Series([len(v) for v in tiles.values()])
    print(f'원본 {n0:,}곳 → 표시 {len(d):,}곳 ({len(d) / n0:.1%}), 카드 {shown_n:,}장(중복 등록 {merged:,}건 합침) · 위치 옮김 {int(moved.sum()):,}  빠짐: ' + ', '.join(f'{k} {v:,}' for k, v in reasons.most_common()))
    ftc = Counter(x['ft'] for v in tiles.values() for x in v)
    print('시설 종류: ' + ', '.join(f'{k} {v:,}' for k, v in ftc.most_common()))
    print(f'개찰구 표기 {sum(1 for v in tiles.values() for x in v if "gt" in x):,}곳 · 주유소·충전소 안내 {sum(1 for v in tiles.values() for x in v if x.get("gs")):,}곳 · 시설 이름 기준 {int(byfac.sum()):,}곳(확인 {int((df.get("시설확신") == "확인").sum()):,} · 추정 {int((df.get("시설확신") == "추정").sum()):,}) · 캠퍼스 건물 좌표 보정 {int(fixed.sum()):,}곳 · 넓은 곳 산지(M) {int((wide == "M").sum()):,} · 넓은 곳(W) {int((wide == "W").sum()):,} · 장소 링크 {sum(1 for v in tiles.values() for x in v if "p" in x):,}')
    print('개방시간: ' + ', '.join(f'{ {"a": "항상", "h": "시각", "u": "확인 필요"}[k]} {v:,}' for k, v in Counter(hrs[i]['k'] for i in d.index).most_common()))
    print(f'칸 {len(tiles):,}개 · 칸당 {per.median():.0f}곳(중앙값), 최대 {per.max():,} · 파일 {s.median() / 1024:.0f}KB(중앙값), 최대 {s.max() / 1024:.0f}KB, 합계 {s.sum() / 1024 / 1024:.1f}MB')
    print(f'저장: {OUT.relative_to(ROOT)}/ (기준일 {index["date"]})')


if __name__ == '__main__':
    main()
