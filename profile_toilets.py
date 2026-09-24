"""수집한 공중화장실 데이터 현황 보고 — 설계 결정에 필요한 숫자를 뽑는다.
보는 것: 구분(공중·개방 등)·소유 구분·시도별 건수, 개방시간 코드와 상세 표기 유형, 주소 빈 칸, 같은 주소 여러 곳,
         기준일자 분포, 비상벨·CCTV·기저귀교환대 비율, 중복
실행: python profile_toilets.py [data/raw/toilets_YYYYMMDD.csv]   (생략하면 가장 최근 파일)
결과: data/processed/profile_<날짜>.md
"""
import re, sys
from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 개방시간은 코드(상시·정시·불규칙·미개방·빈 칸)이고, 시각은 개방시간상세에 자유 형식으로 있다.
# 상세를 '지금 이용 가능' 계산에 쓸 수 있는지 유형으로 나눈다.
HM = r'\d{1,2}\s*:\s*\d{2}\s*[~\-–∼]\s*\d{1,2}\s*:\s*\d{2}'
DTL_TYPES = [
    ('시:분~시:분 하나', re.compile(r'^\s*\(?' + HM + r'\)?\s*$')),
    ('시간대 여러 개(평일·주말 등)', re.compile(HM + r'.*' + HM)),
    ('시:분~시:분 + 설명', re.compile(HM)),
    ('시~시(09~18, 0900-1800)', re.compile(r'\d{1,2}(?:\d{2})?\s*시?\s*[~\-–∼]\s*\d{1,2}(?:\d{2})?\s*시?')),
    ('24시간류', re.compile(r'24|상시|연중')),
    ('N시간(시각 없음)', re.compile(r'^\s*\d+\s*시간\s*$')),
    ('근무·영업시간 등 말', re.compile(r'근무|영업|운영|개장|공연|하절기|동절기|일출|일몰')),
]


def dtl_type(v):
    v = str(v or '').strip()
    if not v:
        return '빈 칸'
    for name, rx in DTL_TYPES:
        if rx.search(v):
            return name
    return '기타'


SIDO = ['서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시', '대전광역시', '울산광역시', '세종특별자치시', '경기도',
        '강원특별자치도', '충청북도', '충청남도', '전북특별자치도', '전남광주통합특별시', '경상북도', '경상남도', '제주특별자치도']


def sido(addr):
    a = str(addr or '').strip().split()
    return a[0] if a else '(주소 없음)'


def pct(n, d):
    return f'{n:,} ({n / d * 100:.1f}%)' if d else '0'


def table(counter, total, head=('값', '건수'), limit=None):
    rows = [f'| {head[0]} | {head[1]} |', '|---|---:|']
    for k, n in counter.most_common(limit):
        rows.append(f'| {k if str(k).strip() else "(빈 칸)"} | {pct(n, total)} |')
    return '\n'.join(rows)


def main():
    raw = ROOT / 'data' / 'raw'
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else max(raw.glob('toilets_*.csv'))
    df = pd.read_csv(path, dtype=str, encoding='utf-8-sig').fillna('')
    n = len(df)
    road, lot = df['소재지도로명주소'].str.strip(), df['소재지지번주소'].str.strip()
    addr = road.where(road != '', lot)
    out = [f'# 공중화장실 데이터 현황 — {path.name}', '', f'전체 **{n:,}곳**', '']

    out += ['## 1. 구분', table(Counter(df['구분명']), n), '']
    out += ['## 2. 화장실 소유 구분', table(Counter(df['화장실소유구분명']), n), '']
    out += ['## 3. 근거 법령', table(Counter(df['근거법령명']), n), '']
    sd = addr.map(sido)
    ok = sd.isin(SIDO)
    out += ['## 4. 시도(주소 첫 단어)', table(Counter(sd[ok]), n), '',
            f'- 시도명으로 시작하지 않는 주소 {pct(int((~ok).sum()), n)} — 띄어쓰기 없음·줄임말(울산·경남)·시군구부터 시작',
            '- 표본: ' + ' / '.join(addr[~ok].head(8)), '']

    code = df['개방시간'].str.strip().replace('', '(빈 칸)')
    dt = df['개방시간상세'].map(dtl_type)
    out += ['## 5. 개방시간', '### 개방시간 코드', table(Counter(code), n), '',
            '### 구분 × 개방시간 코드', pd.crosstab(df['구분명'].replace('', '(빈 칸)'), code, margins=True).to_markdown(), '',
            '### 코드 × 개방시간상세 유형', pd.crosstab(code, dt, margins=True).to_markdown(), '',
            '### 정시인데 상세가 "기타"·"말"인 원문 상위 25']
    odd = df.loc[(code == '정시') & dt.isin(['기타', '근무·영업시간 등 말']), '개방시간상세'].value_counts().head(25)
    out += [f'- `{k}` {v:,}' for k, v in odd.items()]
    out += ['', '### 개방시간상세 원문 상위 30', table(Counter(df['개방시간상세'].str.strip()), n, limit=30), '']

    both = (road == '') & (lot == '')
    out += ['## 6. 주소', f'- 도로명주소 있음 {pct((road != "").sum(), n)} / 지번만 있음 {pct(((road == "") & (lot != "")).sum(), n)} / 둘 다 없음 {pct(both.sum(), n)}']
    same = addr[addr != ''].value_counts()
    out += [f'- 같은 주소에 2곳 이상: 주소 {int((same > 1).sum()):,}개, 화장실 {int(same[same > 1].sum()):,}곳 (좌표가 겹칠 곳)',
            f'- 번지·건물번호 없는 주소(시군구·동까지만, 좌표가 구청 등으로 잡힐 곳) {pct(int((~addr.str.contains(r"\d")).sum()), n)}',
            '- 같은 주소 상위 10: ' + ', '.join(f'{k}({v})' for k, v in same.head(10).items()), '']

    dup_key = df.duplicated(['개방자치단체코드', '관리번호'], keep=False).sum()
    dup_na = df.duplicated(['화장실명', '소재지도로명주소', '소재지지번주소'], keep=False).sum()
    out += ['## 7. 중복', f'- (자치단체코드+관리번호) 중복 {dup_key:,}행', f'- (화장실명+주소) 중복 {dup_na:,}행', '']

    ymd = df['데이터기준일자'].str[:4]
    out += ['## 8. 데이터 기준일자(연도)', table(Counter(ymd), n), '']
    out += ['## 9. 편의·안전 시설']
    for c in ['비상벨설치여부', '화장실입구CCTV설치유무', '기저귀교환대유무', '안전관리시설설치대상여부']:
        out += [f'- {c}: ' + ', '.join(f'{k or "(빈 칸)"} {v:,}' for k, v in Counter(df[c]).most_common(6))]
    fr = (pd.to_numeric(df['남성용-장애인용대변기수'], errors='coerce').fillna(0) + pd.to_numeric(df['여성용-장애인용대변기수'], errors='coerce').fillna(0)) > 0
    out += [f'- 장애인용 대변기 있음: {pct(int(fr.sum()), n)}', '']

    dst = ROOT / 'data' / 'processed' / f'profile_{path.stem.split("_")[-1]}.md'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text('\n'.join(out), encoding='utf-8')
    print('\n'.join(out[:40]))
    print(f'\n저장: {dst.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
