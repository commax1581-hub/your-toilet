"""원본·캐시·기준본 비공개 백업 + 기준본 보관 정책 — 착한가격 `backup_data.py`를 이 프로젝트에 맞게 가져옴.
왜 필요한가: 캐시 97MB(주소 5.1만 · 카카오 7.9만 · 네이버 3천 건)를 잃으면 API를 13만 회 다시 부른다.
             기준본·대장을 잃으면 영구번호가 깨져 공유 링크가 전부 무효가 된다(되돌릴 수 없음).
대상: data/raw, data/processed(캐시·보고서), data/snapshots, data/id_registry.json, data/coord_overrides.csv,
      data/location_fixes.csv, data/address_overrides.csv, data/classify.json, data/gov_sites.json, 정부자료/
제외: 키 파일(.env) — 복사 전에 키 문자열이 들어간 파일이 있으면 중단
보관 정책(--prune): 기준본은 최근 8주는 모두, 그 이전은 월 1개(각 달 마지막), 1년 넘으면 연 1개만 남긴다.
  (주 1회 갱신이면 1년에 약 2.5GB가 쌓인다 — 백업 저장소도 같이 커진다)
실행: python backup_data.py [--no-push] [--prune]
백업 폴더: 프로젝트 옆 '화장실-data-backup' (비공개 GitHub 저장소와 연결)
"""
import glob, re, shutil, subprocess, sys, urllib.error, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DEST = ROOT.parent / '화장실-data-backup'
SNAP = ROOT / 'data' / 'snapshots'
SOURCES = ['data/raw', 'data/processed', 'data/snapshots', 'data/id_registry.json', 'data/coord_overrides.csv',
           'data/location_fixes.csv', 'data/address_overrides.csv', 'data/classify.json', 'data/gov_sites.json', '정부자료']
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
    vals = []
    for f in KEY_FILES:
        p = ROOT / f
        if p.exists():
            for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
                v = line.split('=', 1)[-1].strip().strip('"\'')
                if len(v) >= 16:
                    vals.append(v.encode())
    return vals


def main():
    if '--prune' in sys.argv:
        dropped = prune_snapshots()
        print(f'기준본 정리: {len(dropped)}개 삭제' + (f' ({", ".join(dropped[:6])}…)' if dropped else ' (지울 것 없음)'))

    files = []
    for s in SOURCES:
        for p in glob.glob(str(ROOT / s)):
            p = Path(p)
            files += [x for x in p.rglob('*') if x.is_file()] if p.is_dir() else [p]
    keys = key_values()
    leak = [f for f in files if any(k in f.read_bytes() for k in keys)]
    if leak:
        sys.exit('중단: API 키 문자열이 들어간 파일이 있음 → ' + ', '.join(str(f.relative_to(ROOT)) for f in leak))

    if not (DEST / '.git').exists():
        DEST.mkdir(exist_ok=True)
        subprocess.run(['git', 'init', '-b', 'main'], cwd=DEST, check=True)
        (DEST / 'README.md').write_text(
            '# 가장 가까운 화장실 — 원본·캐시·기준본 비공개 백업\n\n'
            '공개 저장소에서 제외한 원본·캐시·기준본. **비공개 유지.** API 키는 넣지 않는다.\n'
            '복원: 이 폴더의 data/·정부자료/를 프로젝트 폴더에 그대로 복사하면 캐시·기준본·대장이 살아난다.\n', encoding='utf-8')

    copied = 0
    for f in files:
        dst = DEST / f.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != f.stat().st_size or dst.stat().st_mtime < f.stat().st_mtime:
            shutil.copy2(f, dst)
            copied += 1
    size = sum(f.stat().st_size for f in files) / 1024 / 1024
    subprocess.run(['git', 'add', '-A'], cwd=DEST, check=True)
    changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=DEST).returncode != 0
    if changed:
        subprocess.run(['git', 'commit', '-q', '-m', f'백업 {datetime.now():%Y-%m-%d %H:%M}'], cwd=DEST, check=True)
    print(f'파일 {len(files):,}개({size:.0f}MB) 중 {copied:,}개 복사, 키 검사 통과, ' + ('새 커밋' if changed else '바뀐 것 없음'))

    if '--no-push' in sys.argv:
        return
    remote = subprocess.run(['git', 'remote'], cwd=DEST, capture_output=True, text=True).stdout.strip()
    if not remote:
        print(f'원격 저장소가 없음 → GitHub에 비공개 저장소를 만든 뒤: git -C "{DEST}" remote add origin <주소>')
        return
    url = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=DEST, capture_output=True, text=True).stdout.strip()
    m = re.search(r'github\.com[/:]([^/]+/[^/.]+)', url)
    if m:                                           # 로그인 없이 보이면 공개 저장소 → 올리지 않는다
        try:
            urllib.request.urlopen(f'https://api.github.com/repos/{m.group(1)}', timeout=10)
            sys.exit('중단: 백업 저장소가 공개(Public) 상태 → Private으로 바꾼 뒤 다시 실행')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f'경고: 공개 여부 확인 실패(HTTP {e.code}) — 계속 진행')
    subprocess.run(['git', 'push', '-q', '-u', 'origin', 'main'], cwd=DEST, check=True)
    print('비공개 저장소로 올림')


if __name__ == '__main__':
    main()
