"""개방시간 판정 맞대보기 — 파이썬(hours.py)과 앱(app/hours.js)이 같은 답을 내는지.
앱 데이터에 실제로 들어 있는 모든 개방시간 구조를 모아, 여러 시각(평일·주말·공휴일·자정 넘김)에 대해
두 구현의 답(열림/곧 닫힘/닫힘/확인 필요 + 닫는 시각·다음 여는 시각)을 비교한다.
  python test_hours_js.py          (node 필요)
설계 근거: 같은 규칙을 두 언어로 쓰면 반드시 어긋난다 — 착한가격 버그이력 #24(자정 넘김), 화장실 T13(요일 휴무)
"""
import glob, json, subprocess, sys, tempfile
from datetime import datetime
from pathlib import Path
from hours import state

ROOT = Path(__file__).parent
JS = ROOT / 'app' / 'hours.js'
WHEN = ['2026-09-24 14:00', '2026-09-24 23:40', '2026-09-25 09:00', '2026-09-26 08:15',
        '2026-09-26 23:30', '2026-09-27 03:00', '2026-09-28 12:30', '2026-09-28 05:45']   # 목(공휴일)·금·토·일·월
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def unpack(h):
    """앱이 쓰는 짧은 구조 → hours.state 가 받는 구조"""
    if h['k'] == 'a':
        return {'kind': 'always', 'rules': [], 'holiday': None, 'breaks': []}
    if h['k'] == 'u':
        return {'kind': 'unknown', 'rules': [], 'holiday': None, 'breaks': []}
    hm = lambda t: f'{t[:2]}:{t[2:]}'
    return {'kind': 'hours',
            'rules': [{'days': [d for d in range(7) if mask >> d & 1], 'open': hm(o), 'close': hm(c)} for mask, o, c in h['r']],
            'holiday': [{'open': hm(o), 'close': hm(c)} for o, c in h['hd']] if 'hd' in h else None,
            'breaks': [{'from': hm(f), 'to': hm(t)} for f, t in h.get('br', [])]}


def main():
    cases, seen = [], set()
    for f in glob.glob(str(ROOT / 'app' / 'data' / 't' / '*.json')):
        for r in json.loads(Path(f).read_text(encoding='utf-8')):
            k = json.dumps(r['h'], sort_keys=True, ensure_ascii=False)
            if k not in seen:
                seen.add(k)
                cases.append(r['h'])
    holidays = {d for days in json.loads((ROOT / 'app' / 'data' / 'holidays.json').read_text(encoding='utf-8')).values() for d in days}
    print(f'개방시간 구조 {len(cases):,}가지 × 시각 {len(WHEN)}개 = {len(cases) * len(WHEN):,}건 비교')

    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / 'in.json'
        inp.write_text(json.dumps({'cases': cases, 'when': WHEN, 'holidays': sorted(holidays)}), encoding='utf-8')
        js = f'''
const fs = require('fs');
eval(fs.readFileSync({json.dumps(str(JS))}, 'utf8'));
const inp = JSON.parse(fs.readFileSync({json.dumps(str(inp))}, 'utf8'));
const hol = new Set(inp.holidays);
const p = (d) => d ? `${{d.getFullYear()}}-${{String(d.getMonth()+1).padStart(2,'0')}}-${{String(d.getDate()).padStart(2,'0')}} ${{String(d.getHours()).padStart(2,'0')}}:${{String(d.getMinutes()).padStart(2,'0')}}` : '';
const out = inp.cases.map((h) => inp.when.map((w) => {{
  const [dt, tm] = w.split(' '), [y, mo, d] = dt.split('-').map(Number), [hh, mi] = tm.split(':').map(Number);
  const s = Hours.state(h, new Date(y, mo - 1, d, hh, mi), hol);
  return [s.k, p(s.until || s.next || null)];
}}));
process.stdout.write(JSON.stringify(out));
'''
        run = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if run.returncode:
            sys.exit('node 실행 실패:\n' + run.stderr[:800])
        got = json.loads(run.stdout)

    bad = 0
    for h, rows in zip(cases, got):
        for w, (jk, jt) in zip(WHEN, rows):
            now = datetime.strptime(w, '%Y-%m-%d %H:%M')
            pk, pt = state(unpack(h), now, {d.date() for d in map(lambda x: datetime.strptime(x, '%Y-%m-%d'), holidays)})
            pts = pt.strftime('%Y-%m-%d %H:%M') if pt else ''
            if (pk, pts) != (jk, jt):
                bad += 1
                if bad <= 10:
                    print(f'다름 {w} {json.dumps(h, ensure_ascii=False)}\n  파이썬 {pk} {pts} / 앱 {jk} {jt}')
    print(f'{"✅ 두 구현이 같습니다" if not bad else f"❌ 다른 답 {bad:,}건"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
