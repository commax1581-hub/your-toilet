"""갱신 변경 분류 — 지난 기준본과 이번 원본을 관리번호로 비교해 신규·삭제·변경을 나누고, 다시 처리할 곳을 정한다.
착한가격 지도 diff_update.py를 이 데이터에 맞게 고침. 설계: ../공통지식/모듈/공공데이터-파이프라인.md 8장
판정(짝 찾기·이상 감지·확인 목록 규약)은 **공통지식 `도구/update_rules.py`**에 있다 — 세 프로젝트가 같이 쓴다.
여기에는 **이 원천의 사정**만 둔다: 비교할 칸(INFO·ADDR), 기준값(LIMITS), 보고서 꼴, 파일 읽고 쓰기.
원칙: 줄 순서가 아니라 관리번호로 비교(착한가격 #29), "이미 한 곳은 건너뛰기"가 변경을 놓치지 않게 비교 결과로 재처리 대상을 정함(#53)

분류:
  신규        이전에 없던 관리번호 → 주소 정제·좌표·새 영구번호
  삭제        이번에 없는 관리번호 → 숨김(영구번호 보관)
  삭제+신규 짝 삭제 1곳과 신규 1곳이 같은 이름 + 같은 주소 → 확인 목록(추천: 영구번호 이어받기). history_v2 확인에서 6개 지역 138곳 중 18곳이 이 경우
  기존·주소 변경  주소 글자가 바뀜 → 주소 정제 다시(건물관리번호가 같으면 '표기만 변경'으로 좌표 재사용은 refine 단계에서)
  기존·정보 변경  이름·구분·개방시간·변기 수·시설·관리기관·전화 → 값만 갱신
이상 감지(반영 중단): 전체 10% 넘게 감소 / 항목 구성 변경 / 자치단체코드가 바뀐 행 5% 넘음 / 30% 넘게 변경

실행:
  python diff_update.py                        가장 최근 기준본 ↔ 가장 최근 원본(data/raw)
  python diff_update.py --prev DIR --cur FILE  시험용
  python diff_update.py --apply-review DIR     확인 목록의 결정(이어받기) 반영 → 대장
결과: data/processed/update_<날짜>/ report.md · changes.csv · review.csv · summary.json, reprocess_ids.json(다시 정제·좌표할 관리번호)
"""
import argparse, json, re, sys
from collections import Counter
from datetime import date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / '공통지식' / '도구'))
from update_rules import pairs, over_limits, drop_rate, share, inherit_pairs   # noqa: E402
REG = ROOT / 'data' / 'id_registry.json'
SNAP = ROOT / 'data' / 'snapshots'
ADDR = ['소재지도로명주소', '소재지지번주소']
INFO = {'이름': ['화장실명'], '구분': ['구분명', '화장실소유구분명'], '개방시간': ['개방시간', '개방시간상세'],
        '변기 수': ['남성용-대변기수', '남성용-소변기수', '남성용-장애인용대변기수', '남성용-장애인용소변기수',
                  '남성용-어린이용대변기수', '남성용-어린이용소변기수', '여성용-대변기수', '여성용-장애인용대변기수', '여성용-어린이용대변기수'],
        '시설': ['비상벨설치여부', '비상벨설치장소', '화장실입구CCTV설치유무', '기저귀교환대유무', '기저귀교환대장소'],
        '관리': ['관리기관명', '전화번호']}
LIMITS = {'감소율': 0.10, '코드변경율': 0.05, '변경율': 0.30}
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def ns(s):
    return re.sub(r'\s|\([^)]*\)', '', str(s))


def classify(prev, cur):
    p, c = prev.set_index('관리번호'), cur.set_index('관리번호')
    added, removed, common = sorted(set(c.index) - set(p.index)), sorted(set(p.index) - set(c.index)), sorted(set(p.index) & set(c.index))
    changes = []
    for m in common:
        a, b = p.loc[m], c.loc[m]
        items = [k for k, cols in INFO.items() if any(str(a.get(x, '')) != str(b.get(x, '')) for x in cols)]
        if any(ns(a[x]) != ns(b[x]) for x in ADDR):
            items.insert(0, '주소')
        if a['개방자치단체코드'] != b['개방자치단체코드']:
            items.append('자치단체코드')
        if items:
            changes.append({'관리번호': m, '분류': '기존·변경', '항목': '·'.join(items), '화장실명': b['화장실명'],
                            '이전': ' / '.join(f'{x}={a[x]}' for k in items for x in INFO.get(k, ADDR if k == '주소' else ['개방자치단체코드']) if str(a.get(x, '')) != str(b.get(x, ''))),
                            '이번': ' / '.join(f'{x}={b[x]}' for k in items for x in INFO.get(k, ADDR if k == '주소' else ['개방자치단체코드']) if str(a.get(x, '')) != str(b.get(x, '')))})
    # 삭제+신규 짝: 같은 이름 + 같은 주소(도로명 없으면 지번). **판정은 공통**(update_rules.pairs),
    # 키를 무엇으로 볼지만 이 프로젝트가 정한다. 일대일 — 맞는 신규가 딱 하나일 때만 짝으로 본다.
    key = lambda r: (ns(r['화장실명']), ns(r['소재지도로명주소'] or r['소재지지번주소']))
    review = [{'이전관리번호': 옛, '새관리번호': 새, '화장실명': c.loc[새, '화장실명'],
               '주소': c.loc[새, '소재지도로명주소'] or c.loc[새, '소재지지번주소'],
               '추천': '이어받기', '결정': '이어받기'}
              for 옛, 새, _ in pairs({m: p.loc[m] for m in removed}, {m: c.loc[m] for m in added},
                                    keys=[('이름+주소', key)], one_to_one=True)]
    paired_new = {r['새관리번호'] for r in review}
    paired_old = {r['이전관리번호'] for r in review}
    for m in added:
        if m not in paired_new:
            changes.append({'관리번호': m, '분류': '신규', '항목': '', '화장실명': c.loc[m, '화장실명'], '이전': '', '이번': ''})
    for m in removed:
        changes.append({'관리번호': m, '분류': '삭제+신규 짝' if m in paired_old else '삭제', '항목': '', '화장실명': p.loc[m, '화장실명'], '이전': '', '이번': ''})
    return pd.DataFrame(changes, columns=['관리번호', '분류', '항목', '화장실명', '이전', '이번']), pd.DataFrame(review), len(common)


def anomalies(prev, cur, ch, n_common):
    out = []
    if set(prev.columns) != set(cur.columns):
        out.append(f'항목 구성 변경: 없어짐 {sorted(set(prev.columns) - set(cur.columns))}, 새로 {sorted(set(cur.columns) - set(prev.columns))}')
    # 기준값 넘었는지 **판정은 공통**(update_rules.over_limits) — 무엇을 재고 뭐라 말할지는 여기서 정한다
    ex = ch[ch['분류'] == '기존·변경']
    code = int(ex['항목'].str.contains('자치단체코드').sum())
    값 = {'감소율': drop_rate(len(prev), len(cur)),
          '코드변경율': share(code, n_common),
          '변경율': share(len(ex), n_common)}
    말 = {'감소율': f'전체 {len(prev):,} → {len(cur):,}, {LIMITS["감소율"]:.0%} 넘게 감소',
          '코드변경율': f'자치단체코드 바뀐 곳 {code:,} ({값["코드변경율"]:.1%}) — 행정구역 개편 확인',
          '변경율': f'기존 {len(ex):,}곳 변경({값["변경율"]:.1%})'}
    out += [말[이름] for 이름, _, _ in over_limits(값, LIMITS)]
    return out


def run(prev_dir, cur_file, out_dir):
    prev = pd.read_csv(prev_dir / 'toilets_raw.csv', dtype=str, encoding='utf-8-sig').fillna('')
    cur = pd.read_csv(cur_file, dtype=str, encoding='utf-8-sig').fillna('')
    ch, review, n_common = classify(prev, cur)
    stop = anomalies(prev, cur, ch, n_common)
    out_dir.mkdir(parents=True, exist_ok=True)
    ch.to_csv(out_dir / 'changes.csv', index=False, encoding='utf-8-sig')
    review.to_csv(out_dir / 'review.csv', index=False, encoding='utf-8-sig')
    cls = Counter(ch['분류'])
    items = Counter(x for s in ch.loc[ch['분류'] == '기존·변경', '항목'] for x in s.split('·'))
    unchanged = n_common - cls['기존·변경']
    reprocess = sorted(set(ch.loc[ch['분류'] == '신규', '관리번호']) | set(ch.loc[ch['항목'].str.contains('주소'), '관리번호']) | set(review.get('새관리번호', [])))
    summary = {'이전': len(prev), '이번': len(cur), '기존_변경없음': unchanged, **{k: int(v) for k, v in cls.items()},
               '확인목록': len(review), '항목별': dict(items), '다시처리': len(reprocess), '반영중단': stop}
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    (ROOT / 'data' / 'processed' / 'reprocess_ids.json').write_text(json.dumps(reprocess), encoding='utf-8')
    check = unchanged + cls['기존·변경'] + cls['신규'] + len(review) == len(cur) and unchanged + cls['기존·변경'] + cls['삭제'] + cls['삭제+신규 짝'] == len(prev)
    lines = [f'# 갱신 비교 — {prev_dir.name} → {cur_file.name}', '',
             f'이전 {len(prev):,} → 이번 {len(cur):,} | 기존 변경 없음 {unchanged:,} · 기존 변경 {cls["기존·변경"]:,} · 신규 {cls["신규"]:,} · '
             f'삭제 {cls["삭제"]:,} · 삭제+신규 짝 {len(review):,} | 검산 {"맞음" if check else "틀림"}', '',
             '## 기존 변경 항목별(한 곳이 여러 항목)'] + [f'- {k}: {v:,}' for k, v in items.most_common()] + \
            ['', f'## 다시 정제·좌표할 곳 {len(reprocess):,} (신규 + 주소 변경 + 짝의 새 번호)', '',
             '## 반영 중단 사유'] + ([f'- **{s}**' for s in stop] or ['- 없음'])
    (out_dir / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    return summary


def apply_review(d):
    """확인 목록에서 '이어받기'로 결정된 짝: 새 관리번호가 이전 관리번호의 영구번호를 쓴다"""
    reg = json.loads(REG.read_text(encoding='utf-8'))
    rv = pd.read_csv(d / 'review.csv', dtype=str, encoding='utf-8-sig').fillna('')
    n = 0
    # 어느 줄이 '이어받기'이고 옛·새 번호가 무엇인지 **읽기는 공통**(update_rules.inherit_pairs).
    # 화장실 옛 칸 이름(이전관리번호·새관리번호)도 그쪽이 읽어 준다.
    for 옛번호, 새번호 in inherit_pairs(rv.to_dict('records')):
        old_id = reg['by_mng'].get(옛번호)
        if not old_id:
            continue
        wrong = reg['by_mng'].get(새번호)
        reg['by_mng'][새번호] = old_id
        reg['inherit'][새번호] = {'from': 옛번호, 'date': date.today().isoformat(), 'dropped': wrong}
        reg['hidden'].pop(old_id, None)
        if wrong and wrong != old_id:                      # 대장이 먼저 새 번호를 줬다면 그 번호는 숨김(재사용 금지)
            reg['hidden'].setdefault(wrong, date.today().isoformat())
        n += 1
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
    print(f'이어받기 {n}건 반영')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prev'); ap.add_argument('--cur'); ap.add_argument('--out'); ap.add_argument('--apply-review')
    a = ap.parse_args()
    if a.apply_review:
        return apply_review(Path(a.apply_review))
    prev = Path(a.prev) if a.prev else max(SNAP.iterdir())
    cur = Path(a.cur) if a.cur else max((ROOT / 'data' / 'raw').glob('toilets_*.csv'))
    out = Path(a.out) if a.out else ROOT / 'data' / 'processed' / f'update_{date.today():%Y%m%d}'
    s = run(prev, cur, out)
    if s['반영중단']:
        sys.exit(1)


if __name__ == '__main__':
    main()
