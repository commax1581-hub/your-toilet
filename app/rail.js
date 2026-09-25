/* 역 안 화장실 — 운영기관이 주는 별개 데이터.
   본 데이터(지자체 공중화장실)와 **합치지 않고 잇는다**(규약 4-1 · 사례지식 6-24).
   그래서 화면에서도 섞지 않는다 — 연한 청록 상자에 담고 출처를 머리띠에 적는다(6-27).
   목록에서는 **거리순에 그대로 섞인다**(먼저 거리, 그다음 성격). */
'use strict';

let RAIL = null, railJob = null;

/** 운영기관 → 노선 앞에 붙일 지역(이미 지역이 든 노선이름은 그대로) */
function lineLabel(st) {
  const R = { 서울교통공사: '서울', 서울시메트로9호선주식회사: '서울', 인천교통공사: '인천', 부산교통공사: '부산',
    부산김해경전철주식회사: '김해', 대구교통공사: '대구', 남양주도시공사: '남양주', 코레일: '' };
  const reg = R[st.op] === undefined ? '' : R[st.op];
  const ln = /선$|경전철$/.test(st.ln) ? st.ln : st.ln;
  return (reg && !ln.startsWith(reg) ? `${reg} ` : '') + ln;
}

function loadRail() {
  if (!railJob) {
    railJob = fetch('data/rail.json').then((r) => {
      if (!r.ok) throw new Error('rail');
      return r.json();
    }).then((d) => (RAIL = d)).catch(() => (RAIL = { s: [], count: 0 }));   // 없으면 조용히 없는 대로(본 데이터는 그대로 뜬다)
  }
  return railJob;
}

/** 기준점에서 반경 안의 역 — 노선마다 다른 줄이다(환승역은 노선별로 출입구가 떨어져 있다, 6-29) */
function railNear(la, lo, meters) {
  if (!RAIL) return [];
  return RAIL.s.map((st) => ({ st, m: distM(la, lo, st.la, st.lo) }))
    .filter((x) => x.m <= meters)
    .sort((a, b) => a.m - b.m);
}

/** 여는 시간 — 서울교통공사만 시각을 준다(302곳 전부 05:00~24:00). 국가철도공단은 **칸 자체가 없다**(역 565곳).

    없는 값을 지어내지 않되, 565곳을 통째로 "시간 확인"으로 죽이지도 않는다(6-4에서 겪은 실수) →
    **첫차~막차로 안내하되 단정하지 않는다**: 글은 회색 "보통 첫차~막차", 상태는 `likely`.
    "지금 열림만"에서는 likely도 통과시킨다 — 그래야 역이 목록에 남는다(결정 6-27 시간 1안). */
const RAIL_HOURS = [5 * 60, 24 * 60];                     // 첫차~막차의 대략(서울교통공사 표기와 같다)

function railState(st, now) {
  const ht = (st.t[0] && st.t[0].ht) || '';
  const mm = ht.match(/(\d{1,2}):(\d{2})\s*~\s*(\d{1,2}):(\d{2})/);
  const cur = now.getHours() * 60 + now.getMinutes();
  if (!mm) {
    const likely = cur >= RAIL_HOURS[0] && cur < RAIL_HOURS[1];
    return { k: likely ? 'likely' : 'late',
      html: likely ? '<span class="st ask">보통 첫차~막차</span>'
        : '<span class="st shut">지금은 닫혀 있을 수 있어요</span>' };
  }
  const a = +mm[1] * 60 + +mm[2], b = (+mm[3] === 24 ? 24 * 60 : +mm[3] * 60) + +mm[4];
  const open = cur >= a && cur < b;
  return { k: open ? 'open' : 'shut',
    html: `<span class="st ${open ? 'open' : 'shut'}">${open ? '지금 열림' : '지금 닫힘'} · ${ht.trim()}</span>` };
}

/** 화장실 한 칸 — 층·개찰구·출구는 배지로, 상세위치는 글로(이 데이터의 값은 '말로 하는 안내'다) */
function railSeat(t) {
  return `<div class="rrow"><span class="flr">${esc(t.f)}</span>
      <span class="gate ${t.g ? 'in' : 'out'}"><svg class="ic"><use href="#i-gate"/></svg>개찰구 ${t.g ? '안' : '밖'}</span>
      ${t.x ? `<span class="ex"><svg class="ic"><use href="#i-exit"/></svg>${esc(t.x)}번 출구</span>` : ''}</div>
    <div class="rwhere">${esc(t.w || '자세한 위치가 적혀 있지 않아요')}${t.s ? ` · ${t.s.split('').join(' · ')}` : ''}</div>`;
}

function railCard(st, m, now, i, also, sameName) {
  const s = railState(st, now);
  const gongdan = st.src === '국가철도공단';
  const nm = `${lineLabel(st)} ${st.n}역`;
  const ll = `${st.la},${st.lo}`;
  return `<div class="railbox" data-rail="${i}">
      <div class="rhead"><svg class="ic"><use href="#i-train"/></svg>역 안 화장실<span class="who">${esc(st.src)}</span></div>
      <div class="rbody">
        <div class="rh"><b><span class="ln">${esc(lineLabel(st))}</span>${esc(st.n)}역</b>${distHtml(m)}</div>
        ${sameName ? '<div class="rsame">같은 역이지만 <b>노선이 달라</b> 화장실이 따로 있어요</div>' : ''}
        ${st.t.map(railSeat).join('')}
        <div class="meta">${s.html}</div>
        ${also ? '<div class="ralso"><svg class="ic"><use href="#i-wc"/></svg> 이 역은 <b>지자체 자료에도</b> 있어요 — 아래 흰 카드에서 변기 수·전화를 볼 수 있습니다.</div>' : ''}
        <div class="rgo">
          <a class="btn main sm" href="https://map.naver.com/p/directions/-/${st.lo},${st.la},${encodeURIComponent(nm)}/-/walk" target="_blank" rel="noopener" data-stop><svg><use href="#i-walk"/></svg>길찾기</a>
          <a class="btn ghost sm" href="https://map.kakao.com/link/roadview/${ll}" target="_blank" rel="noopener" data-stop><svg><use href="#i-eye"/></svg>입구 보기</a>
        </div>
        ${gongdan ? '<div class="rnone"><svg class="ic"><use href="#i-q"/></svg> 이 출처는 <b>여는 시간과 변기 수를 제공하지 않습니다.</b> 없다는 뜻이 아닙니다.</div>' : ''}
      </div>
    </div>`;
}

/** 역 상세 — 본 데이터 상세와 같은 자리를 쓰되, **그 출처의 값만** 보여 준다(값을 섞지 않는다) */
function openRailDetail(st, m) {
  const now = new Date(), s = railState(st, now), t0 = st.t[0] || {};
  const nm = `${lineLabel(st)} ${st.n}역`;
  const ll = `${st.la},${st.lo}`;
  const tel = String(t0.tel || '').replace(/[^0-9+-]/g, '');
  const fac = (t) => (t.m === undefined ? '' : `<div class="fgrid">
      <div class="fbox${t.m[0] + t.m[1] ? '' : ' off'}"><svg style="color:var(--male)"><use href="#i-male"/></svg><div class="fl">남성</div><div class="fn">대 ${t.m[0]} · 소 ${t.m[1]}</div></div>
      <div class="fbox${t.fm ? '' : ' off'}"><svg style="color:var(--female)"><use href="#i-female"/></svg><div class="fl">여성</div><div class="fn">${t.fm}칸</div></div>
      <div class="fbox${t.ac[0] + t.ac[1] ? '' : ' off'}"><svg style="color:var(--acc)"><use href="#i-acc"/></svg><div class="fl">장애인</div><div class="fn">남 ${t.ac[0]} · 여 ${t.ac[1]}</div></div>
      <div class="fbox${t.ch[0] + t.ch[1] ? '' : ' off'}"><svg style="color:var(--baby)"><use href="#i-child"/></svg><div class="fl">어린이</div><div class="fn">남 ${t.ch[0]} · 여 ${t.ch[1]}</div></div>
      <div class="fbox${t.dp[0] + t.dp[1] ? '' : ' off'}"><svg style="color:var(--baby)"><use href="#i-diaper"/></svg><div class="fl">기저귀 교환대</div><div class="fn">${t.dp[0] || t.dp[1] ? `${t.dp[0] ? '남자' : ''}${t.dp[0] && t.dp[1] ? '·' : ''}${t.dp[1] ? '여자' : ''} 화장실` : '없음'}</div></div>
      <div class="fbox${t.bl ? '' : ' off'}"><svg style="color:var(--open)"><use href="#i-bell"/></svg><div class="fl">비상벨</div><div class="fn">${t.bl ? '있음' : '없음'}</div></div>
      <div class="fbox${t.cc ? '' : ' off'}"><svg style="color:var(--acc)"><use href="#i-cctv"/></svg><div class="fl">입구 CCTV</div><div class="fn">${t.cc ? '있음' : '없음'}</div></div>
    </div>`);

  $('#dt-s').textContent = `${hhmm(now)} 기준 · ${st.src} ${(RAIL.date || {})[st.src] || ''}`;
  $('#detail-body').innerHTML = `
    <div class="dhead rail">
      <div class="dn"><span class="ln">${esc(lineLabel(st))}</span>${esc(st.n)}역</div>
      <div class="da">${esc(st.op)} · <b>${esc(st.src)}</b>가 제공한 정보</div>
      <div class="meta">${s.html}</div>
      ${m != null ? `<div class="dm"><svg><use href="#i-walk"/></svg>${m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`} · 걸어서 약 ${Math.max(1, Math.round(m / WALK))}분</div>` : ''}
    </div>
    <div class="dnote"><b>역 한 곳에 점 하나</b>지도의 점은 <b>역 위치</b>입니다. 역 안 어디인지는 아래 <b>층·개찰구·출구</b>를 보세요.</div>
    ${st.t.some((t) => t.g) ? '<div class="dnote"><b>개찰구 안</b>교통카드로 들어가야 쓸 수 있는 곳이 있습니다.</div>' : ''}
    ${st.src === '국가철도공단' ? '<div class="dnote"><b>이 출처가 주지 않는 것</b>여는 시간·변기 수·기저귀교환대·비상벨이 <b>이 데이터에는 없습니다.</b> 없다는 뜻이 아닙니다.</div>' : ''}
    <div class="dsec"><h3>역 안 어디에 (${st.t.length}곳)</h3>
      ${st.t.map((t) => `<div class="rseat">${railSeat(t)}${fac(t)}</div>`).join('')}
      <div class="dsub">층은 <b>지면에서 가까운 순</b>으로, 같은 층이면 <b>개찰구 밖</b>을 먼저 보여 줍니다.</div>
    </div>
    <div class="dsec"><h3>길찾기</h3>
      <div class="dbtns">
        <a class="btn main" href="https://map.naver.com/p/directions/-/${st.lo},${st.la},${encodeURIComponent(nm)}/-/walk" target="_blank" rel="noopener"><svg><use href="#i-walk"/></svg>네이버 도보 길찾기</a>
        <a class="btn ghost" href="https://map.kakao.com/link/to/${encodeURIComponent(nm)},${ll}" target="_blank" rel="noopener"><svg><use href="#i-pin"/></svg>카카오맵 길찾기<small>자동차 기준</small></a>
      </div>
      <div class="dsub">역 출입구까지 안내합니다. <b>출입구를 지나서는 위 안내를 보고</b> 찾아가세요.
        카카오맵 길찾기는 <b>자동차 경로로 열립니다.</b></div>
    </div>
    <div class="dsec"><h3>지도·입구 확인</h3>
      <div class="dbtns">
        <a class="btn ghost" href="https://map.kakao.com/link/map/${encodeURIComponent(nm)},${ll}" target="_blank" rel="noopener"><svg><use href="#i-pin"/></svg>카카오맵</a>
        <a class="btn ghost" href="https://map.kakao.com/link/roadview/${ll}" target="_blank" rel="noopener"><svg><use href="#i-eye"/></svg>카카오 로드뷰</a>
      </div>
    </div>
    ${tel ? `<div class="dsec"><h3>역 전화</h3><div class="dorg"><b>${esc(st.op)}</b>
        <a class="btn ghost" href="tel:${tel}"><svg><use href="#i-tel"/></svg>${esc(t0.tel)}</a></div></div>` : ''}
    <div class="dsec"><h3>이 정보는</h3>
      <div class="dsub">출처 <b>${esc(st.src)}</b>(공공데이터포털) · 기준일 ${(RAIL.date || {})[st.src] || ''}${t0.ry ? ` · 리모델링 ${esc(t0.ry)}년` : ''}<br>
        지자체 공중화장실 데이터와 <b>합치지 않고 따로</b> 보여 줍니다. 두 출처의 값을 섞으면, 틀렸을 때 <b>누구에게 알려야 할지</b> 알 수 없기 때문입니다.</div>
      <div class="dfix"><b>정보가 틀렸나요?</b><br>① <b>${esc(st.op)}</b>(원천데이터 관리기관)에 알리기 ② <a href="https://www.data.go.kr/tcs/opd/ndm/view.do" target="_blank" rel="noopener">공공데이터포털 오류 신고</a>
        <div class="dsub">역 화장실의 <b>원천데이터 관리기관</b>은 철도 운영기관입니다 — 지자체에 알리면 고쳐지지 않습니다.</div></div>
    </div>`;
  markDetail({ k: 'r', n: `${st.n}역`, la: st.la, lo: st.lo, st });
  go('detail');
  $('#detail-body').scrollTop = 0;
}
