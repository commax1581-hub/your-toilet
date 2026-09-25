"""영구 번호 대장 + 기준본(스냅숏) — 공유 링크·즐겨찾기·수기 보정이 묶이는 우리 번호(WC000001)를 준다.
- 같은 화장실 판별: 관리번호(18자리, 원본 고유). 관리번호가 바뀐 경우(삭제+신규 짝)는 diff_update.py 확인 목록에서 이어받기.
- 한 번 준 번호는 영구, 새 화장실만 새 번호, 삭제된 번호는 재사용 금지(숨김으로 보관).
- **원천 관리번호가 영원하다는 보장은 없다.** 같은 관리번호에 다른 시설이 들어오면(번호 재사용·오기재)
  옛 영구번호를 **폐기(retired)**하고 새 번호를 준다 — 옛 번호를 새 시설에 물려주지 않는다(사례지식 6-33).
- 원본의 줄 순서는 쓰지 않는다 — 착한가격 #29(분기마다 순번이 밀리는 치명 오류) 재발 방지.
대장: data/id_registry.json (공개 저장소에 올린다 — 잃으면 링크가 깨진다)
기준본: data/snapshots/<날짜>/ toilets_raw.csv · toilets_geo.csv (영구번호 포함)
실행: python build_registry.py [--date YYYYMMDD]   (날짜 생략 시 가장 최근 원본 날짜)
"""
import argparse, json, shutil, sys
from datetime import date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
REG = ROOT / 'data' / 'id_registry.json'
SNAP = ROOT / 'data' / 'snapshots'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def load():
    if REG.exists():
        return json.loads(REG.read_text(encoding='utf-8'))
    return {'next': 1, 'by_mng': {}, 'inherit': {}, 'hidden': {}, 'retired': {}}


def save(reg):
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')


def assign(reg, mngs, today):
    """관리번호 목록 → 영구번호. 새 관리번호만 새 번호(관리번호 순으로 정렬해 매번 같은 결과)"""
    new = 0
    for m in sorted(set(mngs) - set(reg['by_mng'])):
        reg['by_mng'][m] = f"WC{reg['next']:06d}"
        reg['next'] += 1
        new += 1
    present = set(mngs)
    gone = {m: i for m, i in reg['by_mng'].items() if m not in present}
    for m, i in gone.items():                       # 사라진 번호: 삭제하지 않고 숨김 목록에(처음 사라진 날)
        reg['hidden'].setdefault(i, today)
    for m in present:
        reg['hidden'].pop(reg['by_mng'][m], None)   # 다시 나타나면 숨김 해제
    return new, len(gone)


def retire(reg, mng, info, today, reason='번호 재사용'):
    """같은 관리번호에 **다른 시설**이 들어왔다 — 옛 영구번호를 폐기하고 새 번호를 준다.

    폐기한 번호는 **누구에게도 주지 않는다.** 그 번호로 들어온 공유 링크·저장한 곳은
    "이 화장실은 더 이상 이 자리에 없습니다"로 안내해야 사용자가 헛걸음하지 않는다.
    되돌릴 수 있게 옛 이름·주소와 사유·날짜를 함께 남긴다.
    """
    old = reg['by_mng'].get(mng)
    ret = reg.setdefault('retired', {})
    if not old or old in ret:
        return None
    # 같은 날 같은 관리번호를 두 번 폐기하지 않는다 — 두 번 부르면 **방금 준 새 번호까지** 버리게 된다.
    # (해가 바뀌어 같은 번호가 또 재사용되는 일은 있을 수 있으므로 날짜까지 함께 본다)
    if any(v['관리번호'] == mng and v['폐기일'] == today for v in ret.values()):
        return None
    new = f"WC{reg['next']:06d}"
    reg['next'] += 1
    reg['by_mng'][mng] = new
    reg['retired'][old] = {'관리번호': mng, '폐기일': today, '사유': reason, '새번호': new,
                           '옛이름': info.get('옛이름', ''), '옛주소': info.get('옛주소', ''),
                           '새이름': info.get('새이름', ''), '새주소': info.get('새주소', '')}
    reg['hidden'].pop(old, None)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    a = ap.parse_args()
    raw_path = ROOT / 'data' / 'raw' / f'toilets_{a.date}.csv' if a.date else max((ROOT / 'data' / 'raw').glob('toilets_*.csv'))
    stamp = raw_path.stem.split('_')[-1]
    raw = pd.read_csv(raw_path, dtype=str, encoding='utf-8-sig').fillna('')
    if raw['관리번호'].duplicated().any():
        sys.exit(f'관리번호 중복 {raw["관리번호"].duplicated().sum()}건 — 고유키 가정이 깨짐, 중단')
    reg = load()
    before = len(reg['by_mng'])
    new, gone = assign(reg, raw['관리번호'], date.today().isoformat())
    save(reg)
    print(f'대장: 기존 {before:,} → {len(reg["by_mng"]):,} (새 번호 {new:,}, 이번에 없는 번호 {gone:,}), 다음 번호 WC{reg["next"]:06d}')

    d = SNAP / stamp
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, d / 'toilets_raw.csv')
    geo = ROOT / 'data' / 'processed' / 'toilets_geo.csv'
    if geo.exists():
        g = pd.read_csv(geo, dtype=str, encoding='utf-8-sig').fillna('')
        g.insert(0, '영구번호', g['관리번호'].map(reg['by_mng']))
        if g['영구번호'].eq('').any() or g['영구번호'].isna().any():
            sys.exit('좌표 결과에 대장에 없는 관리번호가 있다 — 원본과 좌표 결과의 날짜가 다른지 확인')
        g.to_csv(d / 'toilets_geo.csv', index=False, encoding='utf-8-sig')
    print(f'기준본 저장: data/snapshots/{stamp}/')


if __name__ == '__main__':
    main()
