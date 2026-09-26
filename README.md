# 너의 화장실은.

지금 있는 자리에서 **가장 가까운 화장실**을 찾아 주는 모바일 웹. 공공데이터로 만든 **비영리 개인 사례**이며 공식 서비스가 아니다.

**→ https://your-toilet.pages.dev**

자료 둘을 쓴다. **합치지 않고 화면에서 잇는다**(출처가 다르면 관리기관도 다르기 때문).

| 자료 | 원천데이터 관리기관 | 규모 |
|---|---|---|
| 공중·개방화장실 | **지자체**(시·군·구) — 행정안전부 공중화장실정보 | 51,793곳 |
| 역 안 화장실 | **철도 운영기관** — 국가철도공단 · 서울교통공사 | 역 833곳 · 966칸 |

---

## 앱

```
python -m http.server 8000 --directory app     # http://localhost:8000
```
카카오 JS 키에 `localhost:8000`이 등록돼 있어야 지도가 뜬다([배포설정기록](docs/배포설정기록.md) 2-4).

- **화면**: 첫 화면 → 위치 확정(내 위치 / 주소·건물 검색) → 가까운 목록 → 상세 · 지도 보기
- **하단 탭 넷**: 가까운 곳 · 저장한 곳 · 최근 본 곳 · 알아보기
- **역 카드**는 연한 청록 상자로 **출처를 구분**해 거리순에 섞어 보여 준다(층·개찰구 안팎·출구·자세한 위치)
- **거르기**: 지금 열림 · 반경 · 안심/장애인/기저귀/어린이 · 시설 종류 · **개찰구 밖만**
- **보기 설정**(첫 화면 `⚙` 또는 알아보기): 밝게·어둡게·기기 설정 / 글씨 보통·크게·아주 크게
- **저장**: 설정과 **사용자가 스스로 담은 것**(저장한 곳·최근 본 곳)만 **기기 안에** 남고 서버로 보내지 않는다. 한 번에 지울 수 있다
- **오프라인**: `app/sw.js` — 화면 파일 + 지도 칸(기준일별 서랍). 알아보기의 **「미리 받아 두기」**로 둘레 5×5칸을 미리 받는다. 카카오 지도는 남의 서버라 저장할 수 없어 오프라인에서는 목록·상세만 된다
- **검수용**: `?la=37.5665&lo=126.9780&acc=15` — 위치 허용 없이 그 자리에서 시작
- 화면 파일을 고치면 **`python bump_version.py`** (주소에 내용 해시를 붙여 옛 파일을 쓰지 않게 — 배포 전 필수)

**구성**: `index.html` · `style.css` · `app.js`(목록·검색·필터) · `hours.js`(개방시간 판정) · `detail.js`(상세) · `mapview.js`(지도) · `rail.js`(역) · `saved.js`(저장·최근·오프라인) · `mobile.js`(앱 안 브라우저·홈 화면 추가) · `sw.js` · `img/`

---

## 데이터 만들기 (처음 한 번 — 2026-09-22에 실행)

1. `python collect_toilets.py` — OpenAPI로 전국 수집 → `data/raw/toilets_<날짜>.csv`
2. `python profile_toilets.py` — 현황 보고
3. `python refine_address.py` — 도로명주소 API 정제·검증·건물관리번호
4. `python geocode_toilets.py` — 카카오 좌표 + 정확도 등급(A·B·B산·P·C·X) + 산지 교차 확인
5. `python report_geo.py` — 표시 기준 적용 결과
6. `python build_registry.py` — 영구 번호 대장(`data/id_registry.json`) + 기준본(`data/snapshots/`)
7. `python campus_coords.py` — 캠퍼스·단지 건물 좌표(`data/coord_overrides.csv`)
8. `python verify_locations.py [--naver-sample 300]` — 도로명·지번 어긋남, 필지 번지 불일치, **시설 이름으로 찾기** → `data/location_fixes.csv`
   - 검수 시트: `python make_check_sheet.py`
9. `python build_sgg_codes.py` — 자치단체코드 → **법정동 시군구코드**(`data/sgg_codes.json`). 구청 안내를 이름이 아니라 코드로 찾기 위해 — **`build_app_data.py`보다 먼저**(T32)
10. `python build_app_data.py` — 앱 데이터(지도 칸 파일, `app/data/`). 시군구청 누리집도 이때 `../공통지식/기준자료/행정구역/시군구_누리집.json`에서 `app/data/gov_sites.json`으로 복사한다
11. `python check_data.py` — 불변조건 검사(실패면 배포하지 않음)
12. `python audit_data.py` — 내용 정밀 점검(고치지 않고 보고만)
13. `python fetch_holidays.py` — 공휴일(1년에 한 번)
14. `python build_gov_links.py` — 시군구청 누리집을 **새로 모을 때만**. 기준 목록은 공통지식 `시군구_누리집.json`(시군구코드 키, 267곳) — 세 프로젝트가 같이 쓴다. 이 스크립트는 **후보**만 `data/gov_sites_candidates.json`에 쓰고 **기준 표와 다른 곳을 보여 준다**(반영은 사람이). 네이버 지역검색이 `○○구청`에 가게를 주므로 **세 가지로 거른다** — 관청 도메인 · 이름이 '청'으로 끝남 · 첫 화면 제목에 시군구 이름(T33)

## 역 안 화장실

```
python build_rail.py          # 역 좌표표 data/rail_stations.csv (기관×노선×역 833행·역 739개)
python build_rail_app.py      # 앱 데이터 app/data/rail.json (212KB · 역 833곳 · 966칸)
```
- 좌표는 **노선마다 따로** 찾는다 — 환승역은 노선별로 출입구가 떨어져 있다(서울역 1↔4호선 332m).
- 지난 판과 견줘 **사라진 역**을 찾는다. 역은 없어지지 않으므로 사라졌다면 **개명이거나 오류**다.
- 갱신은 **반기 1회**, 역명 대조는 **연 1회**(규약 1-1 「이름은 키가 아니다」).

## 갱신

**확인은 자주, 처리는 바뀔 때만.** 지자체가 자기 기록을 고치는 주기는 연 단위다(2026년 12% · 2025년 19% · 2024년 49%).
- **주 1회**: 원본의 기준일만 확인 → 바뀌었으면 아래를 돌린다 · **월 1회는 바닥선**(변화가 없어도 한 번은 돌려 파이프라인이 살아 있는지 본다)

```
python update.py                                   # 수집 → 변경 분류 → 바뀐 곳만 정제·좌표 → 제안 + 보고서
python update.py --publish data/processed/update_<날짜>   # 사람이 확인한 뒤 반영
python build_sgg_codes.py && python build_app_data.py && python check_data.py && python golden.py
python bump_version.py                             # 그리고 commit → push (자동 배포)
```
- 보고서의 **사람이 볼 목록 5가지**를 본다. 특히 **`swapped_ids.csv`**(같은 번호, 다른 시설)는 결정 칸을 채워야 반영된다 — 원천이 관리번호를 재사용하면 **우리 영구번호가 다른 화장실을 가리킨다**(사례지식 6-33).
- 원천 주소를 급히 고칠 때: `data/address_overrides.csv`

## 백업·점검

```
python backup_data.py [--prune]   # 비공개 저장소로. 핵심은 매번 · 캐시는 월 1회(.gz) · 중복은 담지 않음
python check_links.py             # 외부 링크 생존(시군구 홈페이지 267곳 + 고정 링크)
python build_gov_links.py --verify   # 누리집이 정말 그 구청인지(연 1회) — 살아 있다고 맞는 건 아니다(T33)
python check_docs.py              # 문서끼리·문서와 코드가 어긋나지 않았는지
```

## 시험

```
python test_diff_update.py   # 변경 분류·번호 유지(15항목)
python test_hours.py         # 개방시간 해석(57항목)
python test_hours_js.py      # hours.py ↔ app/hours.js 맞대보기 (node 필요)
python golden.py             # 골든 표본 100곳 + 역 30곳. 갱신은 --make / --make-rail
```

시설 종류 사전: `data/classify.json` · 키: `.env`의 `DATAGOKR_KEY`·`JUSO_KEY`·`KAKAO_REST_KEY`(없으면 `../착한식당/.env`)

---

## 문서

- [앱 구현 시작점](docs/앱구현-시작점.md) — 다음 작업은 여기부터
- [사례 지식](docs/사례지식.md) — 조사·결정·결과 (6-1 ~ 6-37)
- [버그 이력](docs/버그이력.md) — 무엇이 틀렸고 어떻게 막나 (T1 ~ T31)
- [배포 설정 기록](docs/배포설정기록.md) — 배포·운영 설정과 함정, 카카오 무료 쿼터
- 목업: `design/` (첫 화면·아이콘·역 카드)
- 재사용 모듈·공통 규약: [`../공통지식`](../공통지식) · 모듈 문서는 아직 `../착한식당/docs/`
