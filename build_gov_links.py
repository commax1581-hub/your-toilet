"""지자체 홈페이지 주소 모으기 — 원본(주소·시간·시설) 오류는 그 지자체가 고쳐야 한다.
앱에서 "이 화장실 정보가 틀렸나요?"를 누르면 ① 관리기관 전화(데이터에 있음) ② 해당 시군구 홈페이지 ③ 공공데이터포털 오류신고로 안내한다.
네이버 지역검색이 장소의 홈페이지(link)를 함께 주므로 시군구청을 찾아 주소를 받는다(무료).

**네이버는 '○○구청'으로 찾으면 근처 가게를 준다.** 267곳 중 12곳이 다이소·버거킹·하나은행·카페·식당·인스타그램·블로그였다
(2026-09-26 장학금 세션이 전수 열어 제목을 확인하고 고쳤다 — 사례지식 6-40). 이름에 '강북'이 들어가면 통과시킨 탓이다.
→ 후보마다 **세 가지**를 거른다. 하나라도 어긋나면 버리고 **왜 버렸는지 남긴다.**
  ① 주소가 **관청 도메인**(`*.go.kr`)인가 — linktr.ee·instagram.com·blog.naver.com·happy700.or.kr을 막는다
  ② **기관 이름이 '청'으로 끝나는가** — '다이소 강북구청사거리점'(점)·'NH농협은행 칠곡군청출장소'(소)를 막는다
  ③ **첫 화면을 열어 제목에 시군구 이름이 있는가** — 죽은 주소·옛 주소를 막는다(동해 http 404 → https만 열림)

**판정은 셋이다 — 통과 · 버림 · 보류.** ③은 남의 서버에 달렸다. 처음 267곳에 걸었을 때 19곳이 걸렸는데 **대부분 우리 쪽 잘못**이었다
(동시 접속 시간초과 · 지자체 인증서 · 자바스크립트로 그리는 빈 제목 · 일반구 이름 `창원시진해구`를 `창원시청`과 맞추려 한 것 · `전주시 대표사이트`).
**못 열린 것을 틀린 것으로 세면 멀쩡한 것을 고치려 든다**(6-39의 교훈) → 시간초과·인증서·빈 제목은 **보류**로 따로 세고,
이름 비교는 **모시 어간**('창원시진해구'→'창원')으로 한다.

**표를 말없이 덮지 않는다.** 기준 표(`공통지식/기준자료/행정구역/시군구_누리집.json`)에는 사람이 손으로 고친 것과 그 기록이 들어 있다.
이 스크립트는 **후보**를 `data/gov_sites_candidates.json`에 쓰고 **표와 다른 곳만 보여 준다** — 반영은 사람이 한다.

  python build_gov_links.py            후보 모으기(네이버 키 필요) + 기준 표와 대조
  python build_gov_links.py --verify   찾지 않고, 지금 기준 표 267곳에 ①②③를 그대로 걸어 본다(연 1회 점검)
"""
import argparse, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import requests
from addr_util import env

ROOT = Path(__file__).parent
OUT = ROOT / 'data' / 'gov_sites_candidates.json'
TABLE = ROOT.parent / '공통지식' / '기준자료' / '행정구역' / '시군구_누리집.json'
SGG = ROOT / 'data' / 'sgg_codes.json'
UA = {'User-Agent': 'Mozilla/5.0 (toilet-map gov link check)'}
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


def 관청_도메인(link):
    """① 주소가 관청 도메인인가 — go.kr 계열만 받는다."""
    host = re.sub(r'^https?://', '', link).split('/')[0].split(':')[0].lower()
    return host.endswith('.go.kr') or host == 'go.kr'


# 관청 이름에 흔히 붙는 부속 표현 — 떼고 나서 '청'으로 끝나야 한다
부속 = re.compile(r'\s*(본청|신청사|제\s*\d+\s*청사|청사|별관|본관|민원실)$')


def 청으로_끝나나(title):
    """② 기관 이름이 '청'으로 끝나는가 — '…구청사거리점'(점)·'…군청출장소'(소)를 막는다.

    **'통영시청 제1청사'·'여수시청 본청'은 진짜 시청이다.** 처음엔 이것까지 버렸다(267곳 점검에서 드러남)
    → 부속 표현을 떼고 본다. '출장소'는 떼지 않는다 — 은행 출장소가 그렇게 붙는다.
    """
    name = 부속.sub('', title.strip().rstrip('.')).strip()
    return name.endswith('청')


def 첫화면_제목(link):
    """③ 첫 화면을 열어 <title>을 읽는다. http가 죽고 https만 열리는 곳이 있어 https도 해 본다.

    돌려주는 것: (열린 주소, 제목, 덧말) — 못 열면 (None, '', 까닭).
    **지자체 서버는 느리고 인증서가 어긋난 곳이 많다.** 넉넉히 기다리고, 인증서만 어긋나면 제목을 읽되 덧말에 남긴다.
    """
    tries = [link] + ([link.replace('http://', 'https://', 1)] if link.startswith('http://') else [])
    why = ''
    for u in tries:
        for verify in (True, False):
            try:
                r = requests.get(u, headers=UA, timeout=25, allow_redirects=True, verify=verify)
            except requests.RequestException as e:
                why = type(e).__name__
                if verify and 'SSL' in why:
                    continue                      # 인증서만 어긋난 곳 — 살아 있는지 제목으로 본다
                break
            if r.status_code >= 400:
                why = f'{r.status_code}'
                break
            r.encoding = r.apparent_encoding or r.encoding
            m = re.search(r'<title[^>]*>(.*?)</title>', r.text, re.S | re.I)
            return u, (re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''), ('' if verify else '인증서 어긋남')
    return None, '', why or '열리지 않음'


def 이름_어간(sgg):
    """제목과 맞출 어간 — 일반구는 모시로, 꼬리(시·군·구)는 뗀다. '창원시진해구'→'창원' · '전주시완산구'→'전주'"""
    last = sgg.split()[-1]
    모시 = re.match(r'(.+?시)[가-힣]+구$', last)
    if 모시:
        last = 모시.group(1)
    return re.sub(r'(특별자치도|특별자치시|광역시|특별시|시|군|구|도)$', '', last) or last


def 거르기(sgg, title, link):
    """세 가지를 걸어 (판정, 까닭, 열린 주소, 첫화면 제목)을 돌려준다.

    판정: '통과' · '버림'(우리가 판단할 수 있고 틀렸다) · '보류'(남의 서버 사정으로 판단 못 한다)
    """
    if not link.startswith('http'):
        return '버림', '주소가 아님', link, ''
    if not 관청_도메인(link):
        return '버림', f'① 관청 도메인 아님({re.sub(r"^https?://", "", link).split("/")[0]})', link, ''
    if not 청으로_끝나나(title):
        return '버림', f"② 이름이 '청'으로 끝나지 않음({title})", link, ''
    opened, page, 덧말 = 첫화면_제목(link)
    if not opened:
        return '보류', f'③ 첫 화면을 열지 못함({page})', link, ''
    if not page.strip():
        return '보류', '③ 제목이 비어 있음(자바스크립트로 그리는 곳)', opened, ''
    납작 = re.sub(r'\s+', '', page)
    if 이름_어간(sgg) not in 납작 and re.sub(r'\s+', '', sgg.split()[-1]) not in 납작:
        return '버림', f'③ 첫 화면 제목에 시군구 이름 없음({page[:40]})', opened, page
    return '통과', 덧말, opened, page


def one(key):
    sido, sgg = key
    name = office_name(sido, sgg)
    버린것 = []
    for it in search(f'{sido} {name}'):
        title = re.sub(r'<[^>]+>', '', it['title'])
        link = it.get('link') or ''
        판정, why, opened, page = 거르기(sgg or sido, title, link)
        if 판정 == '통과':
            return {'기관': title, '홈페이지': opened, '첫화면제목': page, **({'비고': why} if why else {})}
        버린것.append(f'{title} {link} — [{판정}] {why}')
    return {'못 찾음': 버린것}


def 기준표():
    d = json.loads(TABLE.read_text(encoding='utf-8'))
    return d['누리집'], d


def verify():
    """찾지 않고, 지금 기준 표에 ①②③를 그대로 걸어 본다 — 267곳을 다시 열어 본다(연 1회)."""
    표, _ = 기준표()
    print(f'기준 표 {len(표)}곳에 세 가지를 걸어 본다 (①관청 도메인 ②이름이 청으로 끝남 ③첫 화면 제목에 시군구 이름)')

    def 하나(kv):
        code, v = kv
        판정, why, opened, page = 거르기(v.get('시군구') or v.get('시도', ''), v['기관'], v['홈페이지'])
        return code, v, 판정, why

    with ThreadPoolExecutor(3) as ex:                          # 지자체 서버를 몰아치지 않는다
        res = list(ex.map(하나, 표.items()))
    버림 = [(c, v, why) for c, v, 판정, why in res if 판정 == '버림']
    보류 = [(c, v, why) for c, v, 판정, why in res if 판정 == '보류']
    print(f'통과 {len(res) - len(버림) - len(보류)}/{len(res)} · 버림 {len(버림)} · 보류 {len(보류)}')
    for 제목, 묶음 in (('버림 — 고쳐야 한다', 버림),
                      ('보류 — 우리가 판단 못 했다(느림·인증서·빈 제목). 브라우저로 직접 본다', 보류)):
        if not 묶음:
            continue
        print()
        print(f'[{제목}]')
        for c, v, why in 묶음:
            print(f'  {c} {v.get("시도","")} {v.get("시군구","")} · {v["기관"]} {v["홈페이지"]}')
            print(f'      → {why}')
    return 버림


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true', help='찾지 않고 기준 표에 거르기만 걸어 본다')
    if ap.parse_args().verify:
        return verify()

    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    g = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('')
    keys = sorted({(r['코드시도'], r['코드시군구']) for _, r in g.iterrows() if r['코드시도']})
    print(f'지자체 {len(keys)}곳 찾기')
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(one, keys))
    sgg = json.loads(SGG.read_text(encoding='utf-8')) if SGG.exists() else {}
    이름별코드 = {}
    for _, r in g.iterrows():                                  # 이름이 아니라 코드를 키로 (T32)
        c = sgg.get(r['개방자치단체코드'])
        if c and r['코드시도']:
            이름별코드.setdefault(f"{r['코드시도']} {r['코드시군구']}".strip(), c)

    out, miss = {}, []
    for (a, b), v in zip(keys, res):
        이름 = f'{a} {b}'.strip()
        if '못 찾음' in v:
            miss.append((이름, v['못 찾음']))
            continue
        out[이름별코드.get(이름, 이름)] = {'시도': a, '시군구': b, **v}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'세 가지를 통과한 후보 {len(out)}/{len(keys)} · 저장: {OUT.relative_to(ROOT)}')
    for 이름, 버린것 in miss:
        print(f'  못 찾음: {이름}')
        for b in 버린것[:3]:
            print(f'      버림: {b}')

    if TABLE.exists():                                         # 표를 덮지 않고 다른 곳만 보여 준다
        표, _ = 기준표()
        다름 = [(c, 표[c]['홈페이지'], out[c]['홈페이지']) for c in out if c in 표 and 표[c]['홈페이지'] != out[c]['홈페이지']]
        새것 = [c for c in out if c not in 표]
        print()
        print(f'기준 표와 대조: 다른 곳 {len(다름)} · 표에 없는 곳 {len(새것)}')
        for c, 전, 후 in 다름[:20]:
            print(f'  {c} 표 {전}  ↔  후보 {후}')
        print('반영은 사람이 한다 — 기준 표를 고치고 고친_기록에 남긴다(이 파일이 표를 덮지 않는다).')


if __name__ == '__main__':
    main()
