"""앱 파일 주소에 내용 해시를 붙인다 — 브라우저가 옛 파일을 계속 쓰지 않도록.
화면 파일을 고친 뒤 실행: python bump_version.py
(배포 때도 이걸 돌리고 올린다. 착한가격은 손으로 번호를 올렸다가 캐시 때문에 헤맸다.)
"""
import hashlib, re, sys
from pathlib import Path

APP = Path(__file__).parent / 'app'
FILES = ['style.css', 'hours.js', 'app.js', 'detail.js', 'mapview.js', 'rail.js', 'saved.js']
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

html = APP / 'index.html'
s = html.read_text(encoding='utf-8')
for name in FILES:
    v = hashlib.md5((APP / name).read_bytes()).hexdigest()[:8]
    s = re.sub(r'(["\'])' + re.escape(name) + r'(\?v=[0-9a-f]+)?\1', lambda m, n=name, v=v: f'{m.group(1)}{n}?v={v}{m.group(1)}', s)
    print(f'{name} → {v}')
html.write_text(s, encoding='utf-8')
print('index.html 갱신')
