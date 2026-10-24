"""구글 드라이브 백업 — **다시 만들 수 없는 것만**(두 번째 바구니).

`backup_data.py`는 GitHub 비공개 저장소에 담는데, **앱 저장소와 같은 계정**이라 계정을 잃으면 함께 사라진다.
그래서 **다른 바구니**를 하나 둔다. 장학금 프로젝트와 같은 결 — 날짜 폴더 4벌 · `핵심`/`원천`/`저장소` · `복구안내.md`(자동 갱신).

| 담는 것 | 왜 |
|---|---|
| 영구번호 대장 | 잃으면 **공유 링크가 전부 무효** — 되돌릴 방법이 없다 |
| 그날의 기준본 | 원천 API는 **현재분만** 준다 — 지난 기준본은 다시 못 받는다 |
| 사람이 고친 위치·사전·골든 표본·역 좌표표·코드표·구청표 | 사람이 판단해 만든 것 |
| git 묶음(`--all`) | GitHub 계정을 잃어도 `git clone 화장실.bundle`로 되살린다 |

**담지 않는 것**: 캐시(비쌀 뿐 다시 만들 수 있다 — GitHub 비공개 저장소에 있다) · API 키 · 커밋 안 된 작업.
담기 전에 **키 문자열 검사**를 걸고, 키를 하나도 못 찾으면 **검사가 헛도는 것으로 보고 중단**한다(T35).

실행: python backup_drive.py      (갱신 때마다. G: 동기화 폴더에 쓰면 드라이브가 올린다)
"""
import gzip
import shutil
import subprocess
import sys
import tarfile
from datetime import date
from pathlib import Path

R = Path(__file__).parent
DRIVE = Path(r'G:\내 드라이브\백업\화장실')
오늘 = date.today().isoformat()
날짜 = DRIVE / 오늘
sys.path.insert(0, str(R))
from backup_data import key_values                      # noqa: E402

핵심파일 = ['data/id_registry.json', 'data/classify.json', 'data/golden.json', 'data/rail_stations.csv',
            'data/location_fixes.csv', 'data/coord_overrides.csv', 'data/sgg_codes.json', 'data/gov_sites.json']
snap = sorted((R / 'data' / 'snapshots').iterdir())[-1]

# ── 0. 키 검사부터 (T35: 키를 못 찾으면 그 자체가 이상이다)
keys = key_values()
if not keys:
    print('★ 키 문자열을 하나도 못 찾았다 — 검사가 헛돈다. 중단.')
    raise SystemExit(1)
볼것 = [R / f for f in 핵심파일 if (R / f).exists()] + list(snap.iterdir())
샌것 = [p.name for p in 볼것 if any(k in p.read_bytes() for k in keys)]
if 샌것:
    print('★ 키가 든 파일:', 샌것, '— 중단')
    raise SystemExit(1)
print(f'키 {len(keys)}개로 검사 · 담을 파일 {len(볼것)}개 · 키 든 파일 0개')

for d in ('핵심', '원천', '저장소'):
    (날짜 / d).mkdir(parents=True, exist_ok=True)

# ── 1. 핵심 — 큰 것만 압축
for f in 핵심파일:
    p = R / f
    if not p.exists():
        continue
    if p.stat().st_size > 512 * 1024:
        with p.open('rb') as i, gzip.open(날짜 / '핵심' / (p.name + '.gz'), 'wb', compresslevel=9) as o:
            shutil.copyfileobj(i, o)
    else:
        shutil.copy2(p, 날짜 / '핵심' / p.name)

# ── 2. 원천 — 그날의 기준본(원천 API는 현재분만 주므로 다시 못 받는다)
with tarfile.open(날짜 / '원천' / f'snapshot_{snap.name}.tar.gz', 'w:gz') as t:
    for x in sorted(snap.iterdir()):
        t.add(x, arcname=f'{snap.name}/{x.name}')

# ── 3. 저장소 — 커밋된 것 전부(앱 소스·문서·앱 데이터)
subprocess.run(['git', 'bundle', 'create', str(날짜 / '저장소' / '화장실.bundle'), '--all'],
               cwd=R, check=True, capture_output=True)

# ── 4. 복구 안내 + 보관 4벌
벌 = sorted([p for p in DRIVE.iterdir() if p.is_dir()], reverse=True) if DRIVE.exists() else []
for 옛 in 벌[4:]:
    shutil.rmtree(옛)
    print('옛 벌 지움:', 옛.name)
벌 = sorted([p for p in DRIVE.iterdir() if p.is_dir()], reverse=True)
표 = '\n'.join(f'| {p.name} | {sum(f.stat().st_size for f in p.rglob("*") if f.is_file())/1024/1024:,.0f} MB |' for p in 벌)
(DRIVE / '복구안내.md').write_text(f"""# 복구 안내 — 너의 화장실은. (갱신 {오늘})

구글 드라이브 `내 드라이브\\백업\\화장실\\`에 **날짜 폴더 4벌**을 둔다. 보통 **가장 최신 날짜**를 쓰고, 그게 잘못됐으면 앞 날짜로 간다.

## 날짜 폴더 안
| 폴더 | 내용 |
|---|---|
| `핵심\\` | **영구번호 대장**(`id_registry.json.gz`) · 사람이 고친 위치(`location_fixes`·`coord_overrides`) · 사전(`classify`) · 골든 표본(`golden`) · 역 좌표표(`rail_stations`) · 코드표(`sgg_codes`) · 구청 누리집·대표전화(`gov_sites`) |
| `원천\\` | 그날의 **기준본**(`snapshot_<날짜>.tar.gz`) — 원천 API는 **현재분만** 주므로 지난 기준본은 **다시 받을 수 없다** |
| `저장소\\` | `화장실.bundle` — git 묶음(커밋된 것 전부: 앱 소스·문서·앱 데이터). `git clone 화장실.bundle 화장실`로 되살린다 |

## 들어 있지 않은 것
- **캐시**(카카오·주소·네이버): 비쌀 뿐 **다시 만들 수 있다**(API 13만 회). GitHub 비공개 저장소 `commax1581-hub/toilet-map-data`에 있다.
- **API 키**(`착한식당\\.env`·`API키.txt`): 백업에 담지 않는다. 담을 때 키 문자열 검사를 통과한 것만 올린다.
- 커밋 안 된 작업.

## 왜 이것부터인가
**영구번호 대장을 잃으면 공유 링크가 전부 무효**가 된다 — 되돌릴 방법이 없다. 기준본도 지난 날짜는 원천에서 못 받는다.
나머지는 느리더라도 다시 만들 수 있다.

## 지금 보관 중인 벌
| 날짜 | 크기 |
|---|---|
{표}
""", encoding='utf-8')

크기 = sum(f.stat().st_size for f in 날짜.rglob('*') if f.is_file())
print(f'{날짜.name}: {크기/1024/1024:,.1f} MB')
for d in sorted(날짜.iterdir()):
    print(f"  {d.name}/ {sum(f.stat().st_size for f in d.rglob('*') if f.is_file())/1024/1024:,.1f} MB · {len(list(d.iterdir()))}개")
print('보관 벌:', [p.name for p in 벌])
