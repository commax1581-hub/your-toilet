"""개방시간 해석 — 원본(개방시간 코드 + 개방시간상세 자유 입력)을 앱이 계산할 수 있는 구조로 바꾼다.
공식 코드 뜻(행안부 점검표): 상시 = 24시간 개방 / 정시 = (00:00 ~ 00:00) 시각 기재 / 불규칙 / 미개방
코드 '불규칙'이라도 상세에 시각이 또렷하면 그 시각을 따른다(2026-09-24 결정) — 담당자가 코드를 잘못 고른 경우가 많다. 앱은 'irregular'를 받아 "시간이 바뀔 수 있어요"로 고지한다.
원칙: 애매하면 'unknown'(앱에 "시간 확인 필요") — 열렸다고 했는데 닫혀 있는 게 가장 나쁘다.

parse(code, detail) → {
  'kind': 'always' | 'hours' | 'unknown' | 'closed',
  'rules': [{'days': [0..6] (월=0), 'open': 'HH:MM', 'close': 'HH:MM'}],   # close <= open 이면 자정 넘김, '24:00' 가능
  'holiday': [{'open','close'}] | None,   # (공휴일) 표기가 따로 있을 때
  'breaks': [{'from','to'}],               # 점심시간 제외 등
  'said': [0..6],                          # 원문이 직접 말한 요일(매일·평일·주말·토·일) — 앱의 주말·공휴일 판단에 쓴다
  'reason': 해석 근거·모르는 이유(보고서용)
}
state(sched, now, holidays=set()) → ('open', 닫는 시각) / ('soon', 닫는 시각) / ('closed', 다음 여는 datetime|None) / ('unknown', None)
설계: docs/사례지식.md 1-6, 착한가격 버그이력 #24(자정 넘김)
"""
import re
from datetime import datetime, timedelta

ALL = list(range(7))
WEEKDAY = [0, 1, 2, 3, 4]
DAYWORD = {'평일': WEEKDAY, '주중': WEEKDAY, '월~금': WEEKDAY, '월-금': WEEKDAY, '주말': [5, 6], '토·일': [5, 6], '토일': [5, 6],
           '토요일': [5], '(토)': [5], '토)': [5], '일요일': [6], '(일)': [6], '일)': [6], '매일': ALL, '연중': ALL}
DAYRX = re.compile('|'.join(sorted(map(re.escape, DAYWORD), key=len, reverse=True)))   # 긴 말 먼저('평일'의 '일'을 일요일로 읽지 않게)
SOON_MIN = 30
TILDE = str.maketrans({'∼': '~', '～': '~', '〜': '~', '–': '-', '—': '-', '−': '-', '：': ':'})
RANGE = re.compile(r'(?<![\d:])(\d{1,2})\s*(?::\s*(\d{2}))?\s*시?\s*[~\-]\s*(?:익일|익)?\s*(\d{1,2})\s*(?::?\s*(\d{2}))?\s*시?(?![\d:])')   # 익일01:00, 09:00~1800
COMPACT = re.compile(r'(?<!\d)(\d{2})(\d{2})\s*[~\-]\s*(\d{2})(\d{2})(?!\d)')     # 0900-1800
ALWAYS = re.compile(r'24\s*시간|^\s*24\s*시\s*$|항시\s*개방|상시|^\s*24\s*$|연중\s*무휴\s*24|00:00\s*[~\-]\s*(24:00|23:59|00:00)|^0\s*[~\-]\s*24$')
SEASON = re.compile(r'하절기|동절기|학기|방학|시즌|성수기|비수기|개장\s*기간|\d+\s*월\s*[~\-]\s*\d+\s*월|\d+\s*~\s*\d+\s*월')
VAGUE = re.compile(r'근무|영업|운영|개관|개장|공연|행사|일출|일몰|해\s*뜰|해\s*질|이용\s*시간|관리인|협의|문의|수시|필요\s*시')
BREAK = re.compile(r'(\d{1,2}:\d{2})\s*[~\-]\s*(\d{1,2}:\d{2})\s*(?:제외|미개방|휴게|점심|폐쇄)')
LUNCH = re.compile(r'점심\s*시간?\s*(?:제외|미개방)?')


def _hm(h, m, end=False):
    """시각 → 'HH:MM'. 닫는 시각은 25~30시(= 다음 날 01~06시, '05:00~25:00')도 받는다"""
    h, m = int(h), int(m or 0)
    if end and 24 < h <= 30:
        h -= 24
    if h > 24 or m > 59 or (h == 24 and m):
        return None
    return f'{h:02d}:{m:02d}'


def norm(s):
    s = str(s or '').translate(TILDE).strip()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r':\s*\.', ':', s)                          # 23:.00 오타
    s = COMPACT.sub(lambda m: f'{m[1]}:{m[2]}~{m[3]}:{m[4]}', s)
    return s


def ranges(s):
    out = []
    for m in RANGE.finditer(s):
        o, c = _hm(m[1], m[2]), _hm(m[3], m[4], end=True)
        if o and c:
            out.append((o, c, m.start(), m.end()))
    return out


def _days_before(s, pos):
    """시간 앞에 붙은 요일 말(가장 가까운 것) — 앞 시간대 뒤부터만 본다"""
    last = None
    for m in DAYRX.finditer(s[:pos]):
        last = DAYWORD[m.group(0)]
    return last


def parse(code, detail):
    code, raw = str(code or '').strip(), str(detail or '').strip()
    s = norm(raw)
    if code == '미개방':
        return {'kind': 'closed', 'rules': [], 'holiday': None, 'breaks': [], 'reason': '미개방'}
    if code == '불규칙' and not ranges(s):
        return {'kind': 'unknown', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'불규칙({raw})' if raw else '불규칙'}
    if re.fullmatch(r'\(?\s*미개방\s*\)?', s):
        return {'kind': 'closed', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'{code}인데 상세가 미개방 → 숨김(보수적으로)'}
    rs = ranges(s)
    # 상시: 상세에 24시간이 아닌 시각이 따로 적혀 있으면 상세를 따른다(더 보수적으로)
    if code == '상시' and not [r for r in rs if not ALWAYS.search(f'{r[0]}~{r[1]}')]:
        return {'kind': 'always', 'rules': [], 'holiday': None, 'breaks': [], 'reason': '상시'}
    if not s:
        return {'kind': 'unknown', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'{code or "코드 없음"}·상세 없음'}
    if SEASON.search(s):
        return {'kind': 'unknown', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'계절·기간별({raw})'}
    if ALWAYS.search(s) and len(rs) <= 1:
        return {'kind': 'always', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'상세 24시간({raw})'}
    if not rs:
        why = '말로 적힘' if VAGUE.search(s) else ('시간 길이만' if re.search(r'^\d+\s*시간$', s) else '읽지 못함')
        return {'kind': 'unknown', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'{why}({raw})'}

    breaks = [{'from': _hm(*b.split(':')), 'to': _hm(*e.split(':'))} for b, e in BREAK.findall(s)]
    if LUNCH.search(s) and not breaks:
        breaks = [{'from': '12:00', 'to': '13:00'}]
    brk_spans = {(b['from'], b['to']) for b in breaks}
    rules, holiday, closed_days, said = [], None, set(), set()
    for o, c, st, _ in rs:
        if (o, c) in brk_spans:
            continue
        days = _days_before(s, st)
        if '공휴일' in s[max(0, st - 8):st]:
            holiday = [{'open': o, 'close': c}]
            continue
        if days:
            said.update(days)                        # 원문이 그 요일을 직접 말했다(매일·평일·주말·토·일)
        rules.append({'days': days or ALL, 'open': o, 'close': c})
    for w, d in (('월요일', [0]), ('월', [0]), ('일요일', [6]), ('주말', [5, 6]), ('토요일', [5]), ('공휴일', None)):
        if re.search(w + r'\s*(휴관|휴무|휴일|미개방|미운영|폐쇄|제외)', s):
            if d is None:
                holiday = []
            else:
                closed_days.update(d)
    if closed_days:
        for r in rules:
            r['days'] = [d for d in r['days'] if d not in closed_days]
    # 요일 지정 없이 시간대가 여러 개면(오전·오후 등) 모두 같은 요일로 두되, 겹치는 요일에 두 규칙 — 계산에서 합쳐짐
    if not rules:
        return {'kind': 'unknown', 'rules': [], 'holiday': None, 'breaks': [], 'reason': f'읽지 못함({raw})'}
    return {'kind': 'hours', 'rules': rules, 'holiday': holiday, 'breaks': breaks,
            'said': sorted(said - closed_days), 'irregular': code == '불규칙',   # 코드는 '불규칙'인데 시각이 적힌 곳 → 적힌 시각을 따르되 앱에서 고지
            'reason': (f'코드 불규칙 · 상세 시각 따름({raw})' if code == '불규칙' else raw)}


def _min(hm):
    h, m = map(int, hm.split(':'))
    return h * 60 + m


def _intervals(sched, day, holidays):
    """그 날짜(date)의 열린 구간들 [(시작 datetime, 끝 datetime)] — 자정 넘김은 끝이 다음 날"""
    base = datetime(day.year, day.month, day.day)
    if day in holidays and sched.get('holiday') is not None:
        rules = [{'days': ALL, **r} for r in sched['holiday']]
    else:
        rules = [r for r in sched['rules'] if day.weekday() in r['days']]
    out = []
    for r in rules:
        o, c = _min(r['open']), _min(r['close'])
        if c <= o:
            c += 24 * 60                                 # 자정 넘김(22:00~06:00), 00:00~00:00은 always로 먼저 걸러짐
        out.append((base + timedelta(minutes=o), base + timedelta(minutes=c)))
    # 쉬는 시간 빼기
    for b in sched.get('breaks', []):
        bs, be = base + timedelta(minutes=_min(b['from'])), base + timedelta(minutes=_min(b['to']))
        cut = []
        for s, e in out:
            if be <= s or bs >= e:
                cut.append((s, e))
            else:
                if s < bs:
                    cut.append((s, bs))
                if be < e:
                    cut.append((be, e))
        out = cut
    return sorted(out)


def state(sched, now, holidays=frozenset()):
    k = sched['kind']
    if k == 'always':
        return ('open', None)
    if k in ('unknown', 'closed'):
        return (k, None)
    days = [now.date() - timedelta(days=1), now.date()]
    for s, e in sorted(i for d in days for i in _intervals(sched, d, holidays)):
        if s <= now < e:
            # 바로 이어지는 구간(24:00~ 다음 날 00:00 등)은 합쳐서 닫는 시각 계산
            end = e
            for s2, e2 in sorted(i for d in [now.date(), now.date() + timedelta(days=1)] for i in _intervals(sched, d, holidays)):
                if s2 <= end < e2 or s2 == end:
                    end = max(end, e2)
            return ('soon' if end - now <= timedelta(minutes=SOON_MIN) else 'open', end)
    for i in range(0, 8):
        d = now.date() + timedelta(days=i)
        for s, e in _intervals(sched, d, holidays):
            if s > now:
                return ('closed', s)
    return ('closed', None)
