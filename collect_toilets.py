"""공중화장실정보 수집 — 행정안전부_공중화장실정보 조회서비스(OpenAPI, data.go.kr 15155058)
- 전국 전체를 페이지 단위로 받아 data/raw/toilets_<날짜>.json(원본 그대로)과 .csv(한글 항목명)로 저장한다.
- 파일데이터(15075531)·표준데이터(15012892)는 같은 원본이고, 다운로드 주소(file.localdata.go.kr)가 403이라 API를 쓴다.
- 좌표(위도·경도)는 2025-02부터 원본에서 빠졌다 → 주소 → 좌표 변환은 다음 단계.
키: 이 폴더 .env의 DATAGOKR_KEY, 없으면 착한식당/.env (같은 공공데이터포털 계정 키, 이 API 활용신청 필요)
실행: python collect_toilets.py [--rows 1000]
"""
import argparse, csv, json, sys, time
from datetime import date
from pathlib import Path
import requests

ROOT = Path(__file__).parent
RAW = ROOT / 'data' / 'raw'
URL = 'https://apis.data.go.kr/1741000/public_restroom_info_v2/info_v2'
ENV_FILES = [ROOT / '.env', ROOT.parent / '착한식당' / '.env']

# API 항목명 → 한글 항목명 (API 명세 순서)
FIELDS = {
    'OPN_ATMY_GRP_CD': '개방자치단체코드', 'MNG_NO': '관리번호', 'SE_NM': '구분명', 'BSS_STT_NM': '근거법령명',
    'RSTRM_NM': '화장실명', 'LCTN_ROAD_NM_ADDR': '소재지도로명주소', 'LCTN_LOTNO_ADDR': '소재지지번주소',
    'MALE_TOILT_CNT': '남성용-대변기수', 'MALE_URNL_CNT': '남성용-소변기수',
    'MALE_FRDBL_TOILT_CNT': '남성용-장애인용대변기수', 'MALE_FRDBL_URNL_CNT': '남성용-장애인용소변기수',
    'MALE_CHLD_TOILT_CNT': '남성용-어린이용대변기수', 'MALE_CHLD_URNL_CNT': '남성용-어린이용소변기수',
    'FEMALE_TOILT_CNT': '여성용-대변기수', 'FEMALE_FRDBL_TOILT_CNT': '여성용-장애인용대변기수',
    'FEMALE_CHLD_TOILT_CNT': '여성용-어린이용대변기수', 'MNG_INST_NM': '관리기관명', 'TELNO': '전화번호',
    'OPN_HR': '개방시간', 'OPN_HR_DTL': '개방시간상세', 'INSTL_YM': '설치연월', 'RSTRM_PSN_SE_NM': '화장실소유구분명',
    'WSTE_PRCS_MTH_NM': '오물처리방식명', 'SFTY_MNG_FCLT_INSTL_TRGT': '안전관리시설설치대상여부',
    'EMRGNCBLL_INSTL_YN': '비상벨설치여부', 'EMRGNCBLL_INSTL_PLC': '비상벨설치장소',
    'RSTRM_ENTRAN_CCTV_INSTL_EN': '화장실입구CCTV설치유무', 'DIAP_EXCHCON_EN': '기저귀교환대유무',
    'DIAP_EXCHCON_PLC': '기저귀교환대장소', 'RMOD_YM': '리모델링연월', 'DAT_CRTR_YMD': '데이터기준일자',
    'LAST_MDFCN_PNT': '최종수정시점', 'DAT_UPDT_PNT': '데이터갱신시점', 'DAT_UPDT_SE': '데이터갱신구분',
}

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8')


def api_key():
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text(encoding='utf-8').splitlines():
                if line.startswith('DATAGOKR_KEY='):
                    return line.split('=', 1)[1].strip()
    sys.exit('DATAGOKR_KEY를 찾지 못했습니다 (.env)')


def fetch(key, page, rows):
    params = {'serviceKey': key, 'pageNo': page, 'numOfRows': rows, 'returnType': 'json'}
    for attempt in range(4):
        try:
            r = requests.get(URL, params=params, timeout=60)
            if r.status_code == 200:
                body = r.json()['response']['body']
                items = body.get('items') or {}
                items = items.get('item', items) if isinstance(items, dict) else items
                return int(body.get('totalCount', 0)), items if isinstance(items, list) else [items]
            if 'NOT_REGISTERED' in r.text or 'ACCESS_DENIED' in r.text:
                sys.exit(f'인증키가 이 API에 등록되지 않았습니다 → data.go.kr 15155058 활용신청 필요\n{r.text[:300]}')
            print(f'  {page}쪽 HTTP {r.status_code}: {r.text[:200]}')
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f'  {page}쪽 오류: {e}')
        time.sleep(2 * (attempt + 1))
    sys.exit(f'{page}쪽을 받지 못했습니다')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', type=int, default=1000, help='한 번에 받을 행 수')
    a = ap.parse_args()
    key = api_key()
    total, items = fetch(key, 1, a.rows)
    pages = -(-total // a.rows)
    print(f'전체 {total:,}건, {pages}쪽')
    for page in range(2, pages + 1):
        _, more = fetch(key, page, a.rows)
        items += more
        if page % 10 == 0:
            print(f'  {page}/{pages}쪽 {len(items):,}건')
        time.sleep(0.2)

    # 검산: 받은 수 = 전체 수, 관리번호 중복
    keys = [(i.get('OPN_ATMY_GRP_CD'), i.get('MNG_NO')) for i in items]
    print(f'받은 {len(items):,}건 / 전체 {total:,}건, (자치단체코드+관리번호) 중복 {len(keys) - len(set(keys))}건')
    unknown = sorted({k for i in items for k in i} - set(FIELDS))
    if unknown:
        print('명세에 없는 항목(원본 구성 변경 의심):', unknown)

    RAW.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime('%Y%m%d')
    (RAW / f'toilets_{stamp}.json').write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
    cols = list(FIELDS) + unknown
    with open(RAW / f'toilets_{stamp}.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow([FIELDS.get(c, c) for c in cols])
        for i in items:
            w.writerow([i.get(c, '') for c in cols])
    print(f'저장: data/raw/toilets_{stamp}.json, .csv')


if __name__ == '__main__':
    main()
