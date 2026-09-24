"""확인 목록 검수 시트 — 도로명·지번 중 어느 쪽이 맞는지 사람이 고르도록 두 주소와 지도 링크를 나란히 놓는다.
대상: data/location_fixes.csv 의 조치 'check'(단서가 없어 도로명 좌표로 표시 중인 곳)
결과: data/processed/check_sheet.html (표·검색·정렬, 지도 링크), data/processed/check_sheet.csv (결정 칸)
결정 쓰는 법: CSV의 '결정' 칸에 도로명 / 지번 / 숨김 을 적으면 다음 단계에서 반영(apply_check_sheet)
실행: python make_check_sheet.py
"""
import html, sys
from pathlib import Path
import pandas as pd
from addr_util import clean
from geocode_toilets import by_address, dist_m, save_cache

ROOT = Path(__file__).parent
P = ROOT / 'data' / 'processed'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def kmap(name, la, lo):
    return f'https://map.kakao.com/link/map/{html.escape(str(name))},{la},{lo}'


def kroad(la, lo):
    return f'https://map.kakao.com/link/roadview/{la},{lo}'


def main():
    fx = pd.read_csv(ROOT / 'data' / 'location_fixes.csv', dtype=str, encoding='utf-8-sig').fillna('')
    ck = fx[fx['조치'] == 'check']
    snap = max((ROOT / 'data' / 'snapshots').iterdir())
    g = pd.read_csv(snap / 'toilets_geo.csv', dtype=str, encoding='utf-8-sig').fillna('').set_index('영구번호')
    rows = []
    for r in ck.itertuples():
        x = g.loc[r.영구번호]
        L = by_address(clean(x['소재지지번주소']))
        if not L:
            continue
        d = round(dist_m((float(x['위도']), float(x['경도'])), (L['위도'], L['경도'])))
        rows.append({'영구번호': r.영구번호, '시도': x['코드시도'], '시군구': x['코드시군구'], '지역': '시·구' if x['코드시군구'].endswith(('시', '구')) else '군',
                     '이름': x['화장실명'], '도로명주소': x['소재지도로명주소'], '지번주소': x['소재지지번주소'], '거리m': d,
                     '도로명_위도': x['위도'], '도로명_경도': x['경도'], '지번_위도': L['위도'], '지번_경도': L['경도'],
                     '지번_등급': L['좌표정확도'], '결정': ''})
    save_cache()
    df = pd.DataFrame(rows).sort_values(['지역', '거리m'], ascending=[True, False])
    df.to_csv(P / 'check_sheet.csv', index=False, encoding='utf-8-sig')

    tr = []
    for i, r in enumerate(df.itertuples(), 1):
        tr.append(f'''<tr data-area="{r.지역}">
<td>{i}</td><td>{html.escape(r.영구번호)}</td><td>{html.escape(r.시도)} {html.escape(r.시군구)}<br><small>{r.지역}</small></td>
<td class="nm">{html.escape(r.이름)}</td>
<td>{html.escape(r.도로명주소)}<br><a href="{kmap(r.이름, r.도로명_위도, r.도로명_경도)}" target="_blank">지도</a> ·
<a href="{kroad(r.도로명_위도, r.도로명_경도)}" target="_blank">로드뷰</a></td>
<td>{html.escape(r.지번주소)}<br><a href="{kmap(r.이름, r.지번_위도, r.지번_경도)}" target="_blank">지도</a> ·
<a href="{kroad(r.지번_위도, r.지번_경도)}" target="_blank">로드뷰</a> <small>({r.지번_등급})</small></td>
<td class="d">{r.거리m:,}m</td></tr>''')
    doc = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>확인 목록 — 도로명 vs 지번</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;800&display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#eef1f5;font-family:'Noto Sans KR',sans-serif;color:#15202b;font-size:14px;word-break:keep-all}}
header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #e3e8ee;padding:14px 16px;z-index:2}}
h1{{margin:0 0 4px;font-size:18px}} p{{margin:0;color:#5b6875;font-size:13px}}
.tools{{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
input,select{{border:1px solid #e3e8ee;border-radius:10px;padding:8px 10px;font-family:inherit;font-size:14px}}
table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{border-bottom:1px solid #eef1f5;padding:9px 10px;text-align:left;vertical-align:top}}
th{{background:#f5f7fa;position:sticky;top:104px;font-size:13px}}
td.nm{{font-weight:700;min-width:140px}} td.d{{text-align:right;white-space:nowrap;font-weight:700}}
a{{color:#4338ca;font-weight:700;text-decoration:none}} small{{color:#5b6875}}
tr:hover{{background:#fbfcfe}}
</style></head><body>
<header><h1>확인 목록 {len(df):,}곳 — 도로명주소 vs 지번주소</h1>
<p>같은 화장실인데 두 주소가 300m 넘게 떨어져 있고, 어느 쪽이 맞는지 기계가 판단하지 못한 곳. <b>지금은 도로명 좌표로 표시 중</b>입니다.
지도·로드뷰를 열어 비교한 뒤, 같은 폴더의 <code>check_sheet.csv</code> '결정' 칸에 <b>도로명 / 지번 / 숨김</b>을 적어 주세요.</p>
<div class="tools"><input id="q" placeholder="이름·주소 검색" size="26">
<select id="area"><option value="">전체 지역</option><option value="시·구">시·구(도시)</option><option value="군">군</option></select>
<span id="cnt" style="color:#5b6875"></span></div></header>
<table><thead><tr><th>#</th><th>번호</th><th>지역</th><th>이름</th><th>도로명주소(현재 표시 위치)</th><th>지번주소(다른 후보)</th><th>거리</th></tr></thead>
<tbody id="tb">{''.join(tr)}</tbody></table>
<script>
const rows=[...document.querySelectorAll('#tb tr')], q=document.getElementById('q'), area=document.getElementById('area'), cnt=document.getElementById('cnt');
function f(){{const t=q.value.trim(), a=area.value; let n=0;
rows.forEach(r=>{{const ok=(!t||r.innerText.includes(t))&&(!a||r.dataset.area===a); r.style.display=ok?'':'none'; n+=ok;}});
cnt.textContent=n.toLocaleString()+'곳';}}
q.oninput=f; area.onchange=f; f();
</script></body></html>'''
    (P / 'check_sheet.html').write_text(doc, encoding='utf-8')
    print(f'확인 목록 {len(df):,}곳 — 지역: ' + ', '.join(f'{k} {v:,}' for k, v in df['지역'].value_counts().items()))
    print('거리: 300~500m ' + str(int(((df['거리m'] > 300) & (df['거리m'] <= 500)).sum())) + ' · 500m~1km ' + str(int(((df['거리m'] > 500) & (df['거리m'] <= 1000)).sum())) +
          ' · 1~5km ' + str(int(((df['거리m'] > 1000) & (df['거리m'] <= 5000)).sum())) + ' · 5km 넘음 ' + str(int((df['거리m'] > 5000).sum())))
    print(f'저장: data/processed/check_sheet.html, check_sheet.csv')


if __name__ == '__main__':
    main()
