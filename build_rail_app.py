"""역사 화장실 → 앱 데이터(`app/data/rail.json`)

본 데이터(`app/data/t/*.json`)와 **합치지 않는다.** 파일을 따로 두고 앱이 화면에서 잇는다(규약 4-1 · 사례지식 6-24).
좌표는 `build_rail.py`가 만든 역 좌표표(기관 × 노선 × 역)를 그대로 쓴다 — 먼저 그것을 돌려야 한다.

  python build_rail_app.py

출처가 둘이다. **섞지 않고 역마다 하나를 고른다.**
- 서울교통공사 파일(2026-02)이 있으면 그것 — 더 새롭고 칸이 36개(변기 수·전화·개방시간까지)
- 없으면 국가철도공단 파일(2025-06) — 칸이 9개(층·개찰구·출구·상세위치·남녀)

같은 자리(층·개찰구·출구·상세위치)의 남자·여자 행은 **한 칸으로 묶는다**(원본은 남/여가 따로 한 행씩).
"""
import glob, json, re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / 'data' / 'raw' / 'rail'
STN = ROOT / 'data' / 'rail_stations.csv'
OUT = ROOT / 'app' / 'data' / 'rail.json'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BARE = re.compile(r'[\(（].*?[\)）]')
RENAMED = {'당고개': '불암산', '뚝섬유원지': '자양', '가정': '가정중앙시장', '서구청': '서해구청'}


def norm(name):
    s = BARE.sub('', str(name)).strip()
    s = s[:-1] if len(s) > 2 and s.endswith('역') else s
    return RENAMED.get(s, s)


def read(f):
    for enc in ('cp949', 'utf-8-sig', 'utf-8'):
        try:
            d = pd.read_csv(f, dtype=str, encoding=enc).fillna('')
            d.columns = [c.strip() for c in d.columns]
            return d
        except Exception:
            pass
    sys.exit(f'읽지 못함: {f}')


def floor_txt(updown, n):
    """지상/지하 + 역층 → `B1` · `2F` (사람이 역에서 보는 표기)"""
    n = str(n).strip() or '1'
    return ('B' + n) if str(updown).strip() == '지하' else (n + 'F')


def floor_key(f):
    """층 정렬 — **지면에서 가까운 순, 같으면 지상 먼저**(사용자 결정 6-27).
    1F(0) · 2F(1) · B1(1) · 3F(2) · B2(2) · 4F(3) · B3(3) …"""
    if f.startswith('B'):
        return (int(f[1:]), 1)                  # 지하 n층 → 지면과 n, 지상보다 뒤
    return (int(f[:-1]) - 1, 0)                 # 지상 n층 → 지면과 n-1


def exits(s):
    """출구 번호 — `1 2 5` · `1,2` · `1 또는2` 를 `1·2·5`로. 없으면 ''"""
    nums = re.findall(r'\d+(?:-\d+)?', str(s))
    seen = [n for i, n in enumerate(nums) if n not in nums[:i]]
    return '·'.join(seen)


def num(v):
    try:
        return int(float(str(v).strip() or 0))
    except ValueError:
        return 0


def yn(v):
    return 1 if str(v).strip().upper() == 'Y' else 0


def gongdan():
    """국가철도공단 23개 파일 → (기관, 노선, 역명정규) → 화장실 목록"""
    COLS = ['철도운영기관명', '선명', '역명', '지상구분', '역층', '게이트내외', '출구번호', '상세위치', '화장실구분']
    k = pd.concat([read(f) for f in glob.glob(str(RAW / '국가철도공단*.csv'))], ignore_index=True)
    k = k.drop_duplicates(subset=COLS)                    # 파일끼리 겹친 287행(T24)
    out = {}
    for (op, ln, nm), g in k.groupby(['철도운영기관명', '선명', k['역명'].map(norm)]):
        seats = {}
        for _, r in g.iterrows():
            f = floor_txt(r['지상구분'], r['역층'])
            key = (f, r['게이트내외'].strip(), r['출구번호'].strip(), r['상세위치'].strip())
            seats.setdefault(key, set()).add(r['화장실구분'].strip()[:1])   # 남/여
        out[(op.strip(), ln.strip(), nm)] = [
            {'f': f, 'g': 1 if gate == '내' else 0, 'x': exits(x), 'w': ' '.join(w.split()),
             's': ''.join(c for c in '남여' if c in sx)}
            for (f, gate, x, w), sx in seats.items()]
    return out


def seoul():
    """서울교통공사 파일 → (기관, 노선, 역명정규) → 화장실 목록(변기 수까지)"""
    s = read(RAW / '서울교통공사_역사공중화장실정보_20260212.csv')
    s = s[s['역명'].str.strip() != '']                     # 빈 행 10개
    out = {}
    for (ln, nm), g in s.groupby(['운영노선명', s['역명'].map(norm)]):
        lst = []
        for _, r in g.iterrows():
            lst.append({
                'f': floor_txt(r['지상 또는 지하 구분'], r['역층']),
                'g': 1 if '내' in r['게이트 내외 구분'] else 0,
                'x': exits(r['(근접) 출입구 번호']), 'w': ' '.join(str(r['상세위치']).split()), 's': '남여',
                'm': [num(r['남성용-대변기수']), num(r['남성용-소변기수'])], 'fm': num(r['여성용-대변기수']),
                'ac': [num(r['남성용-장애인용대변기수']) + num(r['남성용-장애인용소변기수']), num(r['여성용-장애인용대변기수'])],
                'ch': [num(r['남성용-어린이용대변기수']) + num(r['남성용-어린이용소변기수']), num(r['여성용-어린이용대변기수'])],
                'dp': [yn(r['기저귀교환대설치유무-남자화장실']), yn(r['기저귀교환대설치유무-여자화장실'])],
                'bl': yn(r['비상벨 설치유무']), 'cc': yn(r['화장실입구cctv설치유무']),
                'tel': str(r['전화번호']).strip(), 'ht': str(r['개방시간']).strip(),
                'ry': str(r['리모델링 연도']).strip()})
        out[('서울교통공사', ln.strip(), nm)] = lst
    return out


def main():
    if not STN.exists():
        sys.exit('역 좌표표가 없습니다 — 먼저 `python build_rail.py`를 돌리세요.')
    stn = pd.read_csv(STN, dtype=str, encoding='utf-8-sig').fillna('')
    gd, se = gongdan(), seoul()
    print(f'국가철도공단 역·노선 {len(gd):,} · 서울교통공사 역·노선 {len(se):,}')

    rows, miss, pick = [], 0, {'서울': 0, '공단': 0}
    for _, r in stn.iterrows():
        if not r['위도']:
            miss += 1
            continue                                       # 좌표 없는 역은 지도에 올릴 수 없다
        key = (r['운영기관'], r['노선'], r['역명'])
        # 출처를 **섞지 않는다** — 서울교통공사가 있으면 그쪽(더 새롭고 칸이 많다), 없으면 국가철도공단
        if key in se:
            src, toilets = '서울교통공사', se[key]
            pick['서울'] += 1
        elif key in gd:
            src, toilets = '국가철도공단', gd[key]
            pick['공단'] += 1
        else:
            continue
        toilets.sort(key=lambda t: (floor_key(t['f']), t['g'], [int(n) for n in re.findall(r'\d+', t['x'])] or [99]))
        rows.append({'n': r['역명'], 'ln': r['노선'], 'op': r['운영기관'], 'src': src,
                     'la': round(float(r['위도']), 6), 'lo': round(float(r['경도']), 6),
                     't': toilets})

    rows.sort(key=lambda x: (x['n'], x['ln']))
    # 개명표를 함께 싣는다 — 저장해 둔 역이 **이름만 바뀐 것**이면 앱이 새 이름으로 이어 준다(6-34).
    # 역은 없어지지 않으므로, 이 표에도 없이 사라진 이름은 앱이 "확인 필요"로 알린다.
    data = {'date': {'국가철도공단': '2025-06-30', '서울교통공사': '2026-02-12'},
            'count': len(rows), 'toilets': sum(len(x['t']) for x in rows),
            'renamed': RENAMED, 's': rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    kb = OUT.stat().st_size / 1024
    print(f'역 {len(rows):,}(서울교통공사 {pick["서울"]:,} · 국가철도공단 {pick["공단"]:,}) · 화장실 {data["toilets"]:,}칸'
          f' · 좌표 없어 제외 {miss}')
    print(f'저장: {OUT.relative_to(ROOT)} ({kb:,.0f}KB)')

    # 눈으로 확인할 표본
    for want in [('대구교통공사', '1호선', '반월당'), ('대구교통공사', '2호선', '반월당'),
                 ('대구교통공사', '1호선', '동대구'), ('서울교통공사', '2호선', '강남')]:
        x = next((v for v in rows if (v['op'], v['ln'], v['n']) == want), None)
        if x:
            print(f"\n  {x['ln']} {x['n']}역 [{x['src']}] {x['la']},{x['lo']}")
            for t in x['t']:
                print(f"    {t['f']} · 개찰구 {'안' if t['g'] else '밖'} · 출구 {t['x'] or '-'} · {t['s']} · {t['w'][:38]}")


if __name__ == '__main__':
    main()
