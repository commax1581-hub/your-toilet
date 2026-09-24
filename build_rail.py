"""역 좌표표 — 역사 화장실(국가철도공단·서울교통공사)을 지도에 올리기 위한 기준표.
본 데이터와 **합치지 않고 잇는다**(사례지식 6-24). 역 안에서는 좌표 정밀도가 쓸모없어 **역마다 점 하나**만 둔다(6-25).

  python build_rail.py            역 목록 만들고 좌표 채우기 → data/rail_stations.csv
  python build_rail.py --report   지금 표의 상태만 보기

좌표는 **카카오 장소검색**으로 **노선마다 따로** 만든다(환승역은 노선별로 출입구가 떨어져 있다 — 서울역 1↔4호선 332m).
파일 목록에는 **중복이 있다**(노선별 파일 ⊂ 기관 전체 파일). 칸이 모두 같은 행을 지우고, 역명은 **부기를 뗀 이름**으로 묶는다.
서울교통공사 파일에도 위경도가 있지만 **248행 중 53행(21%)이 주소와 2km 넘게 어긋나** 쓰지 않는다
(예: 송정 5호선 — 주소는 서울 강서구인데 좌표는 충남 부여 부근 135km 밖). 그 좌표는 `원본좌표`로 남겨 대조에만 쓴다.
"""
import argparse, glob, json, re, sys, time
from pathlib import Path
import pandas as pd
import requests
from addr_util import env

ROOT = Path(__file__).parent
RAW = ROOT / 'data' / 'raw' / 'rail'
OUT = ROOT / 'data' / 'rail_stations.csv'
CACHE = ROOT / 'data' / 'processed' / 'kakao_station_cache.json'
KEYWORD = 'https://dapi.kakao.com/v2/local/search/keyword.json'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 운영기관 → 검색에 붙일 지역(같은 이름의 다른 역을 집지 않게)
REGION = {'서울교통공사': '서울', '서울시메트로9호선주식회사': '서울', '인천교통공사': '인천',
          '부산교통공사': '부산', '부산김해경전철주식회사': '김해', '대구교통공사': '대구',
          '남양주도시공사': '남양주', '코레일': ''}
OKCAT = re.compile('지하철역|기차역|전철|철도')


def read(f):
    for enc in ('cp949', 'utf-8-sig', 'utf-8'):
        try:
            d = pd.read_csv(f, dtype=str, encoding=enc).fillna('')
            d.columns = [c.strip() for c in d.columns]
            return d
        except Exception:
            pass
    sys.exit(f'읽지 못함: {f}')


BARE = re.compile(r'[\(（].*?[\)）]')        # 역명 부기 — `강변(동서울터미널)` = `강변`


# 개명된 역 — 출처(2025-06)는 옛 이름, 카카오·서울교통공사(2026-02)는 새 이름을 쓴다(사례지식 6-29).
# 앞의 셋은 **새 이름 역과 좌표가 0m**임을 확인했고, 서구청은 **2026-07-01 인천 행정구역 개편**으로
# 서구가 나뉘며 바뀐 이름이다(사용자 확인). 역은 잘 바뀌지 않지만 **이름은 바뀐다.**
RENAMED = {'당고개': '불암산', '뚝섬유원지': '자양', '가정': '가정중앙시장', '서구청': '서해구청'}


def norm(name):
    """역명 조인 키 — 부기와 끝의 '역'을 뗀다.
    출처마다 표기가 다르다: 국가철도공단 `서울역`·`하남검단산역` ↔ 서울교통공사 `서울`·`하남검단산`.
    떼지 않으면 **같은 역이 두 줄**이 된다(보여 줄 때는 원래 이름을 쓴다)."""
    s = BARE.sub('', str(name)).strip()
    s = s[:-1] if len(s) > 2 and s.endswith('역') else s
    return RENAMED.get(s, s)


def stations():
    """24개 파일에서 역 목록을 뽑는다.

    **먼저 중복을 지운다.** 공공데이터포털은 같은 데이터를 **노선별 파일과 기관 전체 파일로 두 번** 올려 둔다
    (부산2·3·4호선 파일은 부산교통공사 파일에 통째로 들어 있고, 분당선·수인분당선 파일은 내용이 같다).
    칸 9개가 모두 같은 행을 지우면 2,210행 → 1,923행(13% 감소).
    역명은 **부기를 뗀 이름**으로 묶는다(안 떼면 `강변`과 `강변(동서울터미널)`이 다른 역이 된다 — 서울 56역이 두 번 잡혔다).
    """
    COLS = ['철도운영기관명', '선명', '역명', '지상구분', '역층', '게이트내외', '출구번호', '상세위치', '화장실구분']
    ks = pd.concat([read(f) for f in glob.glob(str(RAW / '국가철도공단*.csv'))], ignore_index=True)
    before = len(ks)
    ks = ks.drop_duplicates(subset=COLS)
    print(f'국가철도공단 {before:,}행 → 중복 제거 {len(ks):,}행(파일끼리 겹친 {before - len(ks):,}행)')
    ks['역명정규'] = ks['역명'].map(norm)
    rows = []
    for (op, ln, nm), g in ks.groupby(['철도운영기관명', '선명', '역명정규']):
        rows.append({'운영기관': op.strip(), '노선': ln.strip(), '역명': nm, '화장실행': len(g), '출처': '국가철도공단',
                     '역명원본': ' / '.join(sorted(set(g['역명'].str.strip())))})

    s = read(RAW / '서울교통공사_역사공중화장실정보_20260212.csv')
    s = s[s['역명'].str.strip() != '']                     # 빈 행 10개
    s['위도'] = pd.to_numeric(s['위도'], errors='coerce')
    s['경도'] = pd.to_numeric(s['경도'], errors='coerce')
    s['역명정규'] = s['역명'].map(norm)
    for (ln, nm), g in s.groupby(['운영노선명', '역명정규']):
        ok = g.dropna(subset=['위도', '경도'])
        ok = ok[(ok['위도'] > 33) & (ok['위도'] < 39) & (ok['경도'] > 124) & (ok['경도'] < 132)]
        rows.append({'운영기관': '서울교통공사', '노선': ln.strip(), '역명': nm, '화장실행': len(g), '출처': '서울교통공사',
                     '원본위도': round(ok['위도'].mean(), 6) if len(ok) else '', '원본경도': round(ok['경도'].mean(), 6) if len(ok) else '',
                     '주소': g['소재지도로명주소'].iloc[0].strip()})   # 좌표는 믿지 않고 주소만 남긴다
    df = pd.DataFrame(rows).fillna('')
    # 같은 역·노선이 두 출처에 있으면(서울교통공사 239역 전부) 한 줄로 합치고 **출처를 모두 적는다.**
    # 좌표는 어차피 카카오로 다시 만들므로, 여기서는 화장실 행 수를 출처별로 나눠 둔다.
    df['키'] = df['운영기관'] + '|' + df['노선'] + '|' + df['역명']
    agg = []
    for k, g in df.groupby('키', sort=False):
        r = g.iloc[0].to_dict()
        r['출처'] = ' + '.join(g['출처'])
        r['화장실행'] = int(g.loc[g['출처'] == '국가철도공단', '화장실행'].sum()) if (g['출처'] == '국가철도공단').any() else 0
        r['화장실행_서울'] = int(g.loc[g['출처'] == '서울교통공사', '화장실행'].sum()) if (g['출처'] == '서울교통공사').any() else 0
        for c in ('원본위도', '원본경도', '주소', '역명원본'):
            v = [x for x in g.get(c, pd.Series(dtype=str)).tolist() if x != '']
            r[c] = v[0] if v else ''
        agg.append(r)
    out = pd.DataFrame(agg).fillna('')
    both = (out['출처'].str.contains(r'\+')).sum()
    print(f'역·노선 {len(out):,}개(두 출처 모두 가진 것 {both:,}개) · 역 이름 {out["역명"].nunique():,}개')
    return out


def ask(q, key, cache):
    if q in cache:
        return cache[q]
    r = requests.get(KEYWORD, params={'query': q, 'size': 5},
                     headers={'Authorization': f'KakaoAK {key}'}, timeout=10)
    hit = ''
    if r.status_code == 200:
        for d in r.json().get('documents', []):
            if OKCAT.search(d.get('category_name', '')):
                hit = {'la': float(d['y']), 'lo': float(d['x']), 'place': d['place_name'], 'cat': d['category_name'].split('>')[-1].strip()}
                break
    cache[q] = hit
    time.sleep(0.05)
    return hit


def line_q(line):
    """선명을 검색어로 — `수인분당` → `수인분당선`, `1호선`·`부산김해경전철`은 그대로"""
    s = str(line).strip()
    return s if (s.endswith('호선') or s.endswith('선') or '경전철' in s) else s + '선'


def kakao_xy(name, line, region, key, cache, taken=None):
    """**노선별로** 좌표를 찾는다 — 환승역은 노선마다 출입구가 떨어져 있다(서울역 1↔4호선 332m).

    순서: `지역 + 노선 + 역명` → (실패·오답이면) `지역 + 역명` → 괄호 부기 제거 → 지역 없이.
    **카카오가 그 노선에 그 역이 없으면 이웃 역을 준다**(을지로3가 3호선 → 충무로역, 명덕 3호선 → 남산역).
    그래서 돌아온 이름이 **역명을 품고 있는지 반드시 확인하고**, 아니면 노선 없는 질의로 되돌린다.
    노선 표기까지 맞으면 `노선확인=Y`(태릉입구 6호선 질의에 7호선 자리가 오는 일이 있어 구분해 둔다).
    """
    bare = BARE.sub('', name).strip()
    base = name if name.endswith('역') else name + '역'          # 대구역·동대구역·서울역은 '역역'이 되지 않게
    barebase = bare if bare.endswith('역') else bare + '역'
    hit = ask(f'{region} {line_q(line)} {base}'.strip(), key, cache)
    if hit and norm(bare) in hit['place']:
        hit['by'] = '노선'
        hit['line_ok'] = 'Y' if line_q(line).replace('선', '') in hit['place'].replace('선', '') else 'N'
        return hit
    # 이름이 다른 결과는 **버린다.** 카카오는 그 노선에 그 역이 없으면 **이웃 역**을 준다
    # (을지로3가 3호선 → 충무로역 · 동구청 → 동대구역 · 수성못 → 황금역). "빈자리면 개명으로 보자"를
    # 시험했더니 이웃 역 10곳을 같은 자리로 붙여 버렸다 → 개명은 **RENAMED 표로만** 다룬다.
    for q in [f'{region} {base}'.strip(), f'{region} {barebase}'.strip(), barebase]:
        h = ask(q, key, cache)
        if h and norm(bare) in h['place']:
            h['by'], h['line_ok'] = '역', '-'
            return h
    return ''


def merge_same_spot(df):
    """같은 기관·같은 노선에서 **좌표가 300m 안이면 같은 역**으로 보고 한 줄로 합친다.

    **기준을 수치로 정했다.** 같은 노선에서 이름이 다른 역끼리의 거리를 전부 재 보니
    500m 안에 붙은 쌍은 **총신대입구 ↔ 이수(175m) 하나뿐**이고, 그다음이 동대신 ↔ 서대신 514m다.
    즉 300m는 **진짜 다른 역을 붙일 위험이 없는** 자리다(이웃 역은 500m 이상 떨어져 있다).

    이름이 달라도 자리가 같으면 같은 역이다 — **개명**(당고개→불암산 · 뚝섬유원지→자양 · 가정→가정중앙시장)과
    **표기 차이**(서울역↔서울 · 하남검단산역↔하남검단산 · 암사역사공원↔암사역사공원역)를 여기서 흡수한다.
    보여 줄 이름은 **카카오가 준 현재 이름**을 쓰고, 원본 이름은 `역명원본`에 남긴다(출처 대조용).
    """
    from geocode_toilets import dist_m
    ok = df[pd.to_numeric(df.get('위도', ''), errors='coerce').notna()].copy()
    drop, moved, pairs = [], 0, []
    for _, g in ok.groupby(['운영기관', '노선']):
        rows = list(g.iterrows())
        for i, (ia, a) in enumerate(rows):
            if ia in drop:
                continue
            for ib, b in rows[i + 1:]:
                if ib in drop or a['역명'] == b['역명']:
                    continue
                if dist_m((float(a['위도']), float(a['경도'])), (float(b['위도']), float(b['경도']))) < 300:
                    df.at[ia, '화장실행'] = int(a['화장실행'] or 0) + int(b['화장실행'] or 0)
                    df.at[ia, '화장실행_서울'] = int(a.get('화장실행_서울') or 0) + int(b.get('화장실행_서울') or 0)
                    df.at[ia, '역명원본'] = ' / '.join(x for x in [str(a.get('역명원본') or a['역명']), str(b.get('역명원본') or b['역명'])] if x)
                    df.at[ia, '출처'] = ' + '.join(sorted(set(str(a['출처']).split(' + ')) | set(str(b['출처']).split(' + '))))
                    for c in ('원본위도', '원본경도', '주소'):
                        if not str(a.get(c, '')) and str(b.get(c, '')):
                            df.at[ia, c] = b[c]
                    pairs.append(f"{a['역명']}={b['역명']}({a['노선']})")
                    drop.append(ib)
                    moved += 1
    if drop:
        print(f'자리가 같아 합친 역 {moved}개(이름이 다르던 것): ' + ', '.join(pairs[:12]))
        df = df.drop(index=drop)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    df = stations()
    print(f'역 {len(df):,}개(운영기관 {df["운영기관"].nunique()}곳 · 노선 {df["노선"].nunique()}개) · 화장실 행 {df["화장실행"].sum():,}')

    if not a.report:
        key = env('KAKAO_REST_KEY')
        cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
        need = df                                            # 모든 역을 카카오로(원본 좌표는 쓰지 않는다)
        print(f'카카오에 물어볼 역 {len(need):,}')
        got = 0
        taken = {}                                           # (기관,노선) → 이미 쓴 카카오 장소 이름
        for i, (idx, r) in enumerate(need.iterrows(), 1):
            k2 = (r['운영기관'], r['노선'])
            hit = kakao_xy(r['역명'], r['노선'], REGION.get(r['운영기관'], ''), key, cache, taken.setdefault(k2, set()))
            if hit:
                taken[k2].add(hit['place'])
            if hit:
                df.at[idx, '위도'], df.at[idx, '경도'] = hit['la'], hit['lo']
                df.at[idx, '좌표출처'], df.at[idx, '카카오장소'] = '카카오', hit['place']
                df.at[idx, '좌표단위'], df.at[idx, '노선확인'] = hit['by'], hit['line_ok']
                got += 1
            if i % 100 == 0:
                print(f'  {i:,}/{len(need):,} …')
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
        print(f'카카오로 찾음 {got:,} · 못 찾음 {len(need) - got:,}')
        df = merge_same_spot(df)
        df.drop(columns=['키']).to_csv(OUT, index=False, encoding='utf-8-sig')
        print(f'저장: {OUT.relative_to(ROOT)}')

    ok = df[pd.to_numeric(df.get('위도', ''), errors='coerce').notna()]
    print(f'\n■ 좌표 확보 {len(ok):,}/{len(df):,} ({len(ok) / len(df) * 100:.0f}%) · 출처: {ok["좌표출처"].value_counts().to_dict()}')
    bad = ok[(pd.to_numeric(ok['위도']) < 33) | (pd.to_numeric(ok['위도']) > 39) | (pd.to_numeric(ok['경도']) < 124) | (pd.to_numeric(ok['경도']) > 132)]
    print(f'  국내 범위 밖: {len(bad)}건' + ('' if len(bad) == 0 else f' → {bad["역명"].tolist()[:5]}'))
    # 대조 — 서울교통공사가 준 원본 좌표와 우리가 만든 좌표의 차이(원본 품질 기록용)
    from geocode_toilets import dist_m
    both = ok[(ok.get('원본위도', '') != '') & (ok['위도'] != '')]
    if len(both):
        gaps = pd.Series([dist_m((float(r['위도']), float(r['경도'])), (float(r['원본위도']), float(r['원본경도'])))
                          for _, r in both.iterrows()])
        print(f'  원본 좌표 대조 {len(gaps)}곳: 500m 이내 {(gaps <= 500).mean() * 100:.0f}% · 2km 초과 {(gaps > 2000).sum()}곳 → 원본 좌표는 쓰지 않는다')

    miss = df[pd.to_numeric(df.get('위도', ''), errors='coerce').isna()]
    if len(miss):
        print(f'  못 찾은 역 {len(miss)}개: {", ".join(miss["역명"].head(12))}')


if __name__ == '__main__':
    main()
