"""자치단체코드 → 법정동 시군구코드(5자리) 대응표 — `data/sgg_codes.json`

**왜 필요한가**: 앱은 "이 정보가 틀렸나요?"에서 **그 화장실의 시군구청**을 안내한다. 지금까지는 **주소의 이름**으로 찾았는데,
행정구역이 개편되면 **주소의 이름과 실제 구가 달라진다**(인천 옛 중구 → 제물포구·영종구로 갈림, 2026-06-30). 이름으로는 가를 수 없다.
→ 행마다 **시군구코드**를 붙이고 코드로 찾는다(T32).

**왜 자치단체코드에서 만드나**: 원본의 `개방자치단체코드`는 **그 화장실을 관리하는 지자체**라, 주소 글자가 옛 이름이어도 **이미 새 구로 갈려 있다**
(인천 34910=영종구 · 35010=제물포구 · 35610=서해구 · 35650=검단구). 주소 이름보다 믿을 만하다.

**만드는 법** — 자치단체코드마다 증거를 모아 으뜸을 고른다.
1. **주소 캐시의 법정동코드**(도로명주소 API가 준 `행정구역코드` 앞 5자리) — 가장 강한 증거
2. 캐시에 없으면 **주소의 시군구 이름**을 공통지식 코드표의 **현재 이름과만** 맞춘다(옛 이름은 세지 않는다)

  python build_sgg_codes.py           만들고 저장
  python build_sgg_codes.py --check   지금 표를 주소 이름과 대조만(고치지 않음)
"""
import argparse, csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
REG = ROOT.parent / '공통지식' / '기준자료' / '행정구역' / '행정구역_시군구.csv'
CACHE = ROOT / 'data' / 'processed' / 'address_cache.json'
OUT = ROOT / 'data' / 'sgg_codes.json'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def current_names():
    """(시도명, 시군구명) → 시군구코드 — **지금 쓰는 이름만**(옛 이름은 들어 있지 않다)"""
    rows = list(csv.DictReader(REG.read_text(encoding='utf-8-sig').splitlines()))
    return {(r['시도명'], r['시군구명']): r['시군구코드'] for r in rows}, {r['시군구코드']: (r['시도명'], r['시군구명']) for r in rows}


def latest_geo():
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    return pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna(''), snap.name


def build():
    by_name, by_code = current_names()
    cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    geo, stamp = latest_geo()
    ev_cache, ev_name = defaultdict(Counter), defaultdict(Counter)
    for r in geo.itertuples():
        code = r.개방자치단체코드
        road, lot = r.소재지도로명주소.strip(), r.소재지지번주소.strip()
        for addr in (road, lot):                        # 캐시 키는 '코드시도|코드시군구|주소'
            if not addr:
                continue
            v = cache.get(f'{r.코드시도}|{r.코드시군구}|{addr}')
            if isinstance(v, dict) and v.get('행정구역코드'):
                ev_cache[code][v['행정구역코드'][:5]] += 1
                break
        p = (road or lot).split()
        if len(p) >= 2 and (p[0], p[1]) in by_name:
            ev_name[code][by_name[(p[0], p[1])]] += 1

    table, how, miss = {}, Counter(), []
    for code in sorted(set(geo['개방자치단체코드'])):
        if ev_cache[code]:
            table[code] = ev_cache[code].most_common(1)[0][0]
            how['캐시(법정동코드)'] += 1
        elif ev_name[code]:
            table[code] = ev_name[code].most_common(1)[0][0]
            how['주소 이름'] += 1
        else:
            miss.append(code)
    print(f'기준본 {stamp} · 자치단체코드 {len(set(geo["개방자치단체코드"]))} · 정함 {len(table)} {dict(how)}')
    if miss:
        print(f'  못 정함 {len(miss)}: {", ".join(miss[:8])} — 주소 캐시를 채운 뒤 다시 돌린다')
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=0), encoding='utf-8')
    print(f'저장: {OUT.relative_to(ROOT)}')
    return table, by_code, geo


def check(table, by_code, geo):
    """배정한 이름과 주소의 이름이 다른 곳을 보여 준다.

    **다르다고 틀린 것이 아니다.** 둘 중 하나다 — ① 행정구역 개편(주소가 옛 이름) ② 특례시·일반구 표기(`수원시 팔달구`).
    개편이 아닌데 다르면 그때 의심한다.
    """
    two = 0
    odd = []
    for code, g in geo.groupby('개방자치단체코드'):
        sgg = table.get(code)
        if not sgg:
            continue
        addr = g['소재지도로명주소'].where(g['소재지도로명주소'] != '', g['소재지지번주소'])
        got = Counter(a.split()[1] for a in addr if len(a.split()) > 1)
        if not got:
            continue
        top = got.most_common(1)[0][0]
        want = by_code[sgg][1]
        if top == want:
            continue
        if want.startswith(top):                        # 수원시 ↔ 수원시팔달구
            two += 1
            continue
        odd.append((code, f'{by_code[sgg][0]} {want}', dict(got.most_common(3)), len(g)))
    print(f'\n■ 대조: 특례시·일반구 표기 {two}곳(정상) · 그 밖에 다른 곳 {len(odd)}곳')
    for c, nm, got, n in odd:
        print(f'   {c} → {nm} (행 {n:,}) · 주소 으뜸 {got}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.check:
        by_name, by_code = current_names()
        table = json.loads(OUT.read_text(encoding='utf-8'))
        geo, _ = latest_geo()
        return check(table, by_code, geo)
    check(*build())


if __name__ == '__main__':
    main()
