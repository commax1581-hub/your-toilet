"""앱 데이터 불변조건 검사 — 하나라도 실패(FAIL)면 종료코드 1 → 배포하지 않는다. (착한가격 check_data.py와 같은 역할)
검사: 영구번호 중복·대장에 없음(합친 번호 포함) / 시설 종류가 사전에 있는 값인지·대체 비율 / 좌표가 국내 범위·자기 칸 안 / 표시 기준(구분·등급) / 개방시간 구조 / 필수 칸 / 파일 크기·개수 / 공휴일 목록 / 지난 판 대비 급감
실행: python check_data.py [--prev 지난 index.json]
"""
import argparse, glob, json, math, re, sys
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
    seen, total, big = set(), 0, []
    ftc = {}
    for f in files:
        key = Path(f).stem
        ty, tx = map(int, key.split('_'))
        kb = Path(f).stat().st_size / 1024
        if kb > MAX_FILE_KB:
            big.append(f'{key} {kb:.0f}KB')
        recs = json.loads(Path(f).read_text(encoding='utf-8'))
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
