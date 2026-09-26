"""앱 데이터 불변조건 검사 — 하나라도 실패(FAIL)면 종료코드 1 → 배포하지 않는다. (착한가격 check_data.py와 같은 역할)
검사: 영구번호 중복·대장에 없음(합친 번호 포함) / 시설 종류가 사전에 있는 값인지·대체 비율 / 좌표가 국내 범위·자기 칸 안 / 표시 기준(구분·등급) / 개방시간 구조 / 필수 칸 / 파일 크기·개수 / 공휴일 목록 / 지난 판 대비 급감
실행: python check_data.py [--prev 지난 index.json]
"""
import argparse, csv, glob, json, math, re, sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent
DATA = ROOT / 'app' / 'data'
CLASSIFY = json.loads((ROOT / 'data' / 'classify.json').read_text(encoding='utf-8'))
FTYPE_OK = {t['이름'] for t in CLASSIFY['종류']} | set(CLASSIFY['대체'].values())
FALLBACK_WARN = 0.25          # 이름으로 분류 안 돼 소유 구분으로 채운 비율이 이보다 크면 경고(사전 손볼 때)
KOREA = (33.0, 38.7, 124.5, 132.0)          # 위도·경도 범위(제주·울릉·독도 포함)
MAX_FILE_KB, MAX_FILES, DROP = 300, 20000, 0.10
HHMM = re.compile(r'^([01]\d|2[0-4])[0-5]\d$')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
fails, warns = [], []


def check_dong():
    """주소의 **법정동**이 가리키는 구와, 우리가 배정한 시군구코드가 어긋난 행을 찾는다.

    배정은 원천의 `개방자치단체코드`(관리 지자체)에서 온다. 그게 주소보다 먼저 새 구로 갈리는 게 보통이지만(T32),
    **드물게 관리 지자체가 실제 소재지와 다른 행**이 있다(인천 서구 시천동 화장실이 서해구 소관으로 적힌 식).
    증거는 주소 캐시의 법정동코드 — **그 행 자신의 주소**에서 나온 값이라 가장 강하다.
    일반구는 자치단체가 아니므로 **양쪽 다 모시로 올려** 견준다(그러지 않으면 특례시 전체가 어긋남으로 잡힌다).
    고치는 것이 아니라 **보여 주기만** 한다 — 원천이 맞을 수도 있다.
    """
    cache_p, sgg_p = ROOT / 'data' / 'processed' / 'address_cache.json', ROOT / 'data' / 'sgg_codes.json'
    reg = ROOT.parent / '공통지식' / '기준자료' / '행정구역' / '행정구역_시군구.csv'
    snaps = sorted((ROOT / 'data' / 'snapshots').iterdir()) if (ROOT / 'data' / 'snapshots').exists() else []
    if not (cache_p.exists() and sgg_p.exists() and reg.exists() and snaps):
        return
    names = {r['시군구코드']: r['시군구명']
             for r in csv.DictReader(reg.read_text(encoding='utf-8-sig').splitlines())}

    def 자치단체로(code):
        nm, up = names.get(code, ''), code[:4] + '0'
        return up if nm.endswith('구') and '시' in nm and up in names else code

    cache = json.loads(cache_p.read_text(encoding='utf-8'))
    table = json.loads(sgg_p.read_text(encoding='utf-8'))
    시도들 = {r['시도명'] for r in csv.DictReader(reg.read_text(encoding='utf-8-sig').splitlines())}
    본 = 0
    어긋 = []
    with (snaps[-1] / 'toilets_geo.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            ours = table.get(r['개방자치단체코드'])
            if not ours:
                continue
            for addr in (r['소재지도로명주소'].strip(), r['소재지지번주소'].strip()):
                # **시도로 시작하는 온전한 주소만** 견준다. '없음'이나 '용당동 172-4'처럼 시도가 없는 주소는
                # 정제가 엉뚱한 곳을 가리키기 쉽고(주소 '없음'이 군산시로 나온 행이 있다), 그런 행은 위의
                # '시도 어긋남' 경고가 이미 잡는다. 잡음을 섞으면 이 경고를 아무도 보지 않게 된다.
                if not addr.split(' ')[0] in 시도들:
                    continue
                v = cache.get(f"{r['코드시도']}|{r['코드시군구']}|{addr}") if addr else None
                if isinstance(v, dict) and v.get('행정구역코드'):
                    본 += 1
                    row = 자치단체로(v['행정구역코드'][:5])
                    if row != 자치단체로(ours):
                        어긋.append((r.get('번호') or r.get('고유번호', ''), names.get(ours, ours), names.get(row, row), (addr or '')[:34]))
                    break
    if 어긋:
        warns.append(f'주소의 법정동과 배정 코드가 어긋난 행 {len(어긋)}/{본:,} — **어느 쪽이 틀렸는지는 열어 봐야 안다** '
                     f'(원천의 관리 지자체가 소재지와 다른 경우 · 주소 정제가 틀린 경우 둘 다 있다. 고치지 않고 보여만 준다): '
                     + ' · '.join(f'{a[3]} → 배정 {a[1]}, 주소 {a[2]}' for a in 어긋[:3]))
    print(f'  주소 법정동으로 견준 행 {본:,} · 어긋남 {len(어긋)}')


def check_hours(h, rid):
    k = h.get('k')
    if k not in ('a', 'h', 'u'):
        return f'{rid} 개방시간 종류 {k}'
    if k == 'h':
        if not h.get('r'):
            return f'{rid} 시각 규칙 없음'
        for m, o, c in h['r']:
            if not (1 <= m <= 127) or not HHMM.match(o) or not HHMM.match(c):
                return f'{rid} 시각 규칙 이상 {m} {o} {c}'
    return None


def main(data=DATA, prev=None):
    idx = json.loads((data / 'index.json').read_text(encoding='utf-8'))
    reg = json.loads((ROOT / 'data' / 'id_registry.json').read_text(encoding='utf-8'))
    known = set(reg['by_mng'].values())
    files = glob.glob(str(data / 't' / '*.json'))
    seen, total, big, every = set(), 0, [], []
    ftc = {}
    for f in files:
        key = Path(f).stem
        ty, tx = map(int, key.split('_'))
        kb = Path(f).stat().st_size / 1024
        if kb > MAX_FILE_KB:
            big.append(f'{key} {kb:.0f}KB')
        recs = json.loads(Path(f).read_text(encoding='utf-8'))
        every += recs                                   # 칸을 넘어서 보는 검사용(시군구코드 등)
        if idx['tiles'].get(key) != len(recs):
            fails.append(f'칸 {key}: index {idx["tiles"].get(key)} ≠ 파일 {len(recs)}')
        for r in recs:
            total += 1
            rid = r.get('id', '?')
            for x in [rid] + r.get('ids', []):          # 합친 중복 등록의 다른 번호도 검사
                if x in seen:
                    fails.append(f'영구번호 중복 {x}')
                seen.add(x)
                if x not in known:
                    fails.append(f'대장에 없는 번호 {x}')
            if not (KOREA[0] <= r['la'] <= KOREA[1] and KOREA[2] <= r['lo'] <= KOREA[3]):
                fails.append(f'{rid} 좌표가 국내 범위 밖 {r["la"]},{r["lo"]}')
            if (math.floor(r['la'] / idx['tile']), math.floor(r['lo'] / idx['tile'])) != (ty, tx):
                fails.append(f'{rid} 좌표가 자기 칸({key}) 밖')
            if r.get('t') not in (0, 1, 2, 3):
                fails.append(f'{rid} 표시하지 않는 구분 {r.get("t")}')
            if r.get('g') not in ('A', 'B', 'P'):
                fails.append(f'{rid} 표시하지 않는 좌표 등급 {r.get("g")}')
            if r.get('g') == 'P' and (r.get('w') != 'F' or 'pc' not in r):
                fails.append(f'{rid} 시설 위치 기준인데 안내 표시(w=F, pc) 없음')
            if not r.get('n') or not r.get('a'):
                fails.append(f'{rid} 이름·주소 빈 칸')
            ft = r.get('ft')
            ftc[ft] = ftc.get(ft, 0) + 1
            if ft not in FTYPE_OK:
                fails.append(f'{rid} 사전에 없는 시설 종류 "{ft}" — data/classify.json 확인')
            e = check_hours(r.get('h', {}), rid)
            if e:
                fails.append(e)
    if total != idx['count']:
        fails.append(f'index 카드 수 {idx["count"]:,} ≠ 파일 합계 {total:,}')
    if 'toilets' in idx and len(seen) != idx['toilets']:
        fails.append(f'index 화장실 수 {idx["toilets"]:,} ≠ 파일 속 번호 {len(seen):,}')
    fb = sum(v for k, v in ftc.items() if k in CLASSIFY['대체'].values())
    if total and fb / total > FALLBACK_WARN:
        warns.append(f'이름으로 분류되지 않아 소유 구분으로 채운 곳 {fb:,} ({fb / total:.1%}) — data/classify.json에 규칙 보강 검토')
    if len(files) > MAX_FILES:
        fails.append(f'파일 {len(files):,}개 — 배포 한도 {MAX_FILES:,} 넘음')
    if big:
        warns.append(f'{MAX_FILE_KB}KB 넘는 칸 {len(big)}개: {", ".join(big[:5])}')
    hol = data / 'holidays.json'                              # 앱이 공휴일에 관공서·사무실을 "공휴일 확인"으로 낮추는 근거(T15)
    if not hol.exists():
        fails.append('holidays.json 없음 — python fetch_holidays.py')
    else:
        years, now = json.loads(hol.read_text(encoding='utf-8')), str(date.today().year)
        if now not in years:
            fails.append(f'holidays.json에 {now}년 없음 — python fetch_holidays.py')
    # 시군구코드(sgg)와 구청 안내 — 행정구역 개편이면 이름은 옛것이라도 코드는 새 구를 가리켜야 한다(T32)
    gov_p = data / 'gov_sites.json'
    if gov_p.exists():
        gov = json.loads(gov_p.read_text(encoding='utf-8'))
        no_code = [r for r in every if not r.get('sgg')]
        no_gov = [r for r in every if r.get('sgg') and r['sgg'] not in gov]
        if no_code:
            fails.append(f'시군구코드가 없는 카드 {len(no_code):,} — python build_sgg_codes.py')
        if no_gov:
            fails.append(f'구청 안내를 못 찾는 카드 {len(no_gov):,}(코드 {len(set(r["sgg"] for r in no_gov))}종) — gov_sites.json에 더한다')
        sido = {c: v.get('시도', '') for c, v in gov.items()}
        odd = [r for r in every if r.get('sgg') and sido.get(r['sgg'])
               and r['a'].split()[:1] and r['a'].split()[0] != sido[r['sgg']] and r['a'].split()[0].endswith(('시', '도'))]
        if odd:
            warns.append(f'주소의 시도와 코드의 시도가 어긋난 카드 {len(odd)} — 원천의 자치단체코드 오류일 수 있다(앱은 주소를 따른다)')
        print(f'  시군구 {len(set(r.get("sgg") for r in every)):,}종 · 구청 안내 {len(gov):,}곳'
              + (f' · 시도 어긋남 {len(odd)}' if odd else ''))
    check_dong()

    rail = data / 'rail.json'                                # 역 안 화장실 — 본 데이터와 합치지 않고 잇는 별개 파일
    if not rail.exists():
        fails.append('rail.json 없음 — python build_rail.py && python build_rail_app.py')
    else:
        r = json.loads(rail.read_text(encoding='utf-8'))
        if r.get('count', 0) < 700:
            fails.append(f'rail.json 역 {r.get("count", 0):,} — 833곳보다 크게 적다')
        no_xy = [s['n'] for s in r['s'] if not (33 < s['la'] < 39 and 124 < s['lo'] < 132)]
        if no_xy:
            fails.append(f'rail.json 국내 범위 밖 좌표 {len(no_xy)}곳: {", ".join(no_xy[:5])}')
        print(f'  역 {r["count"]:,}곳 · 화장실 {r["toilets"]:,}칸 · {rail.stat().st_size / 1024:,.0f}KB')

    if prev:
        p = json.loads(Path(prev).read_text(encoding='utf-8'))
        if total < p['count'] * (1 - DROP):
            fails.append(f'표시 곳 {p["count"]:,} → {total:,}, {DROP:.0%} 넘게 감소')
    for w in warns:
        print('WARN', w)
    for f in fails[:30]:
        print('FAIL', f)
    print(f'{total:,}곳 · 칸 {len(files):,}개 · 실패 {len(fails)} · 경고 {len(warns)}')
    return 1 if fails else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--prev')
    a = ap.parse_args()
    sys.exit(main(prev=a.prev))
