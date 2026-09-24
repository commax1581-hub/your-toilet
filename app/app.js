/* 가장 가까운 화장실 — 1단계: 첫 화면 → 위치 확정(핀) → 가까운 목록
   데이터: app/data/index.json(칸 목록) + app/data/t/<행>_<열>.json(0.05도 ≈ 5km 칸)
   규칙은 docs/앱구현-시작점.md 4·5장. 위치는 저장하지 않는다(화면 안에서만 쓴다). */
'use strict';

const TILE = 0.05;              // 지도 칸 크기(도)
const WALK = 67;                // 도보 분당 m
/* 공휴일에 닫혀 있을 가능성이 큰 시설 종류 — 여는 시각이 적혀 있어도 "휴일 확인"으로 낮춘다.
   원본에 공휴일 표기가 있는 카드는 129곳뿐이라, 종류로 판단한다(사례지식 6-2).
   낮추지 않는 곳: 역·터미널·주유소·공원·하천·산·바다·주차장·쉼터·시장·상가·병원·복지·체육·종교 — 휴일에도 사람이 오는 곳 */
const HOLI_ASK = new Set(['관공서', '공공시설', '문화·관광', '대학', '민간시설']);

const KINDS = [
  { l: '공중', c: 'pub', i: '#i-public' },
  { l: '개방', c: 'opn', i: '#i-opendoor' },
  { l: '간이', c: 'opn', i: '#i-opendoor' },
  { l: '이동식', c: 'opn', i: '#i-opendoor' },
];

const S = {                      // 화면 상태(저장하지 않음)
  screen: 'home',
  mode: 'gps',                   // 'gps' 내 위치 / 'other' 다른 곳
  base: null,                    // {la, lo, addr, sub}
  gps: null,                     // {la, lo, acc}
  radius: 500,
  query: null,                   // 검색으로 고른 장소 {name, la, lo}
  openOnly: true,                // 기본은 "지금 열림"만
  index: null,
  holidays: new Set(),
  tiles: new Map(),
};
let map = null, geocoder = null, places = null, gpsMark = null, gpsCircle = null, addrSeq = 0;

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
/** 기준 위치 줄에 쓸 짧은 주소 — 지금 있는 시·도 이름은 빼서 도로명·건물이 잘리지 않게 */
const shortAddr = (a) => String(a || '').replace(/^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도|서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)\s+/, '');
const hhmm = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;

/* ── 화면 전환 ─────────────────────────────
   화면 이동을 브라우저 이력에 넣는다 — 휴대폰의 뒤로 가기가 앱을 닫지 않고 한 단계씩 돌아가게. */
function go(name, fromPop) {
  const same = S.screen === name;
  S.screen = name;
  document.querySelectorAll('.screen').forEach((el) => el.classList.toggle('on', el.id === `s-${name}`));
  if (name === 'pin' && map) setTimeout(() => map.relayout(), 0);
  if (name === 'search') setTimeout(() => $('#q').focus(), 60);
  if (!fromPop) {
    if (same) history.replaceState({ s: name }, '');
    else history.pushState({ s: name }, '');
  }
}
history.replaceState({ s: 'home' }, '');
window.addEventListener('popstate', (e) => go((e.state && e.state.s) || 'home', true));
document.querySelectorAll('[data-go]').forEach((b) => (b.onclick = () => go(b.dataset.go)));
document.querySelectorAll('[data-back]').forEach((b) => (b.onclick = () => history.back()));

/* ── 첫 화면: 지금 시각으로 배경 (낮 06~17 · 저녁 17~20 · 밤 20~06) ── */
(function background() {
  const h = new Date().getHours();
  const f = h >= 6 && h < 17 ? 'bg_day_blue_1080.webp' : h >= 17 && h < 20 ? 'bg_evening_1080.webp' : 'bg_night_1080.webp';
  $('#s-home').style.backgroundImage = `url(img/${f})`;
})();

function homeMsg(t) {
  const el = $('#home-msg');
  el.innerHTML = t || '';
  el.classList.toggle('on', !!t);
}

/* ── 데이터 ─────────────────────────────── */
let indexJob = null;
function loadIndex() {                                    // 여러 번 불려도 한 번만 받는다
  if (!indexJob) indexJob = fetchIndex();
  return indexJob;
}
async function fetchIndex() {
  const [idx, hol] = await Promise.all([
    fetch('data/index.json').then((r) => r.json()),
    fetch('data/holidays.json').then((r) => r.json()).catch(() => ({})),
  ]);
  S.index = idx;
  Object.values(hol).forEach((days) => days.forEach((d) => S.holidays.add(d)));
  return idx;
}

/** 기준점이 든 칸 + 둘레 8칸 (반경이 칸보다 작아도 칸 경계에 있을 수 있다) */
async function nearby(la, lo) {
  const idx = await loadIndex();
  const r0 = Math.floor(la / TILE), c0 = Math.floor(lo / TILE), out = [];
  const jobs = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      const k = `${r0 + dr}_${c0 + dc}`;
      if (!idx.tiles[k]) continue;
      if (!S.tiles.has(k)) S.tiles.set(k, fetch(`data/t/${k}.json`).then((r) => r.json()));
      jobs.push(S.tiles.get(k).then((recs) => out.push(...recs)));
    }
  }
  await Promise.all(jobs);
  return out;
}

/** 직선거리(m) */
function distM(la1, lo1, la2, lo2) {
  const R = 6371000, rad = Math.PI / 180;
  const dla = (la2 - la1) * rad, dlo = (lo2 - lo1) * rad;
  const a = Math.sin(dla / 2) ** 2 + Math.cos(la1 * rad) * Math.cos(la2 * rad) * Math.sin(dlo / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

/* ── 내 위치 ─────────────────────────────── */
$('#b-gps').onclick = () => {
  if (!navigator.geolocation) return homeMsg('이 브라우저는 위치를 알려주지 않아요. <b>다른 곳</b>으로 찾아 주세요.');
  const btn = $('#b-gps'), keep = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin" style="margin:0 auto"></span><div class="t">위치 확인 중</div><div class="s">잠시만요</div>';
  homeMsg('');
  navigator.geolocation.getCurrentPosition(
    (p) => {
      btn.disabled = false; btn.innerHTML = keep;
      S.gps = { la: p.coords.latitude, lo: p.coords.longitude, acc: p.coords.accuracy || 0 };
      S.query = null;
      openPin('gps');
    },
    (err) => {
      btn.disabled = false; btn.innerHTML = keep;
      homeMsg(err.code === 1
        ? '위치를 쓸 수 없어요. <b>다른 곳</b>에서 주소·장소 이름으로 찾을 수 있어요.'
        : '위치를 받지 못했어요(신호가 약할 수 있어요). <b>다른 곳</b>으로 찾아 주세요.');
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
  );
};
$('#b-other').onclick = () => { S.mode = 'other'; go('search'); };
$('#b-tosearch').onclick = () => { S.mode = 'other'; go('search'); };

/** 지도 위 "내 위치" — 지도를 끌다가 되돌아오는 길 */
$('#b-tomy').onclick = () => {
  if (!navigator.geolocation || !map) return;
  const btn = $('#b-tomy');
  btn.classList.add('on');
  navigator.geolocation.getCurrentPosition(
    (p) => {
      btn.classList.remove('on');
      S.gps = { la: p.coords.latitude, lo: p.coords.longitude, acc: p.coords.accuracy || 0 };
      S.query = null;                                  // 내 위치로 옮기면 "찾으신 곳"은 지운다
      openPin('gps');
    },
    () => {                                          // 실패해도 화면을 막지 않는다 — 지도 위에 알리고 그대로 둔다
      btn.classList.remove('on');
      $('#pin-warn').innerHTML = '<b>위치를 받지 못했어요</b><br>지도를 움직여 핀을 맞춰 주세요';
      $('#pin-warn').classList.add('on');
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
  );
};

/* ── 핀으로 위치 확정 ────────────────────── */
function kakaoReady() {
  return new Promise((res, rej) => {
    if (window.__kakaoFail || !window.kakao || !window.kakao.maps) return rej(new Error('kakao'));
    if (map) return res();
    kakao.maps.load(() => {
      geocoder = new kakao.maps.services.Geocoder();
      places = new kakao.maps.services.Places();
      res();
    });
  });
}

async function openPin(mode, at) {
  S.mode = mode;
  const c = at || S.gps;
  $('#pin-radius').hidden = mode === 'gps';
  $('#pin-s').textContent = mode === 'gps' ? '지도를 움직여 핀을 정확한 자리에 맞춰 주세요' : '핀을 옮기고 반경을 고를 수 있어요';
  $('#b-here').textContent = mode === 'gps' ? '여기 맞아요' : '이 위치에서 찾기';
  go('pin');
  try {
    await kakaoReady();
  } catch (e) {
    // 지도를 못 불러오면(키 도메인 미등록·네트워크) 좌표만으로 진행한다
    $('#pin-warn').innerHTML = '<b>지도를 불러오지 못했어요</b><br>좌표만으로 가까운 곳을 찾습니다';
    $('#pin-warn').classList.add('on');
    $('#pin-addr').textContent = `${c.la.toFixed(5)}, ${c.lo.toFixed(5)} 근처`;
    $('#pin-sub').textContent = '지도 없이 진행';
    S.base = { la: c.la, lo: c.lo, addr: '지금 위치', sub: '' };
    return;
  }
  const center = new kakao.maps.LatLng(c.la, c.lo);
  if (!map) {
    map = new kakao.maps.Map($('#map'), { center, level: 3 });
    kakao.maps.event.addListener(map, 'idle', () => showAddr(map.getCenter()));
  } else {
    map.relayout();
    map.setCenter(center);
    map.setLevel(3);
  }
  // GPS 점과 오차 원 — 오차가 크면 핀을 옮기라고 안내
  if (mode === 'gps' && S.gps) {
    if (gpsMark) gpsMark.setMap(null);
    if (gpsCircle) gpsCircle.setMap(null);
    gpsMark = new kakao.maps.Circle({ center, radius: 5, strokeWeight: 3, strokeColor: '#fff', fillColor: '#2563eb', fillOpacity: 1 });
    gpsMark.setMap(map);
    if (S.gps.acc > 20) {
      gpsCircle = new kakao.maps.Circle({ center, radius: S.gps.acc, strokeWeight: 1.5, strokeColor: '#2563eb', strokeOpacity: .5, fillColor: '#2563eb', fillOpacity: .12 });
      gpsCircle.setMap(map);
    }
    const bad = S.gps.acc > 100;
    $('#pin-warn').classList.toggle('on', bad);
    if (bad) $('#pin-warn').innerHTML = `<b>위치가 정확하지 않아요</b> (오차 약 ${Math.round(S.gps.acc)}m)<br>핀을 지금 계신 곳으로 옮겨 주세요`;
  } else {
    $('#pin-warn').classList.remove('on');
  }
  showAddr(center);
}

/** 핀 아래 주소 — 카카오 좌표→주소 */
function showAddr(ll) {
  const la = ll.getLat(), lo = ll.getLng(), seq = ++addrSeq;
  S.base = { la, lo, addr: '이 위치', sub: '' };
  $('#pin-sub').textContent = S.mode === 'gps' && S.gps
    ? `내 위치에서 ${Math.round(distM(S.gps.la, S.gps.lo, la, lo))}m · 오차 약 ${Math.round(S.gps.acc)}m`
    : '핀을 옮기면 주소가 바뀌어요';
  geocoder.coord2Address(lo, la, (res, st) => {
    if (seq !== addrSeq) return;                                  // 지도를 계속 움직인 경우 늦게 온 답은 버린다
    if (st !== kakao.maps.services.Status.OK || !res.length) { $('#pin-addr').textContent = '주소를 찾지 못했어요'; return; }
    const r = res[0], a = (r.road_address && r.road_address.address_name) || (r.address && r.address.address_name) || '';
    $('#pin-addr').textContent = a ? `${a} 근처` : '주소를 찾지 못했어요';
    $('#pin-q').textContent = a ? shortAddr(a) : '주소 · 건물 이름으로 찾기';
    S.base = { la, lo, addr: a || '이 위치', sub: (r.road_address && r.road_address.building_name) || '' };
  });
}

$('#pin-radius').onclick = (e) => {
  const sp = e.target.closest('span[data-r]');
  if (!sp) return;
  S.radius = +sp.dataset.r;
  $('#pin-radius').querySelectorAll('span').forEach((x) => x.classList.toggle('on', x === sp));
};
$('#b-here').onclick = () => { S.openOnly = true; showList(); };

/* ── 다른 곳 찾기 ──────────────────────────
   한글은 입력기가 글자를 조립하는 동안 Enter가 먹히지 않는다(조립 확정으로 쓰임) → Enter만 두면
   "아무 반응이 없는" 화면이 된다. 그래서 ① 검색 버튼 ② 글자를 멈추면 자동 검색 ③ Enter, 셋 다 받는다. */
let searchJob = 0, searchTimer = null, lastQuery = '';

function pickPlace(p) {
  S.base = { la: p.la, lo: p.lo, addr: p.name, sub: p.addr };
  S.query = { name: p.name, la: p.la, lo: p.lo };      // 이름으로 찾아온 곳 — 목록 맨 위에 그 장소의 화장실을 먼저 보여 준다
  openPin('other', p);
}

function showSug(list, q) {
  const box = $('#sug');
  if (!list.length) {
    box.innerHTML = `<div class="note"><b>'${esc(q)}'로 찾은 곳이 없어요</b><br>
      건물·역·공원 이름이나 <b>도로명 주소</b>로 찾아 보세요. 예) 서울역, 여의도 한강공원, 세종대로 110</div>`;
    return;
  }
  box.innerHTML = list.map((p, i) => `<button class="sug" data-i="${i}"><b>${esc(p.name)}</b><span>${esc(p.addr)}</span></button>`).join('');
  box.querySelectorAll('.sug').forEach((b) => (b.onclick = () => pickPlace(list[+b.dataset.i])));
}

async function doSearch(q, auto) {
  q = (q || '').trim();
  const box = $('#sug');
  if (q.length < 2) {                                          // 한 글자로는 결과가 너무 많다
    if (!auto) box.innerHTML = '<div class="note">두 글자 이상 넣어 주세요.</div>';
    return;
  }
  if (auto && q === lastQuery) return;
  lastQuery = q;
  const job = ++searchJob;
  box.innerHTML = '<div class="loading">찾는 중…</div>';
  try {
    await kakaoReady();
  } catch (err) {
    box.innerHTML = `<div class="note"><b>장소 검색을 쓸 수 없어요</b><br>지도 기능을 불러오지 못했습니다.
      주소창이 <b>localhost:8000</b>인지, 인터넷이 연결돼 있는지 확인해 주세요.</div>`;
    return;
  }
  const done = (list) => { if (job === searchJob) showSug(list, q); };
  places.keywordSearch(q, (data, st) => {
    if (st === kakao.maps.services.Status.OK && data.length) {
      done(data.slice(0, 12).map((d) => ({ name: d.place_name, addr: d.road_address_name || d.address_name, la: +d.y, lo: +d.x })));
      return;
    }
    geocoder.addressSearch(q, (ad, st2) => {                    // 이름으로 못 찾으면 주소로(도로명·지번)
      done(st2 === kakao.maps.services.Status.OK
        ? ad.slice(0, 12).map((d) => ({ name: d.address_name, addr: (d.road_address && d.road_address.address_name) || d.address_name, la: +d.y, lo: +d.x }))
        : []);
    });
  }, { size: 12 });
}

$('#f-search').onsubmit = (e) => { e.preventDefault(); $('#q').blur(); doSearch($('#q').value); };
$('#q').oninput = (e) => {                                     // 글자를 멈추면 자동으로 찾는다(조립 중에는 기다린다)
  clearTimeout(searchTimer);
  if (e.isComposing) return;
  const q = e.target.value;
  searchTimer = setTimeout(() => doSearch(q, true), 350);
};
$('#q').addEventListener('compositionend', (e) => {            // 한글 한 글자가 완성된 순간도 검색 대상
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => doSearch(e.target.value, true), 350);
});

/* ── 검색한 장소의 화장실 먼저 ─────────────
   이름으로 찾아온 사람에게는 그 장소가 답이다 — 묶음 규칙과 상관없이 맨 위에 따로 보여 준다.
   비교는 군더더기 말을 뺀 뒤 서로 포함하는지로 본다(같은 이름의 다른 지역을 집지 않게 300m 안만). */
const nameCore = (s) => String(s || '').replace(/\(.*?\)/g, '')
  .replace(/공중화장실|개방화장실|간이화장실|화장실|주차장|공영|본점|점포/g, '')
  .replace(/[\s·,()\[\]{}\-_]/g, '');

function isQueryHit(rec, m) {
  if (!S.query || m > 300) return false;
  const a = nameCore(rec.n), b = nameCore(S.query.name);
  return a.length >= 2 && b.length >= 2 && (a.includes(b) || b.includes(a));
}

/* ── 카드 내용 ─────────────────────────── */
const ymdStr = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/** 카드의 상태 — 개방시간 판정에 "쉬는 날(공휴일·주말)이면 관공서·사무실은 확인"을 더한다.
    원문이 그 날을 직접 말했으면(공휴일 표기 `hd`, 매일, 토·일·주말) 그 말을 먼저 따른다. */
function cardState(rec, now) {
  const s = Hours.state(rec.h, now, S.holidays);
  if (s.k === 'unknown' || rec.h.k !== 'h' || !HOLI_ASK.has(rec.ft)) return s;
  const wd = (now.getDay() + 6) % 7, dw = rec.h.dw || 0;
  if (S.holidays.has(ymdStr(now))) {
    return rec.h.hd ? s : { k: 'unknown', holi: '공휴일' };     // 공휴일 시간이 따로 적힌 곳만 그대로(81곳)
  }
  if (wd >= 5 && !(dw & (1 << wd))) return { k: 'unknown', holi: '주말' };   // 토·일을 말한 적 없다
  return s;
}

function statePill(rec, now) {
  const s = cardState(rec, now);
  if (s.k === 'unknown') return { s, html: `<span class="st ask">${s.holi ? s.holi + ' 확인' : '시간 확인'}</span>` };
  if (s.k === 'open' && s.always) return { s, html: '<span class="st open">상시</span>' };
  if (s.k === 'open') {
    const t = s.until, h24 = t.getHours() % 24;
    const lab = t.getMinutes() ? hhmm(t) : h24 === 0 ? '자정' : `${h24}시`;
    return { s, html: `<span class="st open">${lab}까지</span>` };
  }
  if (s.k === 'soon') return { s, html: `<span class="st soon">곧 닫힘 · ${hhmm(s.until)}</span>` };
  return { s, html: s.next ? `<span class="st shut">${hhmm(s.next)} 열림</span>` : '<span class="st shut">닫힘</span>' };
}

/** 위치 정확도 뱃지 — 주소로 건물이 확정된 곳에는 아무것도 붙이지 않는다 */
function accBadge(rec) {
  if (rec.g !== 'P') return '';
  return rec.pc
    ? '<span class="acc2 lv3"><svg><use href="#i-build"/></svg>시설 위치</span>'
    : '<span class="acc2 lv4"><svg><use href="#i-q"/></svg>추정</span>';
}

/** 카드 한 줄 안내(사례지식 2-13) */
function notice(rec, st) {
  const n = [];
  if (rec.h.ir) n.push("적힌 시각 기준(원본 표기 '불규칙') · <b>시간이 바뀔 수 있어요</b>");
  if (st && st.holi) n.push(`${st.holi === '주말' ? '주말' : '오늘은 공휴일'} · <b>닫혀 있을 수 있어요</b>`);
  if (rec.g === 'P') n.push(rec.pc ? '시설 위치 기준 · <b>입구·안내판 확인</b>' : '이름으로 찾은 위치 · <b>정확하지 않을 수 있어요</b>');
  else if (rec.w === 'M') n.push('산지에 있어요 · <b>주차장·입구 쪽</b>');
  else if (rec.w === 'W') n.push('범위가 넓어요 · <b>주차장·입구 쪽</b>');
  if (rec.t === 3) n.push('이동식 화장실 · <b>위치가 바뀔 수 있어요</b>');
  if (rec.gs) n.push('주유소 · <b>직원에게 문의</b>');
  if (rec.gt === 1) n.push('개찰구 안 · <b>교통카드 필요</b>');
  else if (rec.gt === 0) n.push('개찰구 밖 · 표 없이 이용');
  return n.length ? `<div class="note">${n.join('<br>')}</div>` : '';
}

function facRow(rec, more) {
  if (rec.ni) return `<div class="fac"><span class="none">시설 정보 없음</span>${more || ''}</div>`;
  const male = (rec.m || [0, 0])[0] + (rec.m || [0, 0])[1];
  const acc = (rec.x || [0, 0])[0] + (rec.x || [0, 0])[1];
  const kid = (rec.c || [0, 0])[0] + (rec.c || [0, 0])[1];
  const one = (color, icon, num, on) =>
    `<span class="${on ? '' : 'no'}" ${on ? `style="color:var(--${color})"` : ''}><svg><use href="#i-${icon}"/></svg>${on && num ? num : ''}</span>`;
  return '<div class="fac">'
    + one('male', 'male', male, male > 0)
    + one('female', 'female', rec.fq ? '?' : rec.f, rec.fq ? true : rec.f > 0)
    + one('acc', 'acc', acc, acc > 0)
    + one('baby', 'diaper', '', rec.dp === 1)
    + (kid > 0 ? one('baby', 'child', kid, true) : '')
    + (rec.bl === 1 ? one('open', 'bell', '', true) : '')
    + (more || '') + '</div>';
}

function distHtml(m) {
  const lab = m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`;
  return `<div class="dist">${lab}<small>${Math.max(1, Math.round(m / WALK))}분</small></div>`;
}

/** 같은 좌표(같은 건물)에 쌓인 카드의 이름 —
    층만 다른 같은 시설이면 공통 앞부분("○○지하상가 · 3곳"),
    이름이 서로 다른 시설이면 이름을 함께 보여 준다("대구역 · 롯데백화점 대구점") — 한 이름만 쓰면 나머지가 없는 것처럼 보인다 */
function groupName(list) {
  const names = list.map((r) => r.n);
  let p = names[0];
  for (const n of names.slice(1)) {
    let i = 0;
    while (i < p.length && i < n.length && p[i] === n[i]) i++;
    p = p.slice(0, i);
  }
  p = p.replace(/[\s(\[{\-·]+$/, '');
  if (p.length >= 3) return `${p} · ${list.length}곳`;
  const two = names.slice(0, 2).join(' · ');
  return list.length > 2 ? `${two} 외 ${list.length - 2}곳` : two;
}

/** 묶음 카드의 시설 수 — 그 자리에 있는 것을 모두 더한다(한 곳만 보여 주면 나머지가 빠진다) */
function sumFac(list) {
  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const t = { m: [0, 0], f: 0, x: [0, 0], c: [0, 0], dp: 0, bl: 0, cc: 0, ni: 1, ft: list[0].ft, h: list[0].h };
  for (const r of list) {
    t.m = add(t.m, r.m || [0, 0]);
    t.f += r.f || 0;
    t.x = add(t.x, r.x || [0, 0]);
    t.c = add(t.c, r.c || [0, 0]);
    t.dp = Math.max(t.dp, r.dp || 0);
    t.bl = Math.max(t.bl, r.bl || 0);
    if (!r.ni) t.ni = 0;
  }
  if (!t.ni && t.f === 0) t.fq = 1;
  return t;
}

function cardHtml(rec, m, now) {
  const k = KINDS[rec.t] || KINDS[0], st = statePill(rec, now);
  const shut = st.s.k === 'closed';
  return `<div class="card${shut ? ' shut' : ''}">
    <div class="h"><div class="grow" style="min-width:0"><div class="n">${esc(rec.n)}</div><div class="adr">${esc(shortAddr(rec.a))}</div></div>${distHtml(m)}</div>
    <div class="meta"><span class="pill ${k.c}"><svg><use href="${k.i}"/></svg>${k.l}</span>${st.html}${accBadge(rec)}</div>
    ${facRow(rec)}${notice(rec, st.s)}</div>`;
}

function groupHtml(list, m, now, gi) {
  const nowOpen = list.filter((r) => ['open', 'soon'].includes(cardState(r, now).k)).length;
  const kinds = [...new Set(list.map((r) => r.t))].slice(0, 2).map((t) => KINDS[t] || KINDS[0]);
  const label = nowOpen ? `<span class="st open">${nowOpen}곳 열림</span>` : '<span class="st shut">닫힘</span>';
  return `<div class="card group" data-g="${gi}" role="button" tabindex="0">
      <div class="h"><div class="grow" style="min-width:0"><div class="n">${esc(groupName(list))}</div><div class="adr">${esc(shortAddr(list[0].a))} · 같은 자리 ${list.length}곳</div></div>${distHtml(m)}</div>
      <div class="meta">${kinds.map((k) => `<span class="pill ${k.c}"><svg><use href="${k.i}"/></svg>${k.l}</span>`).join('')}${label}</div>
      ${facRow(sumFac(list))}<div class="more2">펼쳐 보기 ›</div>
    </div>
    <div class="kids" id="kids-${gi}">${list.map((r) => cardHtml(r, m, now)).join('')}</div>`;
}

/* ── 목록 ─────────────────────────────── */
async function showList() {
  go('list');
  const body = $('#list-body');
  body.innerHTML = '<div class="loading">가까운 곳을 찾는 중…</div>';
  const now = new Date(), base = S.base;
  const recs = await nearby(base.la, base.lo);
  const idx = S.index;
  $('#list-s').textContent = `${hhmm(now)} 기준 · 공공데이터 ${idx.date}`;

  // 거리 → 같은 좌표끼리 묶기
  const withD = recs.map((r) => ({ r, m: distM(base.la, base.lo, r.la, r.lo) })).sort((a, b) => a.m - b.m);
  const inR = (radius, openOnly) => withD.filter((x) => x.m <= radius
    && (!openOnly || ['open', 'soon'].includes(cardState(x.r, now).k)));

  // 검색한 장소의 화장실은 "지금 열림"과 상관없이 맨 위에(찾아온 목적지라 닫혀 있어도 알려 줘야 한다)
  const hits = (S.query ? withD.filter((x) => isQueryHit(x.r, x.m)) : []).slice(0, 6);   // 너무 많으면 목록이 밀린다
  const hitIds = new Set(hits.map((x) => x.r.id));
  let shown = inR(S.radius, S.openOnly).filter((x) => !hitIds.has(x.r.id));
  const hitHtml = hits.length
    ? `<div class="secline">찾으신 곳 · ${esc(S.query.name)}</div>`
      + hits.map((x) => cardHtml(x.r, x.m, now)).join('')
      + `<div class="secline">둘레 ${S.radius < 1000 ? `${S.radius}m` : '1km'} 안</div>`
    : '';
  const head = `<div class="basebar"><b>📍 ${esc(shortAddr(base.addr))}<span class="r">이 위치에서 ${S.radius < 1000 ? `${S.radius}m` : '1km'} 안</span></b><button id="b-change">위치 바꾸기</button></div>
    <div class="chips"><span class="chip${S.openOnly ? ' on' : ''}" id="c-open">지금 열림</span></div>`;
  const foot = `<div class="foot">출처 행정안전부 공중화장실정보(공공데이터포털) · 기준일 ${idx.date}<br>
    실제와 다를 수 있습니다. 시설 상태·개방 시간은 관리기관에 확인해 주세요.<br>
    <a href="https://www.data.go.kr/tcs/opd/ndm/view.do" target="_blank" rel="noopener">공공데이터 오류 신고</a></div>`;

  if (!shown.length) {
    const wider = [1000, 2000, 5000].find((r) => r > S.radius && inR(r, S.openOnly).length);
    const all = inR(S.radius, false).length;
    body.innerHTML = head + hitHtml + `<div class="empty"><svg><use href="#i-pin"/></svg>
        <b>${S.radius < 1000 ? `${S.radius}m` : `${S.radius / 1000}km`} 안에 ${S.openOnly ? '지금 열린 곳이' : '화장실이'} 없어요</b>
        <div class="sub">${wider ? `${wider < 1000 ? `${wider}m` : `${wider / 1000}km`} 안에 ${inR(wider, S.openOnly).length}곳` : '가까운 곳에 등록된 화장실이 없습니다'}${S.openOnly && all ? ` · 닫힘·시간 확인 ${all - shown.length}곳` : ''}</div>
      </div>
      ${wider ? `<button class="btn main" id="b-wide">${wider < 1000 ? `${wider}m` : `${wider / 1000}km`}까지 넓혀 보기</button>` : ''}
      ${S.openOnly && all ? '<button class="btn ghost" style="margin-top:8px" id="b-all">닫힌 곳·시간 확인 필요 포함</button>' : ''}` + foot;
    if (wider) $('#b-wide').onclick = () => { S.radius = wider; showList(); };
    if ($('#b-all')) $('#b-all').onclick = () => { S.openOnly = false; showList(); };
  } else {
    const groups = new Map();
    for (const x of shown) {
      const key = `${x.r.la},${x.r.lo}`;
      if (!groups.has(key)) groups.set(key, { m: x.m, list: [] });
      groups.get(key).list.push(x.r);
    }
    const cards = [...groups.values()].map((g, i) =>
      g.list.length > 1 ? groupHtml(g.list, g.m, now, i) : cardHtml(g.list[0], g.m, now)).join('');
    const hidden = inR(S.radius, false).length - shown.length;
    body.innerHTML = head + hitHtml + cards
      + (S.openOnly && hidden ? `<button class="btn ghost" id="b-all">닫힌 곳·시간 확인 필요 ${hidden}곳 보기</button>` : '')
      + foot;
    if ($('#b-all')) $('#b-all').onclick = () => { S.openOnly = false; showList(); };
    body.querySelectorAll('[data-g]').forEach((c) => (c.onclick = () => {
      const on = $(`#kids-${c.dataset.g}`).classList.toggle('on');
      c.querySelector('.more2').textContent = on ? '접기 ›' : '펼쳐 보기 ›';
    }));
  }
  $('#b-change').onclick = () => go(S.mode === 'gps' ? 'pin' : 'pin');
  $('#c-open').onclick = () => { S.openOnly = !S.openOnly; showList(); };
  body.scrollTop = 0;
}

loadIndex();     // 첫 화면을 보는 동안 칸 목록을 미리 받아 둔다

/* 검수·시험용: ?la=37.5665&lo=126.9780[&acc=15] 로 열면 위치 허용 없이 그 자리에서 시작한다 */
(function devStart() {
  const q = new URLSearchParams(location.search);
  if (!q.has('la') || !q.has('lo')) return;
  S.gps = { la: +q.get('la'), lo: +q.get('lo'), acc: +(q.get('acc') || 15) };
  loadIndex().then(() => openPin('gps'));
})();
