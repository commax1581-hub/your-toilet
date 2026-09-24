"""지자체 홈페이지 주소 모으기 — 원본(주소·시간·시설) 오류는 그 지자체가 고쳐야 한다.
앱에서 "이 화장실 정보가 틀렸나요?"를 누르면 ① 관리기관 전화(데이터에 있음) ② 해당 시군구 홈페이지 ③ 공공데이터포털 오류신고로 안내한다.
네이버 지역검색이 장소의 홈페이지(link)를 함께 주므로 시군구청을 찾아 주소를 받는다(무료, 229곳 한 번).
결과: data/gov_sites.json  {"서울특별시 강남구": {"기관": "강남구청", "홈페이지": "https://..."}}
실행: python build_gov_links.py
"""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import requests
from addr_util import env

ROOT = Path(__file__).parent
OUT = ROOT / 'data' / 'gov_sites.json'
URL = 'https://naverapihub.apigw.ntruss.com/search/v1/local'
H = {'X-NCP-APIGW-API-KEY-ID': env('NAVER_CLIENT_ID'), 'X-NCP-APIGW-API-KEY': env('NAVER_CLIENT_SECRET')}
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def office_name(sido, sgg):
    """강남구 → 강남구청 / 화성시 → 화성시청 / 양평군 → 양평군청 / 시군구가 없으면 시도청"""
    if not sgg:
        return re.sub(r'(특별자치도|특별자치시|광역시|특별시|도)$', '', sido) + ('도청' if sido.endswith('도') else '시청')
    last = sgg.split()[-1]
    return last + {'구': '청', '시': '청', '군': '청'}.get(last[-1], '청')


def search(q):
    for _ in range(3):
        try:
            r = requests.get(URL, headers=H, params={'query': q, 'display': 5}, timeout=10)
            if r.status_code == 200:
                return r.json().get('items', [])
            if r.status_code == 429:
                time.sleep(2); continue
            return []
        except requests.RequestException:
            time.sleep(1)
    return []


def one(key):
    sido, sgg = key
    name = office_name(sido, sgg)
    for it in search(f'{sido} {name}'):
        title = re.sub(r'<[^>]+>', '', it['title'])
        link = it.get('link') or ''
        if link.startswith('http') and (name[:2] in title or (sgg and sgg.split()[-1][:2] in title)):
            return {'기관': title, '홈페이지': link}
    return None


def main():
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    g = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('')
    keys = sorted({(r['코드시도'], r['코드시군구']) for _, r in g.iterrows() if r['코드시도']})
    print(f'지자체 {len(keys)}곳 찾기')
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(one, keys))
    out = {f'{a} {b}'.strip(): v for (a, b), v in zip(keys, res) if v}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    miss = [f'{a} {b}'.strip() for (a, b), v in zip(keys, res) if not v]
    print(f'홈페이지 찾음 {len(out)}/{len(keys)}' + (f' · 못 찾음: {", ".join(miss[:10])}' if miss else ''))
    for k, v in list(out.items())[:5]:
        print(f'  {k} → {v["기관"]} {v["홈페이지"]}')
    print(f'저장: {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
