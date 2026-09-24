/* 개방시간 판정 — hours.py 의 state() 를 브라우저로 옮긴 것. 두 곳의 규칙이 같아야 한다.
   h = {k:'a' 항상 | 'h' 시각 | 'u' 확인 필요,
        r:  [[요일비트, 'HHMM', 'HHMM'], ...]   요일비트: 월=1, 화=2, 수=4, 목=8, 금=16, 토=32, 일=64
        hd: [['HHMM','HHMM'], ...]             공휴일 표기가 따로 있을 때(빈 배열 = 공휴일 휴무)
        br: [['HHMM','HHMM'], ...]}            쉬는 시간(점심 등)
   state(h, now, holidays) → {k:'open'|'soon'|'closed'|'unknown', until:Date, next:Date, always:true}
   원칙: 애매하면 'unknown'("시간 확인"). 열렸다고 했는데 닫혀 있는 게 가장 나쁘다. */
(function (global) {
  const SOON_MIN = 30;          // 닫기 30분 전이면 "곧 닫힘"

  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const mins = (s) => +s.slice(0, 2) * 60 + +s.slice(2);
  const pyDay = (d) => (d.getDay() + 6) % 7;                       // 월=0 (파이썬과 같게)
  const at = (day, m) => new Date(day.getFullYear(), day.getMonth(), day.getDate(), 0, m);

  /** 그 날짜에 열린 구간들 [[시작, 끝]] — 자정을 넘기면 끝이 다음 날 */
  function intervals(h, day, holidays) {
    let rules;
    if (h.hd && holidays.has(ymd(day))) rules = h.hd;              // 공휴일 표기가 있으면 그것만 (빈 배열이면 하루 종일 닫힘)
    else rules = (h.r || []).filter((r) => r[0] & (1 << pyDay(day))).map((r) => [r[1], r[2]]);
    let out = rules.map(([o, c]) => {
      const s = mins(o);
      let e = mins(c);
      if (e <= s) e += 1440;                                       // 22:00~06:00
      return [at(day, s), at(day, e)];
    });
    for (const [bf, bt] of h.br || []) {                           // 쉬는 시간 빼기
      const bs = at(day, mins(bf)), be = at(day, mins(bt)), cut = [];
      for (const [s, e] of out) {
        if (be <= s || bs >= e) cut.push([s, e]);
        else {
          if (s < bs) cut.push([s, bs]);
          if (be < e) cut.push([be, e]);
        }
      }
      out = cut;
    }
    return out.sort((a, b) => a[0] - b[0]);
  }

  function state(h, now, holidays) {
    holidays = holidays || new Set();
    if (!h || h.k === 'u') return { k: 'unknown' };
    if (h.k === 'a') return { k: 'open', always: true };
    const day = (off) => new Date(now.getFullYear(), now.getMonth(), now.getDate() + off);
    const span = (offs) => offs.reduce((a, o) => a.concat(intervals(h, day(o), holidays)), []).sort((a, b) => a[0] - b[0]);
    for (const [s, e] of span([-1, 0])) {                          // 어제 시작해 자정을 넘긴 구간도 본다
      if (s <= now && now < e) {
        let end = e;
        for (const [s2, e2] of span([0, 1])) {                     // 바로 이어지는 구간은 합쳐서 닫는 시각을 낸다
          if ((s2 <= end && end < e2) || +s2 === +end) end = new Date(Math.max(+end, +e2));
        }
        return { k: end - now <= SOON_MIN * 60000 ? 'soon' : 'open', until: end };
      }
    }
    for (let i = 0; i < 8; i++) {
      for (const [s] of intervals(h, day(i), holidays)) if (s > now) return { k: 'closed', next: s };
    }
    return { k: 'closed', next: null };
  }

  global.Hours = { state, intervals };
})(typeof window !== 'undefined' ? window : globalThis);   // 브라우저와 node(시험) 모두에서 쓴다
