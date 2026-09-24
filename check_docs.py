"""지식 문서 정합성 자동 검사 — 문서끼리, 문서와 코드가 서로 어긋나지 않았는지 확인한다.
실패(FAIL)가 하나라도 있으면 종료코드 1 → 고친 뒤 올린다. 경고(WARN)는 확인만.
실행: python check_docs.py
점검 항목 설명: docs/지식화-프로세스.md 4장

이 프로젝트(화장실)용: 버그 번호는 T#, 재사용 모듈은 ../착한식당/docs에 있으므로 여기서는 링크만 확인한다.
"""
import datetime, glob, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / 'docs'
CASE = DOCS / '사례지식.md'
BUGS = DOCS / '버그이력.md'
README = ROOT / 'README.md'
MODULE_MARK = '> **모듈 문서:**'
# 버그 분류 → 그 버그를 원칙으로 흡수해야 하는 모듈 (새 버그가 모듈에 반영됐는지 경고)
ABSORB = {}          # 재사용 모듈은 ../착한식당/docs에 있다 — 흡수 확인은 그쪽 check_docs.py가 한다
# 코드 이름처럼 보이지만 코드가 아닌 것(예시 문자열 등)
NOT_CODE = {'ROCOCO', 'KTX', 'CU', 'IC', 'JC', 'KT', 'SK', 'GS', 'LG', 'OIL'}
# 실행 중에 생기는 파일(분기 갱신 때 만들어짐) — 지금 없어도 문서에 적을 수 있다
GENERATED = {'changes.csv', 'review.csv', 'summary.json', 'report.md', 'quality.json', 'sample_check.csv', 'moved_coords.csv',
             'new_bad_coords.csv', 'unread_hours.csv', 'reprocess_ids.json', 'toilets_geo.csv', 'toilets_raw.csv', 'toilets_addr.csv',
             'check_sheet.csv', 'check_sheet.html', 'facility_sheet.csv', 'facility_sheet.html', 'golden.json', 'holidays.json',
             'gov_sites.json', 'classify.json', 'location_fixes.csv', 'coord_overrides.csv', 'address_overrides.csv', 'id_registry.json'}
FRESH_DAYS = 120                                       # 외부 플랫폼 레퍼런스 '마지막 확인' 기한

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
fails, warns = [], []
def FAIL(msg): fails.append(msg)
def WARN(msg): warns.append(msg)
def rel(p):
    q = Path(p).resolve()
    try:
        return q.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(q)                      # 프로젝트 밖(착한식당 모듈 문서 등)은 절대 경로로
def read(p): return Path(p).read_text(encoding='utf-8')

tracked = set(subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True).stdout.decode('utf-8').split('\0'))
md_files = [README] + sorted(DOCS.glob('*.md')) + sorted(p for p in ROOT.glob('*.md') if p != README)
modules = [p for p in sorted(DOCS.glob('*.md')) if MODULE_MARK in read(p)[:600]]

# 1. 링크: 가리키는 파일이 있고 저장소에 올라가 있는지
untracked = set()
for f in md_files:
    for m in re.finditer(r'\[[^\]]*\]\(([^)\s]+)\)', read(f)):
        href = m.group(1)
        if href.startswith(('http', 'mailto:')): continue
        path = href.split('#')[0]
        if not path: continue
        tgt = (f.parent / path).resolve()
        if not tgt.exists(): FAIL(f'없는 파일을 가리키는 링크: {rel(f)} → {href}')
        elif tgt.is_file() and not str(tgt.resolve()).startswith(str(ROOT.resolve())): pass   # 프로젝트 밖 모듈 문서는 링크 존재만 확인
        elif tgt.is_file() and rel(tgt) not in tracked: untracked.add(rel(tgt))

if untracked: WARN('링크된 파일이 아직 저장소에 없음(커밋 전이면 무시): ' + ', '.join(sorted(untracked)))

# 2. 버그 번호: 요약 표 ↔ 상세 절, 문서에 적힌 번호가 실제로 있는지
bug_text = read(BUGS)
summary_part = bug_text.split('## 부록')[0]
rows = {int(m.group(1)): m.group(2) for m in re.finditer(r'^\| T(\d+) \| [^|]+\| ([^|]+)\|', summary_part, re.M)}
details = {int(n) for n in re.findall(r'^### T(\d+)\. ', bug_text, re.M)}
for n in sorted(set(rows) - details): FAIL(f'버그 T{n}: 요약 표에는 있는데 상세 절(### T{n}.)이 없음')
for n in sorted(details - set(rows)): FAIL(f'버그 T{n}: 상세 절은 있는데 요약 표 행이 없음')

def bug_refs(text):
    refs = set()
    for m in re.finditer(r'T(\d{1,3})(?![0-9A-Za-z])(?:\s*~\s*T?(\d{1,3})(?![0-9A-Za-z]))?', text):
        a, b = int(m.group(1)), m.group(2)
        refs.update(range(a, int(b) + 1) if b and int(b) > a else [a])
    return refs
for f in md_files:
    for n in sorted(bug_refs(read(f)) - set(rows)):
        if n <= 0 or n > 999: continue
        FAIL(f'없는 버그 번호 T{n} 인용: {rel(f)}')

# 3. 모듈 형식과 양방향 연결
case_text, readme_text = read(CASE), read(README)
for m in modules:
    t = read(m)
    for sec in ('변경 이력', '갱신 규칙'):
        if not re.search(rf'^##+ .*{sec}', t, re.M): FAIL(f'모듈에 "{sec}" 절이 없음: {rel(m)}')
    if '(사례지식.md)' not in t: FAIL(f'모듈에서 사례지식으로 가는 링크가 없음: {rel(m)}')
    if f'({m.name})' not in case_text: FAIL(f'사례지식에서 모듈로 가는 링크가 없음: {m.name}')
    if f'(docs/{m.name})' not in readme_text: FAIL(f'README 문서 목록에 모듈이 없음: {m.name}')
for p in sorted(DOCS.glob('*.md')):
    if p.name != CASE.name and p.name not in case_text: WARN(f'사례지식(문서 지도)에 언급되지 않은 문서: {p.name}')

# 4. 장 참조: 문서에 적힌 "사례지식 N-N"이 실제 장 제목으로 있는지
case_secs = set(re.findall(r'^### (\d+-\d+)\. ', case_text, re.M))
for f in md_files:
    for m in re.finditer(r'사례지식(?:\]\(사례지식\.md\))?\s*((?:\d+-\d+)(?:\s*[·,]\s*\d+-\d+)*)', read(f)):
        for sec in re.findall(r'\d+-\d+', m.group(1)):
            if sec not in case_secs: FAIL(f'사례지식에 없는 장 "{sec}" 참조: {rel(f)}')

# 5. 코드 참조: 모듈에 적힌 코드 이름·파일 이름이 실제로 있는지
code = ''.join(read(p) for p in list(ROOT.glob('app/*.js')) + list(ROOT.glob('functions/**/*.js')) + list(ROOT.glob('*.py'))
               if p.name != 'check_docs.py')
for m in modules:
    for tok in set(re.findall(r'`([^`\s]+)`', read(m))):
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{3,}', tok):
            if tok not in NOT_CODE and not re.search(rf'\b{re.escape(tok)}\b', code):
                FAIL(f'코드에 없는 이름 "{tok}" (코드가 바뀌었으면 문서도 고칠 것): {rel(m)}')
        elif re.fullmatch(r'[\w./-]+\.(py|js|json|md|toml|css|html)', tok) and '://' not in tok:
            bases = (ROOT, DOCS, ROOT / 'data', ROOT / 'data' / 'processed', ROOT / 'data' / 'raw')
            if Path(tok).name not in GENERATED and not any((base / tok).exists() for base in bases):
                FAIL(f'없는 파일 이름 "{tok}": {rel(m)}')

# 6. 흡수 확인(경고): 분류별 버그가 담당 모듈에 인용됐는지
for cat, mod in ABSORB.items():
    mp = DOCS / mod
    if not mp.exists(): continue
    cited = bug_refs(read(mp))
    miss = [n for n, c in rows.items() if cat in c and n not in cited]
    if miss: WARN(f'{mod}에 아직 반영(인용)되지 않은 `{cat}` 버그: ' + ', '.join(f'#{n}' for n in miss))

# 7. 신선도(경고): 외부 플랫폼 레퍼런스 마지막 확인일
ref = DOCS / '외부플랫폼-레퍼런스.md'
if ref.exists():
    m = re.search(r'마지막 확인: (\d{4}-\d{2}-\d{2})', read(ref))
    if not m: FAIL('외부플랫폼-레퍼런스.md에 "마지막 확인: YYYY-MM-DD" 줄이 없음')
    else:
        age = (datetime.date.today() - datetime.date.fromisoformat(m.group(1))).days
        if age > FRESH_DAYS: WARN(f'외부 플랫폼 레퍼런스 마지막 확인이 {age}일 전 → 공식 문서와 대조 필요')

print(f'문서 {len(md_files)}개 · 모듈 {len(modules)}개({", ".join(m.name for m in modules)}) · 버그 {len(rows)}건 검사')
for w in warns: print('  WARN', w)
for f in fails: print('  FAIL', f)
if fails:
    print(f'\n❌ 실패 {len(fails)}건 — 고친 뒤 다시 실행')
    sys.exit(1)
print(f'\n✅ 통과' + (f' (경고 {len(warns)}건)' if warns else ''))
