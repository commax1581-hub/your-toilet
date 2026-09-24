"""좌표 결과 보고 — 결정된 표시 기준을 적용해 몇 곳이 보이는지, 어디서 빠지는지 숫자로 본다.
표시 기준(docs/사례지식.md 1-4·1-5·2-2):
  구분: 공중·개방·간이 표시, 이동화장실은 따로 셈 / 개방시간 코드 '미개방' 숨김
  좌표: A·B·B산 표시(B산은 "산지에 있음", 장소와 300m 넘게 떨어지면 핀을 장소 좌표로), C·X 숨김, P는 미정
보는 것: 등급 × 도시(동)/농어촌(읍·면), 시군구 종류(구·시·군)별 표시율, 같은 좌표에 몰린 곳, 넓은 곳 후보, P·산지 표본
실행: python report_geo.py [data/processed/toilets_geo.csv]
결과: data/processed/geo_report.md
"""
import re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
P = ROOT / 'data' / 'processed'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
WIDE = re.compile(r'공원|산책로|유원지|해수욕장|해변|둘레길|등산로|수변|캠핑|야영|계곡|저수지|호수|광장|둔치|강변|천변|하천|생태|숲|휴양림|정자|약수|쉼터|폭포|섬|해안|항|포구|체육|운동장|주차장')


def pct(n, d):
    return f'{n:,} ({n / d * 100:.1f}%)' if d else '0'


def area_of(r):
    """도시(동) / 농어촌(읍·면) — 원본 주소나 카카오 주소에 읍·면이 있으면 농어촌"""
    text = ' '.join([r['소재지도로명주소'], r['소재지지번주소'], r['카카오주소']])
    return '농어촌(읍·면)' if re.search(r'\S+[읍면](?=\s|$)', text) else '도시(동)'


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else P / 'toilets_geo.csv'
    g = pd.read_csv(src, dtype=str, encoding='utf-8-sig').fillna('')
    raw = pd.read_csv(max((ROOT / 'data' / 'raw').glob('toilets_*.csv')), dtype=str, encoding='utf-8-sig').fillna('')
    g = g.merge(raw[['개방자치단체코드', '관리번호', '개방시간']], on=['개방자치단체코드', '관리번호'], how='left')
    n = len(g)
    g['지역'] = g.apply(area_of, axis=1)
    g['시군구종류'] = g['코드시군구'].str.strip().str[-1].map({'구': '구', '시': '시', '군': '군'}).fillna('(시도 단위)')
    grade_ok = g['좌표정확도'].isin(['A', 'B', 'B산'])
    kind_ok = g['구분명'].isin(['공중화장실', '개방화장실', '간이화장실'])
    open_ok = g['개방시간'] != '미개방'
    g['표시'] = grade_ok & kind_ok & open_ok
    out = [f'# 좌표 결과 보고 — {src.name}', '', f'전체 {n:,}곳 → **표시 {pct(int(g["표시"].sum()), n)}**', '',
           '## 1. 빠지는 이유(순서대로 하나만 셈)']
    reason = pd.Series('표시', index=g.index)
    reason[~open_ok] = '미개방'
    reason[open_ok & ~kind_ok] = '이동화장실·구분 없음'
    reason[open_ok & kind_ok & ~grade_ok] = '좌표 ' + g['좌표정확도']
    out += [f'- {k}: {pct(v, n)}' for k, v in reason.value_counts().items()] + ['']

    out += ['## 2. 좌표 등급 × 지역', pd.crosstab(g['좌표정확도'], g['지역'], margins=True).to_markdown(), '',
            '### 지역별 표시율']
    for k, s in g.groupby('지역')['표시']:
        out.append(f'- {k}: {pct(int(s.sum()), len(s))}')
    out += ['', '### 시군구 종류별 표시율']
    for k, s in g.groupby('시군구종류')['표시']:
        out.append(f'- {k}: {pct(int(s.sum()), len(s))}')

    shown = g[g['표시']].copy()
    shown['핀위도'] = shown['장소위도'].where(shown['장소위도'] != '', shown['위도'])
    shown['핀경도'] = shown['장소경도'].where(shown['장소경도'] != '', shown['경도'])
    key = shown['핀위도'].astype(float).round(5).astype(str) + ',' + shown['핀경도'].astype(float).round(5).astype(str)
    size = key.map(key.value_counts())
    out += ['', '## 3. 같은 좌표에 몰린 곳(표시 대상 기준)']
    for lo, hi in [(1, 1), (2, 3), (4, 9), (10, 29), (30, 10 ** 6)]:
        m = (size >= lo) & (size <= hi)
        out.append(f'- 한 좌표에 {lo}~{hi if hi < 10 ** 6 else "∞"}곳: 화장실 {pct(int(m.sum()), len(shown))}, 좌표 {key[m].nunique():,}개')
    top = shown.assign(k=key, s=size).sort_values('s', ascending=False).drop_duplicates('k').head(15)
    out += ['', '| 곳 수 | 주소 | 이름 예 |', '|---:|---|---|'] + \
           [f'| {r.s} | {r.카카오주소} | {", ".join(shown.loc[key == r.k, "화장실명"].head(3))} |' for r in top.itertuples()]

    b = shown['좌표정확도'] == 'B'
    wide = b & shown['화장실명'].str.contains(WIDE)
    out += ['', '## 4. 넓은 곳 안내 대상',
            f'- B산(산지) 전부: {int((shown["좌표정확도"] == "B산").sum()):,}곳 — 교차 확인 ' +
            ', '.join(f'{k} {v:,}' for k, v in shown.loc[shown['좌표정확도'] == 'B산', '산지확인'].value_counts().items()),
            f'- B(필지) 중 이름에 공원·산책로·해수욕장 등: {int(wide.sum()):,}곳 / B {int(b.sum()):,}곳',
            '- B 중 이름 표본(넓은 곳 말 없음): ' + ', '.join(shown.loc[b & ~wide, '화장실명'].sample(min(15, int((b & ~wide).sum())), random_state=1))]

    p = g[g['좌표정확도'] == 'P']
    out += ['', f'## 5. P 장소(미정) {len(p):,}곳 표본', '| 화장실명 | 원본 주소 | 찾은 장소 | 유사도 |', '|---|---|---|---:|'] + \
           [f'| {r.화장실명} | {r.소재지도로명주소 or r.소재지지번주소} | {r.카카오장소명} | {r.이름유사도} |' for r in p.sample(min(15, len(p)), random_state=1).itertuples()]
    far = g[g['산지확인'].isin(['중간', '멀리 떨어짐'])]
    out += ['', f'## 6. 산지 중간·멀리 떨어짐 {len(far):,}곳 표본', '| 화장실명 | 필지 | 찾은 장소 | 거리 m |', '|---|---|---|---:|'] + \
           [f'| {r.화장실명} | {r.카카오주소} | {r.카카오장소명} | {r.산지거리m} |' for r in far.sample(min(12, len(far)), random_state=1).itertuples()]
    x = g[g['좌표정확도'] == 'X']
    out += ['', f'## 7. 실패 X {len(x):,}곳 표본'] + [f'- {r.화장실명} | {r.소재지도로명주소 or r.소재지지번주소}' for r in x.sample(min(15, len(x)), random_state=1).itertuples()]

    dst = P / 'geo_report.md'
    dst.write_text('\n'.join(out), encoding='utf-8')
    print('\n'.join(out))


if __name__ == '__main__':
    main()
