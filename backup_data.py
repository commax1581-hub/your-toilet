"""원본·캐시·기준본 비공개 백업 + 보관 정책 — 잃으면 되돌릴 수 없는 것부터 지킨다.

**왜 필요한가**
- 기준본·번호 대장을 잃으면 **영구번호가 깨져 공유 링크가 전부 무효**가 된다(되돌릴 수 없음).
- 캐시를 잃으면 주소·지도 API를 **13만 회 다시** 부른다(되돌릴 수는 있지만 비싸다).

**세 갈래로 나눠 담는다**(2026-09-25 정리) — 전부 매주 올리면 저장소가 1년에 1GB씩 불어난다.
| 갈래 | 무엇 | 주기 |
|---|---|---|
| 핵심 | 번호 대장·수기 보정·사전·골든 표본·역 좌표표·기준본(snapshots) | **매번** |
| 캐시 | 카카오·주소·네이버 캐시 → **`.gz`로 압축** | **월 1회**(`--cache`로 강제) |
| 원본 | `toilets_*.json`(API 응답 원본) → **`.gz`** · 역 원본 CSV | 매번(작다) |

**담지 않는 것** — 같은 내용이 이미 있는 것들. `data/raw/toilets_*.csv`는 기준본의 `toilets_raw.csv`와 **바이트까지 같고**,
제안 폴더(`update_*`)의 `toilets_raw/geo.csv`도 같은 내용이다. 사람이 결정한 작은 CSV(review·swapped…)만 담는다.

**GitHub 한도**: 파일 하나 **100MB 차단** · 저장소 1GB 권장(5GB 강력 권장) · **git은 과거를 지우지 않아 누적된다.**
그래서 큰 캐시는 압축해서 월 1회만 넣는다.

실행: python backup_data.py [--no-push] [--prune] [--cache]
백업 폴더: 프로젝트 옆 '화장실-data-backup' (비공개 GitHub 저장소와 연결)
"""
import glob, gzip, re, shutil, subprocess, sys, urllib.error, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DEST = ROOT.parent / '화장실-data-backup'
SNAP = ROOT / 'data' / 'snapshots'

# 매번 — 잃으면 되돌릴 수 없는 것(전부 합쳐도 수십 MB)
CORE = ['data/id_registry.json', 'data/coord_overrides.csv', 'data/location_fixes.csv',
        'data/address_overrides.csv', 'data/classify.json', 'data/gov_sites.json',
        'data/golden.json', 'data/rail_stations.csv', 'data/raw/rail', '정부자료']
# 기준본은 **압축해서** 담는다 — 한 주치가 49MB(원본 20 + 정제 29)라 그대로 쌓으면 1년에 2.5GB다.
# 백업은 되살리기용이라 압축해도 쓰는 데 지장이 없다(프로젝트 폴더의 기준본은 그대로 둔다).
GZ_SNAP = 'data/snapshots'
# 압축해서 담을 것 — 크고, 내용이 텍스트라 10% 안팎으로 줄어든다
GZ_RAW = 'data/raw/toilets_*.json'
GZ_CACHE = ['data/processed/kakao_cache.json', 'data/processed/address_cache.json',
            'data/processed/naver_cache.json', 'data/processed/kakao_station_cache.json',
            'data/processed/gov_pdf_text.json']
# 제안 폴더에서 **사람이 결정한 작은 것만** (큰 두 파일은 기준본과 같은 내용이라 뺀다)
PROPOSE_KEEP = {'report.md', 'summary.json', 'quality.json', 'changes.csv', 'review.csv',
                'swapped_ids.csv', 'moved_coords.csv', 'new_bad_coords.csv', 'unread_hours.csv', 'sample_check.csv'}
KEY_FILES = ['.env']
KEEP_WEEKS = 8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def prune_snapshots():
    """최근 8주는 모두 / 그 전 1년은 달마다 1개 / 1년 넘으면 해마다 1개"""
    if not SNAP.exists():
        return []
    days = sorted(d for d in SNAP.iterdir() if d.is_dir() and re.fullmatch(r'\d{8}', d.name))
    today = date.today()
    keep = set()
    by_month, by_year = defaultdict(list), defaultdict(list)
    for d in days:
        dt = date(int(d.name[:4]), int(d.name[4:6]), int(d.name[6:]))
        if today - dt <= timedelta(weeks=KEEP_WEEKS):
            keep.add(d.name)
        elif today - dt <= timedelta(days=365):
            by_month[d.name[:6]].append(d.name)
        else:
            by_year[d.name[:4]].append(d.name)
    for group in (by_month, by_year):
        for v in group.values():
            keep.add(max(v))                       # 그 달·그 해의 마지막 기준본만
    drop = [d for d in days if d.name not in keep]
    for d in drop:
        shutil.rmtree(d)
    return [d.name for d in drop]


def key_values():
    """API 키 문자열 — 백업에 섞여 들어가면 비공개 저장소라도 위험하다"""
    vals = []
    for f in KEY_FILES:
        p = ROOT / f
        if p.exists():
            for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
                v = line.split('=', 1)[-1].strip().strip('"\'')
                if len(v) >= 16:
                    vals.append(v.encode())
    return vals


def gather():
    """(그대로 담을 파일, 압축해 담을 파일) — 담지 않는 것은 위 설명 참고"""
    plain, gz = [], []
    for s in CORE:
        p = ROOT / s
        if not p.exists():
            continue
        plain += [x for x in p.rglob('*') if x.is_file()] if p.is_dir() else [p]
    for d in sorted(glob.glob(str(ROOT / 'data' / 'processed' / 'update_*'))):
        plain += [x for x in Path(d).iterdir() if x.is_file() and x.name in PROPOSE_KEEP]
    gz += [Path(p) for p in sorted(glob.glob(str(ROOT / GZ_RAW)))]
    snap = ROOT / GZ_SNAP
    if snap.exists():
        gz += sorted(x for x in snap.rglob('*') if x.is_file())
    return plain, gz


def cache_due(force):
    """캐시는 **월 1회**만 — 매주 담으면 압축본 7MB가 통째로 새로 쌓인다(git은 과거를 못 지운다)"""
    mark = DEST / '.cache_month'
    now = f'{date.today():%Y%m}'
    if force:
        return True, mark, now
    return (not mark.exists() or mark.read_text(encoding='utf-8').strip() != now), mark, now


def put_gz(src, dst):
    """압축해서 담는다. 내용이 그대로면 건드리지 않는다(쓸데없는 커밋 방지)"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(src.read_bytes(), 6)
    if dst.exists() and dst.stat().st_size == len(data):
        return False
    dst.write_bytes(data)
    return True


def main():
    force_cache = '--cache' in sys.argv
    if '--prune' in sys.argv:
        dropped = prune_snapshots()
        print(f'기준본 정리: {len(dropped)}개 삭제' + (f' ({", ".join(dropped[:6])}…)' if dropped else ' (지울 것 없음)'))

    plain, gz = gather()
    due, mark, month = cache_due(force_cache)
    if due:
        gz += [ROOT / c for c in GZ_CACHE if (ROOT / c).exists()]

    keys = key_values()
    leak = [f for f in plain + gz if any(k in f.read_bytes() for k in keys)]
    if leak:
        sys.exit('중단: API 키 문자열이 들어간 파일이 있음 → ' + ', '.join(str(f.relative_to(ROOT)) for f in leak))

    if not (DEST / '.git').exists():
        DEST.mkdir(exist_ok=True)
        subprocess.run(['git', 'init', '-b', 'main'], cwd=DEST, check=True)
    (DEST / 'README.md').write_text(
        '# 가장 가까운 화장실 — 비공개 백업\n\n'
        '공개 저장소에서 제외한 **원본·캐시·기준본**. 이 저장소는 반드시 **비공개**로 둔다. API 키는 넣지 않는다.\n\n'
        '## 무엇이 들어 있나\n'
        '- **핵심(매번)** — 번호 대장(`id_registry.json`)·수기 보정·사전·골든 표본·역 좌표표·기준본(`data/snapshots/`)\n'
        '  - 잃으면 **영구번호가 깨져 공유 링크가 전부 무효**가 된다. 되돌릴 수 없는 쪽.\n'
        '- **캐시(월 1회, `.gz`)** — 주소·카카오·네이버 캐시. 잃으면 API를 13만 회 다시 부른다.\n'
        '- **원본(`.gz`)** — 수집한 API 응답 원본(`toilets_*.json`)과 역 원본 CSV.\n\n'
        '## 없는 것\n'
        '`data/raw/toilets_*.csv`와 제안 폴더의 큰 CSV는 **기준본과 같은 내용**이라 담지 않는다.\n\n'
        '## 되살리기\n'
        '```\n'
        '# 1) 이 폴더의 data/ 를 프로젝트에 복사\n'
        '# 2) 압축 풀기 (예)\n'
        'python -c "import gzip,pathlib;p=pathlib.Path(\'data/processed/kakao_cache.json.gz\');'
        'pathlib.Path(str(p)[:-3]).write_bytes(gzip.decompress(p.read_bytes()))"\n'
        '```\n', encoding='utf-8')

    copied = 0
    for f in plain:
        dst = DEST / f.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != f.stat().st_size or dst.stat().st_mtime < f.stat().st_mtime:
            shutil.copy2(f, dst)
            copied += 1
    zipped = 0
    for f in gz:
        if put_gz(f, DEST / f.relative_to(ROOT).with_suffix(f.suffix + '.gz')):
            zipped += 1
    if due:
        mark.write_text(month, encoding='utf-8')

    # **담을 목록에 없는 파일은 지운다.** 예전 판이 담던 중간 산출물(정제 CSV 79MB 등)이 남아
    # 저장소를 계속 불렸다. 목록을 바꾸면 백업도 따라오게 한다.
    # 캐시는 **이번에 담지 않아도 지우면 안 된다**(월 1회만 새로 담는다).
    # 처음엔 이 줄이 없어서, 캐시를 건너뛴 회차에 백업이 캐시 압축본을 통째로 지웠다 — API 13만 회를 날릴 뻔했다.
    want = ({f.relative_to(ROOT) for f in plain}
            | {f.relative_to(ROOT).with_suffix(f.suffix + '.gz') for f in gz}
            | {Path(c).with_suffix('.json.gz') for c in GZ_CACHE})
    keep_names = {'README.md', '.cache_month'}
    stale = [x for x in DEST.rglob('*')
             if x.is_file() and '.git' not in x.parts and x.name not in keep_names
             and x.relative_to(DEST) not in want]
    for x in stale:
        x.unlink()
    for d in sorted((p for p in DEST.rglob('*') if p.is_dir() and '.git' not in p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()

    tot = sum(f.stat().st_size for f in DEST.rglob('*') if f.is_file() and '.git' not in f.parts)
    big = [f for f in DEST.rglob('*') if f.is_file() and '.git' not in f.parts and f.stat().st_size > 95 * 1024 * 1024]
    subprocess.run(['git', 'add', '-A'], cwd=DEST, check=True)
    changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=DEST).returncode != 0
    if changed:
        subprocess.run(['git', 'commit', '-q', '-m', f'백업 {datetime.now():%Y-%m-%d %H:%M}'], cwd=DEST, check=True)
    print(f'담은 파일 {len(plain) + len(gz):,}개 · 복사 {copied:,} · 압축 {zipped:,} · 지운 옛 파일 {len(stale):,}'
          f"{' · 캐시 포함(이번 달 첫 백업)' if due else ' · 캐시 건너뜀(이번 달 이미 담음)'}")
    print(f'백업 크기 {tot / 1024 / 1024:.0f}MB · 키 검사 통과 · ' + ('새 커밋' if changed else '바뀐 것 없음'))
    if big:
        print('⚠ 95MB 넘는 파일 — GitHub는 100MB에서 push를 막는다: '
              + ', '.join(f'{f.name} {f.stat().st_size / 1024 / 1024:.0f}MB' for f in big))

    if '--no-push' in sys.argv:
        return
    remote = subprocess.run(['git', 'remote'], cwd=DEST, capture_output=True, text=True).stdout.strip()
    if not remote:
        print(f'\n원격 저장소가 없습니다. GitHub에 **비공개** 저장소를 만든 뒤:\n'
              f'  git -C "{DEST}" remote add origin <주소>\n'
              f'  git -C "{DEST}" push -u origin main')
        return
    url = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=DEST, capture_output=True, text=True).stdout.strip()
    m = re.search(r'github\.com[/:]([^/]+/[^/.]+)', url)
    if m:                                           # 로그인 없이 보이면 공개 저장소 → 올리지 않는다
        try:
            urllib.request.urlopen(f'https://api.github.com/repos/{m.group(1)}', timeout=10)
            sys.exit(f'중단: {m.group(1)} 은 공개 저장소로 보입니다. 비공개로 바꾼 뒤 다시 실행하세요.')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    subprocess.run(['git', 'push', '-u', 'origin', 'main'], cwd=DEST, check=True)
    print('push 완료')


if __name__ == '__main__':
    main()
