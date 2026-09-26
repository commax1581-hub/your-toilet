"""외부 링크 생존 확인 — 배포 전과 갱신 때 돌린다.

시군구 홈페이지 219곳은 **사용자가 오류를 신고하는 통로**다. 죽은 링크는 그 통로를 막는다.
지도·로드뷰 같은 고정 링크도 함께 본다.

**주의: 동시에 많이 부르면 멀쩡한 곳도 실패로 나온다.** 처음 병렬 12로 돌렸더니 96곳이 실패로 나왔는데,
순차로 다시 재니 11곳이었다(대구 8곳은 전부 정상이었다). → 병렬은 4까지, 실패한 곳만 **순차로 두 번 더** 확인한다.

  python check_links.py            시군구 홈페이지 + 고정 링크
  python check_links.py --fast     고정 링크만(빠름)
"""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'
FIXED = {  # 앱이 쓰는 고정 링크(좌표는 대구 반월당역)
    '카카오 길찾기': 'https://map.kakao.com/link/to/반월당역,35.864498,128.593337',
    '카카오 로드뷰': 'https://map.kakao.com/link/roadview/35.864498,128.593337',
    '네이버 도보': 'https://map.naver.com/p/directions/-/128.593337,35.864498,반월당역/-/walk',
    '구글 지도': 'https://www.google.com/maps/search/?api=1&query=35.864498,128.593337',
    '공공데이터포털 신고': 'https://www.data.go.kr/tcs/opd/ndm/view.do',
}
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def hit(url, timeout=25):
    r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-L', '--max-time', str(timeout),
                        '-w', '%{http_code}', '-A', UA, url], capture_output=True, text=True)
    return (r.stdout or '000').strip()[-3:]


def check(url, tries=1):
    for _ in range(tries):
        c = hit(url)
        if c == '200':
            return c
    return c


def main():
    print('■ 고정 링크')
    for name, url in FIXED.items():
        c = check(url, 2)
        print(f'  {"OK  " if c == "200" else "확인"} {name:14} {c}')
    if '--fast' in sys.argv:
        return

    gov = json.loads((ROOT / 'data' / 'gov_sites.json').read_text(encoding='utf-8'))
    # 키가 시군구코드라 그대로 쓰면 읽기 어렵다 — 이름을 붙여 보여 준다(T32 뒤 코드 키로 바뀜)
    items = [(f"{k} {v.get('시도','')} {v.get('시군구','')}".strip(), v['홈페이지']) for k, v in gov.items()]
    print(f'\n■ 시군구 홈페이지 {len(items)}곳 (동시 4)')
    with ThreadPoolExecutor(max_workers=4) as ex:
        first = list(ex.map(lambda it: (it[0], it[1], hit(it[1])), items))
    bad = [(k, u) for k, u, c in first if c != '200']
    print(f'  1차: 정상 {len(first) - len(bad)} · 확인 대상 {len(bad)}')

    still = []
    for k, u in bad:                                   # 동시 호출 탓에 실패한 것을 걸러낸다
        if check(u, 2) != '200':
            still.append((k, u, check(u.replace('http://', 'https://'), 1)))
    print(f'  2차(순차 재시도): 남은 곳 {len(still)}')
    for k, u, alt in still:
        tip = ' → https로는 열림(고치면 됨)' if alt == '200' else ''
        print(f'   {k:26} {u}{tip}')
    if not still:
        print('  모두 정상')


if __name__ == '__main__':
    main()
