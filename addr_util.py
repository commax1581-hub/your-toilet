"""주소 정제 공용 모듈 — 도로명주소 API(행정안전부 juso) 대조(캐시), 건물관리번호 추출
착한가격 지도(../착한식당/addr_util.py)에서 가져와 이 데이터에 맞게 고침:
- 결과가 여러 건이면 첫 번째를 채택하지 않고 '모호'로 둔다(번지 없는 주소: '대전광역시 서구' → 24,966건).
  단 후보가 모두 같은 건물(건물관리번호)이면 채택.
- 결과의 시도·시군구가 원본(자치단체코드로 얻은 시도·시군구)과 다르면 '지역 불일치'로 버린다.
- 좌표 변환에 쓸 항목(행정구역코드·도로명코드·지하여부·건물 본번·부번)도 남긴다.
같은 주소 문구는 한 번만 조회하고 data/processed/address_cache.json에 저장해 다음 갱신에 재사용한다.
설계: ../착한식당/docs/공공데이터-파이프라인.md 6장(좌표)·8장(분기 갱신)
"""
import json, re, threading, time
from pathlib import Path
import requests

ROOT = Path(__file__).parent
CACHE_PATH = ROOT / 'data' / 'processed' / 'address_cache.json'
URL = 'https://business.juso.go.kr/addrlink/addrLinkApi.do'
ENV_FILES = [ROOT / '.env', ROOT.parent / '착한식당' / '.env']

_lock = threading.Lock()
_cache = None
_key = None


def env(name):
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text(encoding='utf-8').splitlines():
                if line.startswith(name + '='):
                    return line.split('=', 1)[1].strip()
    raise KeyError(f'{name}를 .env에서 찾지 못했습니다')


def clean(a):
    """괄호·쉼표 뒤·층 이하 제거, 번지·호 표기와 붙어 쓴 번호 정리, 공백 정리
    (좌표 변환 실패 표본에서 나온 형식: '상리692번지', '1008번지 1호', '산애길100-10', '72 4~7층')"""
    a = re.sub(r'\([^)]*\)', ' ', str(a or ''))
    a = re.sub(r'([가-힣]+?)\d+(?:,\d+)+동\s*(?=산?\s*\d)', r'\1동 ', a)   # 행정동 '중계2,3동514-4' → 법정동 '중계동 514-4' (쉼표에서 잘리지 않게, T11)
    a = re.sub(r',.*$', '', a)
    a = re.sub(r'\s*(지하\s*)?\d+\s*[~\-]\s*\d+층.*$', '', a)          # 4~7층
    a = re.sub(r'\s*(지하\s*)?\d+층.*$', '', a)
    a = re.sub(r'(\d+)\s*번지\s*(\d+)\s*호', r'\1-\2', a)              # 473번지 6호 → 473-6
    a = re.sub(r'(\d+(?:-\d+)?)\s*번지', r'\1', a)                    # 692번지 → 692
    a = re.sub(r'([가-힣])(\d+(?:-\d+)?)\s*$', r'\1 \2', a) if re.search(r'(동|리|가)\d+(-\d+)?\s*$', a) else a  # 상리692 → 상리 692
    a = re.sub(r'(로|길)(\d+(?:-\d+)?)(?![\d\-]|번길|번가|가)', r'\1 \2', a)  # 산애길100-10 → 산애길 100-10 (473번길은 그대로)
    return re.sub(r'\s+', ' ', a).strip()


def _load():
    global _cache, _key
    if _cache is None:
        _cache = json.loads(CACHE_PATH.read_text(encoding='utf-8')) if CACHE_PATH.exists() else {}
    if _key is None:
        _key = env('JUSO_KEY')


def save_cache():
    if _cache is not None:
        with _lock:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False), encoding='utf-8')


def _query(kw):
    err = ''
    for _ in range(3):
        try:
            r = requests.get(URL, params={'confmKey': _key, 'currentPage': 1, 'countPerPage': 20,
                                          'keyword': kw, 'resultType': 'json'}, timeout=15)
            j = r.json()['results']
            if j['common']['errorCode'] != '0':
                return None, 0, j['common']['errorMessage']
            return j['juso'] or [], int(j['common']['totalCount']), ''
        except Exception as e:
            time.sleep(1); err = str(e)[:60]
    return None, 0, err


def _same_region(j, sido, sgg):
    if sido and j.get('siNm') != sido:
        return False
    if sgg and sgg.replace(' ', '') not in (j.get('sggNm') or '').replace(' ', '') \
            and (j.get('sggNm') or '').replace(' ', '') not in sgg.replace(' ', ''):
        return False
    return True


EMPTY = {'정규주소': '', '지번주소': '', '우편번호': '', 'juso시도': '', 'juso시군구': '', '읍면동': '', '건물명': '',
         '건물관리번호': '', '행정구역코드': '', '도로명코드': '', '지하여부': '', '건물본번': '', '건물부번': '', '후보수': 0}


def _res(how, j=None, total=0, note=''):
    r = dict(EMPTY, 검증결과=how, 후보수=total, 비고=note)
    if j:
        r.update(정규주소=j.get('roadAddrPart1', ''), 지번주소=j.get('jibunAddr', ''), 우편번호=j.get('zipNo', ''),
                 juso시도=j.get('siNm', ''), juso시군구=j.get('sggNm', ''), 읍면동=j.get('emdNm', ''),
                 건물명=j.get('bdNm', ''), 건물관리번호=j.get('bdMgtSn', ''), 행정구역코드=j.get('admCd', ''),
                 도로명코드=j.get('rnMgtSn', ''), 지하여부=j.get('udrtYn', ''), 건물본번=j.get('buldMnnm', ''),
                 건물부번=j.get('buldSlno', ''))
    return r


ROAD_TAIL = re.compile(r'([가-힣A-Za-z0-9·.]+(?:로|길)\s*(?:지하\s*)?\d+(?:-\d+)?)\s*$')
LOT_TAIL = re.compile(r'([가-힣0-9]+(?:동|리|가)\s*(?:산\s*)?\d+(?:-\d+)?)\s*$')


def _exact(key, cands):
    """후보 중 주소 끝(도로명+건물번호, 또는 동·리+번지)이 정확히 같은 것 — '봉양로408'과 '봉양로408번길 5'를 가른다"""
    ns = lambda s: re.sub(r'\s+', '', s or '')
    m = ROAD_TAIL.search(key)
    if m:
        return [j for j in cands if ns(j.get('roadAddrPart1')).endswith(ns(m.group(1)))]
    m = LOT_TAIL.search(key)
    if m:
        return [j for j in cands if ns(j.get('jibunAddr')).endswith(ns(m.group(1)))]
    return []


def lookup(addr, sido='', sgg=''):
    """주소 → dict(검증결과, 정규주소, 건물관리번호 …, 후보수, 조회)
    검증결과: 정상 / 모호(후보 여러 건물) / 지역불일치 / 주소없음 / 조회실패
    sido·sgg: 원본의 시도·시군구(자치단체코드로 얻은 값). 결과가 이 지역 밖이면 버린다."""
    _load()
    key = clean(addr)
    ck = f'{sido}|{sgg}|{key}'
    with _lock:
        hit = _cache.get(ck)
    if hit is not None:
        return {**hit, '조회': False}
    juso, total, err = _query(key) if key else ([], 0, '')
    if juso is None:
        return {**_res('조회실패', note=err), '조회': True}      # 일시 오류는 저장하지 않는다
    inside = [j for j in juso if _same_region(j, sido, sgg)]
    exact = _exact(key, inside)
    if len(juso) < total:
        exact = []                       # 후보가 다 안 왔으면(20건 초과) 정확 일치도 확신할 수 없다
    if not juso:
        res = _res('주소없음')
    elif not inside:
        res = _res('지역불일치', juso[0], total, f'결과 {juso[0].get("roadAddrPart1", "")}')
    elif total == 1 or len({j['bdMgtSn'] for j in inside}) == 1 and total <= len(juso):
        res = _res('정상', inside[0], total)
    elif len({j['bdMgtSn'] for j in exact}) == 1:
        res = _res('정상', exact[0], total, f'후보 {total}건 중 번지 정확 일치')
    else:
        res = _res('모호', None, total, f'후보 {total:,}건')
    with _lock:
        _cache[ck] = res
    return {**res, '조회': True}
