"""갱신 변경 분류 시험 — 이번 기준본으로 '가짜 다음 판'을 만들어 분류·이어받기·번호 유지·이상 감지를 확인한다.
실제 대장은 건드리지 않는다(임시 복사본 사용). 실행: python test_diff_update.py
"""
import json, shutil, sys, tempfile
from pathlib import Path
import pandas as pd
import build_registry as br
import diff_update as du

ROOT = Path(__file__).parent
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
ok = []


def check(name, cond):
    ok.append(cond)
    print(('통과 ' if cond else '실패 ') + name)


def main():
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    prev = pd.read_csv(snap / 'toilets_raw.csv', dtype=str, encoding='utf-8-sig').fillna('')
    cur = prev.copy()
    m = list(prev['관리번호'])
    cur.loc[cur['관리번호'] == m[0], '화장실명'] = '이름바뀐화장실'
    cur.loc[cur['관리번호'] == m[1], '개방시간상세'] = '06:00~23:00'
    cur.loc[cur['관리번호'] == m[2], '여성용-대변기수'] = '99'
    cur.loc[cur['관리번호'] == m[3], '소재지도로명주소'] = '서울특별시 중구 세종대로 110'
    cur.loc[cur['관리번호'] == m[4], '소재지도로명주소'] = prev.loc[prev['관리번호'] == m[4], '소재지도로명주소'].iloc[0] + ' (표기만)'
    cur = cur[~cur['관리번호'].isin([m[10], m[11]])]                       # 삭제 2
    re_reg = prev[prev['관리번호'] == m[20]].copy(); re_reg['관리번호'] = '209999999999999001'
    cur = cur[cur['관리번호'] != m[20]]                                     # 삭제+신규 짝(재등록)
    brand = prev[prev['관리번호'] == m[30]].copy(); brand['관리번호'] = '209999999999999002'; brand['화장실명'] = '완전새화장실'
    cur = pd.concat([cur, re_reg, brand]).sample(frac=1, random_state=1)   # 순서 섞기

    tmp = Path(tempfile.mkdtemp())
    cur_file = tmp / 'toilets_29990101.csv'
    cur.to_csv(cur_file, index=False, encoding='utf-8-sig')
    s = du.run(snap, cur_file, tmp / 'out')
    ch = pd.read_csv(tmp / 'out' / 'changes.csv', dtype=str).fillna('')
    get = lambda mm: ch.loc[ch['관리번호'] == mm]
    check('이름 변경', '이름' in get(m[0])['항목'].iloc[0])
    check('개방시간 변경', '개방시간' in get(m[1])['항목'].iloc[0])
    check('변기 수 변경', '변기 수' in get(m[2])['항목'].iloc[0])
    check('주소 변경 → 다시 처리', '주소' in get(m[3])['항목'].iloc[0] and m[3] in json.loads((ROOT / 'data/processed/reprocess_ids.json').read_text()))
    check('괄호 안 표기만 바뀐 주소는 변경 아님', get(m[4]).empty)
    check('삭제 2', set(ch.loc[ch['분류'] == '삭제', '관리번호']) == {m[10], m[11]})
    check('삭제+신규 짝 1(재등록)', s['확인목록'] == 1 and get(m[20])['분류'].iloc[0] == '삭제+신규 짝')
    check('신규 1(짝 아닌 것)', list(ch.loc[ch['분류'] == '신규', '관리번호']) == ['209999999999999002'])
    check('반영 중단 없음', not s['반영중단'])

    # 이어받기 + 대장 번호 유지(임시 대장)
    reg_tmp = tmp / 'reg.json'
    shutil.copy2(du.REG, reg_tmp)
    du.REG = br.REG = reg_tmp
    before = json.loads(reg_tmp.read_text(encoding='utf-8'))
    du.apply_review(tmp / 'out')
    reg = br.load()
    br.assign(reg, cur['관리번호'], '2999-01-01')
    check('재등록 곳은 옛 영구번호 이어받음', reg['by_mng']['209999999999999001'] == before['by_mng'][m[20]])
    check('완전 신규만 새 번호', reg['by_mng']['209999999999999002'] == f"WC{before['next']:06d}" and reg['next'] == before['next'] + 1)
    check('순서를 섞어도 기존 번호 그대로', all(reg['by_mng'][x] == before['by_mng'][x] for x in cur['관리번호'] if x in before['by_mng']))
    check('삭제된 번호는 숨김(보관)', before['by_mng'][m[10]] in reg['hidden'] and m[10] in reg['by_mng'])
    check('이어받은 번호는 숨김 아님', before['by_mng'][m[20]] not in reg['hidden'])

    # 이상 감지: 15% 삭제
    small = prev.sample(frac=0.85, random_state=2)
    small.to_csv(tmp / 'toilets_29990102.csv', index=False, encoding='utf-8-sig')
    s2 = du.run(snap, tmp / 'toilets_29990102.csv', tmp / 'out2')
    check('15% 급감 → 반영 중단', any('감소' in x for x in s2['반영중단']))
    print(f'\n{sum(ok)}/{len(ok)} 통과')
    shutil.rmtree(tmp, ignore_errors=True)
    (ROOT / 'data/processed/reprocess_ids.json').unlink(missing_ok=True)
    sys.exit(0 if all(ok) else 1)


if __name__ == '__main__':
    main()
