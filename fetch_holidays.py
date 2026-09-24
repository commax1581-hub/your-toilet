"""공휴일 목록 — 개방시간의 `(공휴일)…`·`공휴일 휴무` 표기를 정확히 계산하려면 그 해 공휴일이 필요하다.
출처: 한국천문연구원_특일 정보(공공데이터포털 15012690, 무료·자동승인). 1년에 한 번만 받으면 된다.
결과: app/data/holidays.json  {"2026": ["2026-01-01", ...], ...}
실행: python fetch_holidays.py [--years 2026 2027]
"""
import argparse, json, sys
from datetime import date
from pathlib import Path
import requests
from addr_util import env

ROOT = Path(__file__).parent
OUT = ROOT / 'app' / 'data' / 'holidays.json'
URL = 'https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def year_holidays(key, year):
    days = []
    for month in range(1, 13):
        r = requests.get(URL, params={'serviceKey': key, 'solYear': year, 'solMonth': f'{month:02d}',
                                      'numOfRows': 50, '_type': 'json'}, timeout=20)
        if r.status_code != 200:
            sys.exit(f'{year}-{month:02d} 오류 {r.status_code}: {r.text[:200]}')
        body = r.json()['response']['body']
        items = (body.get('items') or {}).get('item', []) if body.get('totalCount') else []
        items = items if isinstance(items, list) else [items]
        days += [f'{str(i["locdate"])[:4]}-{str(i["locdate"])[4:6]}-{str(i["locdate"])[6:]}'
                 for i in items if i.get('isHoliday') == 'Y']
    return sorted(set(days))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', nargs='*', type=int, default=[date.today().year, date.today().year + 1])
    a = ap.parse_args()
    key = env('DATAGOKR_KEY')
    out = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    for y in a.years:
        out[str(y)] = year_holidays(key, y)
        print(f'{y}년 공휴일 {len(out[str(y)])}일: ' + ', '.join(out[str(y)]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'저장: {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
