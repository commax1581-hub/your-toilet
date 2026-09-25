"""주간 갱신 — 한 명령으로 수집 → 변경 분류 → 바뀐 곳만 정제·좌표 → 보고서. 처음 3개월은 '제안'만 만들고 승인 후 반영.
설계: docs/사례지식.md 1-6(갱신 구조), ../착한식당/docs/공공데이터-파이프라인.md 8장

  python update.py                       수집 + 제안 만들기 → data/processed/update_<날짜>/ (대장·기준본은 그대로)
  python update.py --raw FILE            수집 없이 이 원본으로(시험·재실행)
  python update.py --publish DIR         제안 반영: 확인 목록 결정(이어받기) → 대장 → 기준본 → 캠퍼스 건물 좌표 → 위치 검증

바뀐 곳만 다시 처리(주소 정제·좌표): 신규 · 주소 변경 · 삭제+신규 짝의 새 번호 · 지난번 좌표 C/X(지자체가 고쳤을 수 있음) · 수기 주소 보정
나머지는 지난 기준본의 좌표를 그대로 이어받는다(카카오 캐시를 새로 받아도 핀이 흔들리지 않게). 주소 외 항목(이름·시간·설비)은 이번 원본 값.
이상 감지(diff_update 반영 중단 조건)에 걸리면 멈추고, 앱 데이터는 지난 판 그대로.
수기 주소 보정: data/address_overrides.csv (영구번호, 수정주소, 사유, 날짜) — 원천 오류를 급히 고칠 때, 다음 갱신에도 유지
"""
import argparse, json, shutil, subprocess, sys
from collections import Counter
from datetime import date
from pathlib import Path
import pandas as pd
import addr_util as au
import build_registry as br
import diff_update as du
import geocode_toilets as gt
from hours import parse as parse_hours
from refine_address import code_regions, RANK

ROOT = Path(__file__).parent
P = ROOT / 'data' / 'processed'
OVR = ROOT / 'data' / 'address_overrides.csv'
GEO_COLS = ['위도', '경도', '좌표정확도', '좌표출처', '카카오주소', '카카오주소종류', '조회주소', '카카오장소ID', '카카오장소명',
            '이름유사도', '산지확인', '산지거리m', '장소위도', '장소경도', '좌표비고']
ADDR_COLS = ['코드시도', '코드시군구', '조회주소종류', '검증결과', '정규주소', '지번주소', '우편번호', 'juso시도', 'juso시군구', '읍면동',
             '건물명', '건물관리번호', '행정구역코드', '도로명코드', '지하여부', '건물본번', '건물부번', '후보수', '비고']
SHOWN = ['A', 'B', 'B산', 'P']
MOVE_LIMIT = 100          # 갱신에서 이보다 많이 움직인 좌표는 확인 목록(핀이 조용히 이동하는 것 방지)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def overrides(reg):
    """영구번호 → 수정주소, 관리번호 기준으로 바꿔 돌려준다"""
    if not OVR.exists():
        return {}
    o = pd.read_csv(OVR, dtype=str, encoding='utf-8-sig').fillna('')
    back = {v: k for k, v in reg['by_mng'].items()}
    return {back[r.영구번호]: r.수정주소 for r in o.itertuples() if r.영구번호 in back and r.수정주소}


def refine_one(row, sido, sgg, fixed=''):
    """refine_address.py와 같은 규칙: 도로명(없으면 지번) → 정상이 아니면 지번 → 더 나은 결과"""
    road, lot = (fixed or row['소재지도로명주소']).strip(), row['소재지지번주소'].strip()
    first = road or lot
    best, used = au.lookup(first, sido, sgg), ('수기 보정' if fixed else '도로명' if road else '지번')
    road_res = best['검증결과']
    if best['검증결과'] != '정상' and road and lot:
        alt = au.lookup(lot, sido, sgg)
        if RANK[alt['검증결과']] < RANK[best['검증결과']]:
            best, used = alt, '지번(2차)'
    out = {**{k: v for k, v in best.items() if k != '조회'}, '조회주소종류': used, '확인필요': ''}
    if used == '지번(2차)' and road_res in ('지역불일치', '주소없음'):
        # 도로명이 틀렸거나 지번이 옛 주소일 수 있다(도로명만 고치고 지번을 안 고친 경우) → 사람이 확인
        out['확인필요'] = f'도로명 {road_res} → 지번으로 찾음'
    return out


def propose(raw_file):
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    out = P / f'update_{date.today():%Y%m%d}'
    s = du.run(snap, raw_file, out)
    if s['반영중단']:
        print('\n반영 중단 — 지난 판을 그대로 둡니다. 보고서를 확인하세요:', out / 'report.md')
        sys.exit(1)

    cur = pd.read_csv(raw_file, dtype=str, encoding='utf-8-sig').fillna('')
    prev_geo = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('').set_index('관리번호')
    reg = br.load()
    ovr = overrides(reg)
    reprocess = set(json.loads((P / 'reprocess_ids.json').read_text()))
    retry = set(prev_geo.index[prev_geo['좌표정확도'].isin(['C', 'X'])]) & set(cur['관리번호'])
    targets = reprocess | retry | (set(ovr) & set(cur['관리번호']))
    road, lot = cur['소재지도로명주소'].str.strip(), cur['소재지지번주소'].str.strip()
    regions = code_regions(cur, road.where(road != '', lot))
    print(f'\n다시 처리 {len(targets):,}곳 (신규·주소 변경·짝 {len(reprocess):,} · 지난번 C/X {len(retry):,} · 수기 보정 {len(set(ovr) & set(cur["관리번호"])):,}), 나머지 좌표 이어받기')

    rows = []
    for r in cur.to_dict('records'):
        m = r['관리번호']
        sido, sgg = regions[r['개방자치단체코드']]
        base = {c: r[c] for c in ['개방자치단체코드', '관리번호', '구분명', '화장실명', '소재지도로명주소', '소재지지번주소']}
        if m in targets or m not in prev_geo.index:
            a = refine_one(r, sido, sgg, ovr.get(m, ''))
            row = {**base, '코드시도': sido, '코드시군구': sgg, **a}
            row.update(gt.locate(row))
            row['처리'] = '다시 처리'
        else:
            keep = prev_geo.loc[m]
            row = {**base, **{c: keep.get(c, '') for c in ADDR_COLS + GEO_COLS}, '처리': '이어받기'}
        rows.append(row)
    au.save_cache(); gt.save_cache()
    geo = pd.DataFrame(rows).reindex(columns=['개방자치단체코드', '관리번호', '구분명', '화장실명', '소재지도로명주소', '소재지지번주소']
                                     + ADDR_COLS + GEO_COLS + ['처리', '확인필요'])
    geo.to_csv(out / 'toilets_geo.csv', index=False, encoding='utf-8-sig')
    shutil.copy2(raw_file, out / 'toilets_raw.csv')

    # 보고서 덧붙이기: 다시 처리한 곳 결과, 사람이 볼 목록, 표시 곳 수 변화
    t = geo[geo['처리'] == '다시 처리']
    newly_bad = t[(t['좌표정확도'].isin(['C', 'X']) & ~t['관리번호'].isin(retry)) | (t['확인필요'].fillna('') != '')]
    fixed = t[t['관리번호'].isin(retry) & t['좌표정확도'].isin(SHOWN)]
    ch = pd.read_csv(out / 'changes.csv', dtype=str).fillna('')

    # 좌표가 **조용히 멀리 움직인 곳** — 지난 기준본과 대조한다.
    # 이름·주소가 그대로인데 핀만 옮겨 가면 사용자는 헛걸음을 하고도 이유를 모른다(T31에서 이 계산이 빠져 있었다).
    def _xy(la, lo):
        try:
            return (float(la), float(lo))
        except (TypeError, ValueError):
            return None

    moved = []
    for r in geo.to_dict('records'):
        m = r['관리번호']
        if m not in prev_geo.index:
            continue
        now_xy, old_xy = _xy(r['위도'], r['경도']), _xy(prev_geo.at[m, '위도'], prev_geo.at[m, '경도'])
        if not now_xy or not old_xy:
            continue
        d = gt.dist_m(now_xy, old_xy)
        if d > MOVE_LIMIT:
            moved.append({'관리번호': m, '화장실명': r['화장실명'], '이동m': round(d),
                          '주소': r['소재지도로명주소'] or r['소재지지번주소'],
                          '지난등급': prev_geo.at[m, '좌표정확도'], '이번등급': r['좌표정확도'], '처리': r['처리'],
                          '지도': f"https://map.kakao.com/link/map/{r['화장실명']},{r['위도']},{r['경도']}"})
    moved_far = sorted(moved, key=lambda x: -x['이동m'])

    # **같은 번호, 다른 시설** — 관리번호는 그대로인데 이름과 주소가 함께 바뀌고 좌표까지 멀리 옮겨 갔다면
    # 지자체가 번호를 **다시 쓴 것**일 수 있다. 그러면 우리 영구번호(공유 링크)가 엉뚱한 곳을 가리킨다.
    # 행정구역 개편으로 주소 표기만 바뀐 것과 가르려고 **좌표 이동**을 함께 본다(2026-09-25 리허설에서 발견).
    item = ch.groupby('관리번호')['항목'].apply(lambda v: set('·'.join(v).split('·')))
    both = {m for m, s in item.items() if '이름' in s and '주소' in s}
    # 판정은 **제안**까지만 한다. 이름·주소가 함께 바뀌고 좌표가 1km 넘게 뛰었으면 거의 확실히 다른 시설이지만,
    # 번호를 폐기하는 일은 되돌리기 어려워 마지막 결정은 사람이 한다(결정 칸).
    swapped = [{**x, '결정': '다른 시설' if x['이동m'] >= 1000 else '같은 시설'} for x in moved_far if x['관리번호'] in both]
    hr_changed = set(ch.loc[ch['항목'].str.contains('개방시간'), '관리번호'])
    hrs = [(r['관리번호'], r['화장실명'], r['개방시간상세'], parse_hours(r['개방시간'], r['개방시간상세'])) for r in cur.to_dict('records')
           if r['관리번호'] in targets or r['관리번호'] in hr_changed]
    unread = [(m, n, d, p['reason']) for m, n, d, p in hrs if p['kind'] == 'unknown' and p['reason'].startswith('읽지 못함')]
    shown_prev = int(prev_geo['좌표정확도'].isin(SHOWN).sum())
    shown_now = int(geo['좌표정확도'].isin(SHOWN).sum())
    lines = ['', '## 바뀐 곳 처리 결과',
             f'- 다시 처리 {len(t):,}곳 → 좌표 등급 ' + ', '.join(f'{k} {v:,}' for k, v in Counter(t['좌표정확도']).most_common()),
             f'- 지난번 C/X였다가 이번에 표시 가능해진 곳 {len(fixed):,}',
             f'- 좌표 표시 가능(A·B·B산) {shown_prev:,} → {shown_now:,}',
             '', f'## 사람이 볼 목록',
             f'1. 삭제+신규 짝 {s["확인목록"]:,}건 — review.csv (추천: 이어받기, 결정 칸 수정 가능)',
             f'2. 새로 생긴 좌표 실패·대략, 도로명·지번 엇갈림 {len(newly_bad):,}곳 — new_bad_coords.csv (원천 오류 신고 또는 data/address_overrides.csv)',
             f'3. 좌표가 {MOVE_LIMIT}m 넘게 움직인 곳 {len(moved_far):,} — moved_coords.csv (핀이 조용히 이동하지 않게 확인)',
             f'4. 읽지 못한 개방시간 표기 {len(unread):,}곳 — unread_hours.csv (자주 나오면 hours.py 규칙 + test_hours.py)',
             f'5. **같은 번호, 다른 시설** 의심 {len(swapped):,}곳 — swapped_ids.csv (결정 칸: 다른 시설 → 옛 번호 폐기·새 번호 / 같은 시설 → 그대로)',
             '', f'반영: `python update.py --publish {out.relative_to(ROOT).as_posix()}`']
    # 품질 지표(갱신마다 기록해 추세를 본다)
    from hours import parse as _ph
    kinds = Counter(_ph(r['개방시간'], r['개방시간상세'])['kind'] for r in cur.to_dict('records'))
    shown_kinds = Counter(geo['좌표정확도'])
    q = {'표시 가능(A·B·B산·P)': shown_now, '좌표 등급': dict(shown_kinds.most_common()),
         '시간 해석률': f"{(kinds['always'] + kinds['hours']) / max(len(cur) - kinds['closed'], 1):.1%}",
         '확인 필요': kinds['unknown']}
    lines += ['', '## 품질 지표(추세 확인용)'] + [f'- {k}: {v}' for k, v in q.items()]
    (out / 'quality.json').write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding='utf-8')

    # 표본 검수: 이번에 새로 처리·매핑된 곳 30곳을 지도 링크와 함께
    samp = t.sample(min(30, len(t)), random_state=1)
    rows = [{'영구번호': r.영구번호 if hasattr(r, '영구번호') else '', '관리번호': r.관리번호, '화장실명': r.화장실명,
             '주소': r.소재지도로명주소 or r.소재지지번주소, '좌표정확도': r.좌표정확도, '좌표비고': r.좌표비고,
             '지도': f'https://map.kakao.com/link/map/{r.화장실명},{r.위도},{r.경도}' if r.위도 else '',
             '로드뷰': f'https://map.kakao.com/link/roadview/{r.위도},{r.경도}' if r.위도 else '', '결정': ''}
            for r in samp.itertuples()]
    pd.DataFrame(rows).to_csv(out / 'sample_check.csv', index=False, encoding='utf-8-sig')
    lines += ['', f'## 표본 검수 {len(rows)}곳 — sample_check.csv (지도·로드뷰 링크, 틀리면 결정 칸에 "숨김")']

    newly_bad[['관리번호', '화장실명', '소재지도로명주소', '소재지지번주소', '좌표정확도', '검증결과', '확인필요', '좌표비고']].to_csv(out / 'new_bad_coords.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(moved_far, columns=['관리번호', '화장실명', '이동m', '주소', '지난등급', '이번등급', '처리', '지도']).to_csv(out / 'moved_coords.csv', index=False, encoding='utf-8-sig')
    for x in swapped:                                     # 옛 이름·주소를 함께 적어 사람이 눈으로 가를 수 있게
        old = prev_geo.loc[x['관리번호']]
        x['옛이름'], x['옛주소'] = old.get('화장실명', ''), old.get('소재지도로명주소', '') or old.get('소재지지번주소', '')
    pd.DataFrame(swapped, columns=['관리번호', '결정', '화장실명', '옛이름', '이동m', '주소', '옛주소', '지난등급', '이번등급', '지도']).to_csv(out / 'swapped_ids.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(unread, columns=['관리번호', '화장실명', '개방시간상세', '이유']).to_csv(out / 'unread_hours.csv', index=False, encoding='utf-8-sig')
    with open(out / 'report.md', 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def publish(d):
    d = Path(d)
    summary = json.loads((d / 'summary.json').read_text(encoding='utf-8'))
    if summary['반영중단']:
        sys.exit('반영 중단된 제안은 반영할 수 없습니다')
    if (d / 'review.csv').exists() and (d / 'review.csv').stat().st_size > 3:
        du.apply_review(d)                                  # 결정 칸이 '이어받기'인 짝만
    raw = pd.read_csv(d / 'toilets_raw.csv', dtype=str, encoding='utf-8-sig').fillna('')
    reg = br.load()
    today = date.today().isoformat()
    # **같은 번호, 다른 시설** — 사람이 '다른 시설'로 결정한 것만 옛 번호를 폐기하고 새 번호를 준다.
    # 원천 관리번호가 영원하다는 보장이 없기 때문이다(사례지식 6-33). assign보다 먼저 해야 새 번호가 제대로 붙는다.
    sw = d / 'swapped_ids.csv'
    retired = 0
    if sw.exists() and sw.stat().st_size > 3:
        for r in pd.read_csv(sw, dtype=str).fillna('').to_dict('records'):
            if r.get('결정', '').strip() != '다른 시설':
                continue
            n = br.retire(reg, r['관리번호'], {'옛이름': r.get('옛이름', ''), '옛주소': r.get('옛주소', ''),
                                              '새이름': r.get('화장실명', ''), '새주소': r.get('주소', '')}, today)
            if n:
                retired += 1
                print(f"  번호 폐기: {r.get('옛이름', '')} → {n} (새 시설: {r.get('화장실명', '')}, {r['이동m']}m 이동)")
    new, gone = br.assign(reg, raw['관리번호'], today)
    br.save(reg)
    stamp = d.name.split('_')[-1]
    snap = ROOT / 'data' / 'snapshots' / stamp
    snap.mkdir(parents=True, exist_ok=True)
    shutil.copy2(d / 'toilets_raw.csv', snap / 'toilets_raw.csv')
    g = pd.read_csv(d / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('').drop(columns=['처리', '확인필요'])
    g.insert(0, '영구번호', g['관리번호'].map(reg['by_mng']))
    g.to_csv(snap / 'toilets_geo.csv', index=False, encoding='utf-8-sig')
    print(f'대장: 새 번호 {new:,}, 숨김 {gone:,}, 폐기 {retired:,} · 기준본 저장 data/snapshots/{stamp}/')
    subprocess.run([sys.executable, str(ROOT / 'campus_coords.py')], check=True)   # 새로 몰린 곳 포함 캠퍼스 건물 좌표 다시(캐시 재사용)
    subprocess.run([sys.executable, str(ROOT / 'verify_locations.py')], check=True)  # 도로명·지번 어긋남·필지 번지 불일치 검증(T11·T12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw'); ap.add_argument('--publish')
    a = ap.parse_args()
    if a.publish:
        return publish(a.publish)
    if a.raw:
        raw_file = Path(a.raw)
    else:
        subprocess.run([sys.executable, str(ROOT / 'collect_toilets.py')], check=True)
        raw_file = max((ROOT / 'data' / 'raw').glob('toilets_*.csv'))
    propose(raw_file)


if __name__ == '__main__':
    main()
