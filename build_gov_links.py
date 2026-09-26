"""지자체 홈페이지 주소 모으기 — 원본(주소·시간·시설) 오류는 그 지자체가 고쳐야 한다.
앱에서 "이 화장실 정보가 틀렸나요?"를 누르면 ① 관리기관 전화(데이터에 있음) ② 해당 시군구 홈페이지 ③ 공공데이터포털 오류신고로 안내한다.
네이버 지역검색이 장소의 홈페이지(link)를 함께 주므로 시군구청을 찾아 주소를 받는다(무료).

**네이버는 '○○구청'으로 찾으면 근처 가게를 준다.** 267곳 중 12곳이 다이소·버거킹·하나은행·카페·식당·인스타그램·블로그였다
(2026-09-26 장학금 세션이 전수 열어 제목을 확인하고 고쳤다 — 사례지식 6-40). 이름에 '강북'이 들어가면 통과시킨 탓이다.
→ 후보마다 **네 가지**를 거른다. 하나라도 어긋나면 버리고 **왜 버렸는지 남긴다.** 싼 것부터 본다.
  ④ **네이버가 준 갈래(category)가 `공공,사회기관`인가** — 가장 싸고 가장 강하다(망도, 여는 것도 필요 없다).
     `다이소 강북구청사거리점`=쇼핑,유통>종합생활용품 · `버거킹 서귀포시청점`=양식>햄버거 · `카페마일로 거제시청점`=카페,디저트>카페
     · `강북구청사거리`=도로시설>교차로. **고친 12곳이 전부 여기서 막힌다**(2026-09-27에 찾음).
  ② **기관 이름이 '청'으로 끝나는가** — '다이소 강북구청사거리점'(점)·'NH농협은행 칠곡군청출장소'(소)를 막는다
  ① 넘어간 **최종 주소**가 **관청 도메인**(`*.go.kr`)인가 — linktr.ee·instagram.com·blog.naver.com·happy700.or.kr을 막는다
  ③ **첫 화면을 열어 제목에 시군구 이름이 있는가** — 죽은 주소·옛 주소를 막는다(동해 http 404 → https만 열림)

**진짜 기관인데 누리집이 비어 있는 경우를 가게로 메우지 않는다.** `거제시청`은 갈래가 `공공,사회기관>시청`인데 `link`가 비어 있어,
옛 코드가 다음 후보로 내려가 **카페마일로 거제시청점**을 집었다. → 그런 곳은 **'누리집 없음'으로 따로 보고**한다. 사람이 채울 일이지 가게를 넣을 일이 아니다.

**판정은 셋이다 — 통과 · 버림 · 보류.** 기준 표 267곳에 걸어 보며 **거르기를 세 번 고쳤다.** 겪은 것을 그대로 남긴다.
1. **동시 8갈래·12초**는 멀쩡한 곳을 시간초과로 떨어뜨렸다 → 3갈래·25초. 지자체 인증서가 어긋난 곳도 많다(제목만 읽고 덧말에 남긴다).
2. **② 가 `통영시청 제1청사`(진짜 시청)를 버렸다** → 부속 표현(`본청`·`제1청사`·`청사`·`별관`)을 떼고 '청'을 본다. `출장소`는 떼지 않는다(은행이 그렇게 붙는다).
3. **① 이 진짜 구청 20곳을 버렸다** — 관청이 `go.kr`만 쓰는 게 아니다: `junggu.seoul.kr` · `dong.daegu.kr` · `nowon.kr` · `suseong.kr` ·
   `ycg.kr`(예천군) · `okjc.net`(제천시 — **`jecheon.go.kr`로 넘어가는 옛 주소**) → ①은 **넘어간 최종 주소**로 보고,
   `go.kr`이 아닌 `.kr`은 **버림이 아니라 보류**로 둔다(사람이 본다). 장사 도메인(`co.kr`·`or.kr`·`.com`·`.net`·SNS·블로그)만 버린다.

**③은 문(gate)이 아니라 확인이다.** 이 환경에서 267곳 중 **100곳 남짓이 안 열린다**(강남·성남 같은 큰 곳도 시간초과·TLS).
**못 열린 것을 틀린 것으로 세면 멀쩡한 것을 고치려 든다**(6-39의 교훈). 이름 비교는 **모시 어간**('창원시진해구'→'창원')으로 한다.
게다가 **제목에 이름이 없는 관청도 있다** — 동해시청의 첫 화면 제목은 `대표홈페이지`다. 그래서 ③으로 **버리는 것은 제목이 다른 시군구를
가리킬 때뿐**이고(목포 화장실이 양산시청으로 가는 식), 그냥 이름이 없으면 **보류**다.

**보류는 다른 환경의 기록으로 풀 수 있다.** 공통지식 `시군구_누리집_확인_<날짜>.json`은 267곳을 다른 환경에서 연 기록이다
(장학금 세션, 2026-09-26: 열림·제목 있음 227 · 제목 없음 40). `--verify`는 우리가 못 연 곳을 이 기록으로 확인해 **통과(기록)**로 돌린다.
환경마다 열리는 곳이 다르다는 것 자체가 사실이므로, **누가 언제 어디서 열었는지**를 함께 적는다.

**표를 말없이 덮지 않는다.** 기준 표(`공통지식/기준자료/행정구역/시군구_누리집.json`)에는 사람이 손으로 고친 것과 그 기록이 들어 있다.
이 스크립트는 **후보**를 `data/gov_sites_candidates.json`에 쓰고 **표와 다른 곳만 보여 준다** — 반영은 사람이 한다.

  python build_gov_links.py            후보 모으기(네이버 키 필요) + 기준 표와 대조 — ④②①③ 모두 건다
                                       (④는 수집 때만 쓴다. 기준 표에는 갈래가 없으니 --verify는 ②①③만 건다)
  python build_gov_links.py --verify   찾지 않고, 지금 기준 표 267곳에 ①②③를 그대로 걸어 본다(연 1회 점검)
"""
import argparse, csv, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
import pandas as pd
import requests
from addr_util import env

ROOT = Path(__file__).parent
OUT = ROOT / 'data' / 'gov_sites_candidates.json'
TABLE = ROOT.parent / '공통지식' / '기준자료' / '행정구역' / '시군구_누리집.json'
SGG = ROOT / 'data' / 'sgg_codes.json'
공통 = ROOT.parent / '공통지식' / '기준자료' / '행정구역'
확인기록 = sorted(공통.glob('시군구_누리집_확인_*.json'))
시군구표 = 공통 / '행정구역_시군구.csv'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'ko-KR,ko;q=0.9', 'Connection': 'close'}
requests.packages.urllib3.disable_warnings()       # 인증서 어긋난 지자체가 많다 — 덧말로 남기고 경고는 끈다
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


# 장사·개인 도메인 — 여기 걸리면 관청이 아니다
장사 = ('.co.kr', '.or.kr', '.ne.kr', '.pe.kr', '.re.kr', '.ac.kr', '.hs.kr', '.ms.kr', '.es.kr', '.sc.kr')


def 관청_갈래(category):
    """④ 네이버가 준 갈래가 관청인가 — `공공,사회기관>구청`·`>시청`·`>군청`.

    **망도 필요 없고 열 필요도 없는 가장 싼 문**인데 처음에 안 썼다. 우리가 고친 12곳은 모두 쇼핑·음식점·카페·도로시설이었다.
    """
    return str(category or '').startswith('공공,사회기관')


def 관청_도메인(link):
    """① 주소가 관청 도메인인가 — '통과'·'보류'·'버림'.

    관청은 `go.kr`만 쓰지 않는다: `junggu.seoul.kr`·`dong.daegu.kr`·`nowon.kr`·`ycg.kr`(예천군)이 모두 진짜다.
    그래서 **`go.kr`이면 통과, 그 밖의 `.kr`이면 보류(사람이 본다), 장사 도메인·그 밖은 버림**으로 나눈다.
    **넘어간 최종 주소로 보는 게 맞다** — `okjc.net`은 `jecheon.go.kr`로 넘어가는 제천시의 옛 주소다.
    """
    host = re.sub(r'^https?://', '', link).split('/')[0].split(':')[0].lower()
    if host.endswith('.go.kr') or host == 'go.kr':
        return '통과'
    if host.endswith(장사):
        return '버림'
    if host.endswith('.kr'):
        return '보류'
    return '버림'


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
            return r.url, (re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''), ('' if verify else '인증서 어긋남')
    return None, '', why or '열리지 않음'


def 이름_어간(sgg):
    """제목과 맞출 어간 — 일반구는 모시로, 꼬리(시·군·구)는 뗀다. '창원시진해구'→'창원' · '전주시완산구'→'전주'"""
    last = sgg.split()[-1]
    모시 = re.match(r'(.+?시)[가-힣]+구$', last)
    if 모시:
        last = 모시.group(1)
    return re.sub(r'(특별자치도|특별자치시|광역시|특별시|시|군|구|도)$', '', last) or last


@lru_cache(maxsize=1)
def 어간들():
    """전국 시군구 이름의 어간 — 한 번만 읽는다."""
    rows = csv.DictReader(시군구표.read_text(encoding='utf-8-sig').splitlines())
    return frozenset(이름_어간(r['시군구명']) for r in rows)


def 다른_시군구(page, 우리):
    """제목이 **다른 시군구**를 가리키나 — ③으로 버리는 것은 이때뿐이다(목포 화장실이 양산시청으로 가는 식)."""
    납작 = re.sub(r'\s+', '', page)
    남 = 어간들() - {우리}
    걸린 = [n for n in 남 if len(n) >= 2 and n in 납작]
    return 걸린[0] if 걸린 else ''


def 거르기(sgg, title, link):
    """세 가지를 걸어 (판정, 까닭, 최종 주소, 첫화면 제목)을 돌려준다.

    판정: '통과' · '버림'(우리가 판단할 수 있고 틀렸다) · '보류'(판단할 근거가 모자란다 — 사람이 본다)
    순서: ② 이름(망 없이) → 열어 보기 → ① 최종 주소 → ③ 제목. **①을 최종 주소로 보려면 먼저 열어야 한다.**
    """
    if not link.startswith('http'):
        return '버림', '주소가 아님', link, ''
    if not 청으로_끝나나(title):
        return '버림', f"② 이름이 '청'으로 끝나지 않음({title})", link, ''

    opened, page, 덧말 = 첫화면_제목(link)
    도메인 = 관청_도메인(opened or link)
    if 도메인 == '버림':                                   # 장사·SNS 도메인 — 열리든 말든 관청이 아니다
        host = re.sub(r'^https?://', '', opened or link).split('/')[0]
        return '버림', f'① 관청 도메인 아님({host})', opened or link, page
    if not opened:
        return '보류', f'③ 첫 화면을 열지 못함({덧말}) — 브라우저로 본다', link, ''
    if 도메인 == '보류':
        어긋 = 이름_어간(sgg) not in re.sub(r'\s+', '', page) if page.strip() else True
        host = re.sub(r'^https?://', '', opened).split('/')[0]
        if 어긋:
            return '보류', f'① go.kr이 아닌 .kr({host}) — 제목으로도 확인되지 않음', opened, page
        return '통과', f'① go.kr이 아니지만 제목이 맞다({host})' + (f' · {덧말}' if 덧말 else ''), opened, page
    if not page.strip():
        return '보류', '③ 제목이 비어 있음(자바스크립트로 그리는 곳)', opened, ''
    납작 = re.sub(r'\s+', '', page)
    우리 = 이름_어간(sgg)
    if 우리 not in 납작 and re.sub(r'\s+', '', sgg.split()[-1]) not in 납작:
        남 = 다른_시군구(page, 우리)
        if 남:
            return '버림', f'③ 제목이 다른 시군구를 가리킨다({남} · {page[:34]})', opened, page
        return '보류', f'③ 제목에 이름이 없다({page[:34]}) — 관청도 그런 곳이 있다(동해시청=대표홈페이지)', opened, page
    return '통과', 덧말, opened, page


def one(key):
    sido, sgg = key
    name = office_name(sido, sgg)
    버린것, 누리집없음 = [], []
    for it in search(f'{sido} {name}'):
        title = re.sub(r'<[^>]+>', '', it['title'])
        link, cat = it.get('link') or '', it.get('category') or ''
        if not 관청_갈래(cat):                                  # ④ 먼저 — 가장 싸다
            버린것.append(f'{title} [{cat}] — [버림] ④ 갈래가 관청이 아님')
            continue
        if not link:                                          # 진짜 기관인데 누리집이 비어 있다 → 가게로 메우지 않는다
            누리집없음.append(f'{title} [{cat}]')
            continue
        판정, why, opened, page = 거르기(sgg or sido, title, link)
        if 판정 == '통과':
            return {'기관': title, '갈래': cat, '홈페이지': opened, '첫화면제목': page, **({'비고': why} if why else {})}
        버린것.append(f'{title} {link} — [{판정}] {why}')
    return {'못 찾음': 버린것, **({'누리집 없음': 누리집없음} if 누리집없음 else {})}


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

    # 우리가 못 연 곳은 **다른 환경의 기록**으로 확인한다 — 환경마다 열리는 곳이 다르다
    풀림 = []
    if 확인기록:
        기록본 = json.loads(확인기록[-1].read_text(encoding='utf-8'))
        기록, 날짜 = 기록본['결과'], 기록본.get('확인일', 확인기록[-1].stem)
        남은보류 = []
        for c, v, why in 보류:
            r = 기록.get(c) or {}
            제목 = (r.get('제목') or '').strip()
            우리 = 이름_어간(v.get('시군구') or v.get('시도', ''))
            납작 = re.sub(r'\s+', '', 제목)
            if str(r.get('결과', '')).startswith('열림·제목 있음') and 제목 and (우리 in 납작 or re.sub(r'\s+', '', v.get('시군구') or '') in 납작):
                풀림.append((c, v, 제목))
            else:
                if not r:
                    덧 = ' · 기록에 없음'
                elif 제목:
                    덧 = f' · 기록({날짜})은 열렸지만 제목에 이름이 없다({제목[:24]})'
                else:
                    덧 = f' · 기록({날짜})에서도 제목이 없다 — 브라우저 단계로 열면 나온다'
                남은보류.append((c, v, why + 덧))
        보류 = 남은보류
        print(f'기록({확인기록[-1].name})으로 보류를 푼 곳 {len(풀림)}')
    print(f'통과 {len(res) - len(버림) - len(보류)}/{len(res)}'
          + (f'(이 환경 {len(res) - len(버림) - len(보류) - len(풀림)} + 기록 {len(풀림)})' if 풀림 else '')
          + f' · 버림 {len(버림)} · 보류 {len(보류)}')
    for 제목, 묶음 in (('버림 — 고쳐야 한다', 버림),
                      ('보류 — 우리도 기록도 제목을 못 봤다. 브라우저(자바스크립트 그리는 단계)로 열면 대개 나온다', 보류)):
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
            miss.append((이름, v))
            continue
        out[이름별코드.get(이름, 이름)] = {'시도': a, '시군구': b, **v}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'세 가지를 통과한 후보 {len(out)}/{len(keys)} · 저장: {OUT.relative_to(ROOT)}')
    for 이름, v in miss:
        빈것 = v.get('누리집 없음') or []
        print(f'  못 찾음: {이름}' + (f' · **갈래는 관청인데 누리집이 비어 있음**: {", ".join(빈것[:2])} → 공식 누리집을 찾아 손으로 넣는다' if 빈것 else ''))
        for b in (v.get('못 찾음') or [])[:3]:
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
