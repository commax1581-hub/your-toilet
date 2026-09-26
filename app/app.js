/* 가장 가까운 화장실 — 1단계: 첫 화면 → 위치 확정(핀) → 가까운 목록
   데이터: app/data/index.json(칸 목록) + app/data/t/<행>_<열>.json(0.05도 ≈ 5km 칸)
   규칙은 docs/앱구현-시작점.md 4·5장. 지금 위치는 저장하지 않는다(화면 안에서만 쓴다).
   사용자가 스스로 담은 것(저장한 곳·최근 본 곳)만 기기 안에 남는다 — saved.js, 결정 6-28. */
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
  f: { bell: 0, acc: 0, dp: 0, kid: 0, ft: '' },   // 안심·장애인·기저귀·어린이·시설 종류
  gate: 0,                       // 역 화장실 중 "개찰구 밖만"(표 없이 들어갈 수 있는 곳) — 밖이 80%다
  index: null,
  holidays: new Set(),
  tiles: new Map(),
  groups: [],                    // 지도에 그릴 묶음
  rails: [],                     // 지도에 그릴 역(출처가 다른 별개 데이터)
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
  if (name === 'home') homeFav();
  if (name === 'saved') renderSaved();
  if (name === 'recent') renderRecent();
  syncTabs(name);
  if (name === 'search') setTimeout(() => $('#q').focus(), 60);
  if (!fromPop) {
    if (same) history.replaceState({ s: name }, '');
    else history.pushState({ s: name }, '');
  }
}
/* 하단 메뉴 — 목록·저장·최근·알아보기에서만 보인다(첫 화면·핀·검색·상세·지도에는 없다).
   상세와 지도는 '깊이 들어간 화면'이라 탭을 두면 돌아가는 길이 두 개가 되어 헷갈린다. */
const TABBED = { list: 'near', saved: 'saved', recent: 'recent', info: 'info' };
function syncTabs(name) {
  const bar = $('#tabbar');
  bar.hidden = !TABBED[name];
  bar.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.tab === TABBED[name]));
  document.body.classList.toggle('hastab', !!TABBED[name]);
}
$('#tabbar').onclick = async (e) => {
  const b = e.target.closest('button[data-tab]');
  if (!b) return;
  if (b.dataset.tab === 'near') return S.base ? showList() : go('home');
  go(b.dataset.tab);
};

history.replaceState({ s: 'home' }, '');
window.addEventListener('popstate', (e) => go((e.state && e.state.s) || 'home', true));
document.querySelectorAll('[data-go]').forEach((b) => (b.onclick = () => go(b.dataset.go)));
document.querySelectorAll('[data-back]').forEach((b) => (b.onclick = () => history.back()));
/* 키보드로도 카드를 열 수 있게 — 누를 수 있는 것은 Enter·Space로도 눌려야 한다 */
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const c = e.target.closest('[role="button"]');
  if (c) { e.preventDefault(); c.click(); }
});

/* ── 첫 화면 배경: 지금 시각(낮 06~17 · 저녁 17~20 · 밤 20~06). 어두운 모드면 밤 그림 ── */
function background(dark) {
  const h = new Date().getHours();
  const f = dark ? 'bg_night_1080.webp'
    : h >= 6 && h < 17 ? 'bg_day_blue_1080.webp' : h >= 17 && h < 20 ? 'bg_evening_1080.webp' : 'bg_night_1080.webp';
  $('#s-home').style.backgroundImage = `url(img/${f})`;
}


/* ── 보기 설정 — 어두운 모드·글씨 크기 ─────────
   기본은 기기 설정을 따름. 저장하는 것은 설정과 **사용자가 스스로 담은 것**뿐(saved.js). */
const PREF = {
  get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};

function applyPrefs() {
  const t = PREF.get('theme', 'auto'), z = PREF.get('size', 'normal');
  const dark = t === 'dark' || (t === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  if (z === 'normal') delete document.documentElement.dataset.size;
  else document.documentElement.dataset.size = z;
  document.querySelector('meta[name=theme-color]').setAttribute('content', dark ? '#0f141a' : '#4338ca');
  background(dark);                                     // 어두운 모드면 첫 화면도 밤 그림으로
  $('#seg-theme').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.v === t));
  $('#seg-size').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.v === z));
  if (map) setTimeout(() => map.relayout(), 0);
}

/** 지금 보고 있는 상세(화장실 또는 역) — 별 버튼과 '최근 본 곳'이 함께 본다 */
function markDetail(it) {
  S.cur = it;
  pushRecent(it);
  paintFav();
  setTimeout(installNudge, 1200);                       // 한 곳을 본 뒤에 조용히 한 번만 권한다
}
function paintFav() {
  const b = $('#b-fav');
  if (!b || !S.cur) return;
  const on = isFav(S.cur);
  b.classList.toggle('on', on);
  b.innerHTML = `<svg><use href="#${on ? 'i-star-on' : 'i-star'}"/></svg><span>${on ? '저장됨' : '저장'}</span>`;
}
$('#b-fav').onclick = () => { if (S.cur) { toggleFav(S.cur); paintFav(); } };

$('#b-set').onclick = () => $('#s-set').classList.add('on');
$('#b-set2').onclick = () => $('#s-set').classList.add('on');
$('#b-pre').onclick = (e) => preloadArea(e.currentTarget);
$('#b-clearall').onclick = (e) => { clearAllSaved(); e.currentTarget.textContent = '지웠습니다'; };
document.querySelectorAll('#s-set [data-close]').forEach((b) => (b.onclick = () => $('#s-set').classList.remove('on')));
$('#seg-theme').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b) { PREF.set('theme', b.dataset.v); applyPrefs(); } };
$('#seg-size').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b) { PREF.set('size', b.dataset.v); applyPrefs(); if (S.screen === 'list') showList(); } };
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (PREF.get('theme', 'auto') === 'auto') applyPrefs(); });
applyPrefs();
initMobile();                                           // 앱 안 브라우저 안내 · 홈 화면에 추가

/** 첫 화면의 저장한 곳 바로가기 — 담아 둔 자리가 있으면 위치를 잡기 전에도 바로 간다 */
function homeFav() {
  const box = $('#home-fav');
  const list = (typeof favs === 'function' ? favs() : []).filter((x) => x.k === 'p').slice(0, 3);
  box.hidden = !list.length;
  if (!list.length) return;
  box.innerHTML = list.map((x, i) => `<button class="hf" data-hf="${i}"><svg><use href="#i-star-on"/></svg>${esc(x.n)}</button>`).join('')
    + '<button class="hf more" data-go="saved">저장한 곳</button>';
  box.querySelectorAll('[data-hf]').forEach((b) => (b.onclick = () => openSaved(list[+b.dataset.hf])));
  box.querySelectorAll('[data-go]').forEach((b) => (b.onclick = () => go(b.dataset.go)));
}

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

/** 지도 칸 주소에 **기준일**을 붙인다.
    붙이지 않으면 서비스워커가 한 번 저장한 칸을 계속 쓰고, **갱신을 해도 옛 데이터가 남는다**(T28).
    기준일이 바뀌면 주소가 바뀌어 새로 받고, 서비스워커가 옛 기준일 저장본을 통째로 지운다. */
const tileUrl = (k, idx) => `data/t/${k}.json?v=${(idx && idx.date) || '0'}`;

/** 기준점이 든 칸 + 둘레 8칸 (반경이 칸보다 작아도 칸 경계에 있을 수 있다) */
async function nearby(la, lo) {
  const idx = await loadIndex();
  const r0 = Math.floor(la / TILE), c0 = Math.floor(lo / TILE), out = [];
  const jobs = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      const k = `${r0 + dr}_${c0 + dc}`;
      if (!idx.tiles[k]) continue;
      if (!S.tiles.has(k)) S.tiles.set(k, fetch(tileUrl(k, idx)).then((r) => r.json()));
      jobs.push(S.tiles.get(k).then((recs) => out.push(...recs)));
    }
  }
  await Promise.all(jobs);
  return out;
}

/** 작은 반경용 — 점이 든 칸만 읽고, 칸 경계에 가까울 때만 옆 칸을 더 읽는다(검색 결과 12개 × 9칸을 막는다) */
async function nearbySmall(la, lo, meters) {
  const idx = await loadIndex();
  const r0 = Math.floor(la / TILE), c0 = Math.floor(lo / TILE);
  const fy = la / TILE - r0, fx = lo / TILE - c0;
  const dy = meters / 111000 / TILE, dx = meters / (111000 * Math.cos(la * Math.PI / 180)) / TILE;
  const rows = [r0], cols = [c0];
  if (fy < dy) rows.push(r0 - 1);
  if (fy > 1 - dy) rows.push(r0 + 1);
  if (fx < dx) cols.push(c0 - 1);
  if (fx > 1 - dx) cols.push(c0 + 1);
  const out = [], jobs = [];
  for (const r of rows) for (const c of cols) {
    const k = `${r}_${c}`;
    if (!idx.tiles[k]) continue;
    if (!S.tiles.has(k)) S.tiles.set(k, fetch(tileUrl(k, idx)).then((x) => x.json()));
    jobs.push(S.tiles.get(k).then((recs) => out.push(...recs)));
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
  if (S.query && distM(S.query.la, S.query.lo, la, lo) > 30) S.query = null;   // 핀을 옮기면 찾아온 장소가 아니다
  const name = S.query ? S.query.name : '';
  S.base = { la, lo, addr: '이 위치', name };
  $('#pin-sub').textContent = S.mode === 'gps' && S.gps
    ? `내 위치에서 ${Math.round(distM(S.gps.la, S.gps.lo, la, lo))}m · 오차 약 ${Math.round(S.gps.acc)}m`
    : '핀을 옮기면 주소가 바뀌어요';
  geocoder.coord2Address(lo, la, (res, st) => {
    if (seq !== addrSeq) return;                                  // 지도를 계속 움직인 경우 늦게 온 답은 버린다
    if (st !== kakao.maps.services.Status.OK || !res.length) { $('#pin-addr').textContent = '주소를 찾지 못했어요'; return; }
    const r = res[0], a = (r.road_address && r.road_address.address_name) || (r.address && r.address.address_name) || '';
    const bn = (r.road_address && r.road_address.building_name) || '';
    $('#pin-addr').textContent = name || bn || (a ? `${a} 근처` : '주소를 찾지 못했어요');
    if (!name && bn && a) $('#pin-sub').textContent = `${shortAddr(a)} · ${$('#pin-sub').textContent}`;
    $('#pin-sub2') && ($('#pin-sub2').textContent = '');
    $('#pin-q').textContent = name || (a ? shortAddr(a) : '주소 · 건물 이름으로 찾기');
    S.base = { la, lo, addr: a || '이 위치', name: name || bn };
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
  pushRecent({ k: 'p', n: p.name, addr: p.addr || p.name, la: p.la, lo: p.lo });   // 같은 주소를 또 치지 않게
  openPin('other', p);
}

/** 검색 제안 맨 위의 역 — 역 이름으로 찾는 사람은 대개 그 역에서 화장실을 찾는 사람이다.
    카카오 결과를 고른 뒤 목록에서 만나게 하지 말고, **치는 순간 보여 준다.** */
function railSug(q) {
  const key = nameCore(q);
  if (!RAIL || key.length < 2) return [];
  return RAIL.s.filter((st) => nameCore(`${st.n}역`).includes(key)).slice(0, 3);
}

function showSug(list, q) {
  const box = $('#sug');
  const rs = railSug(q);
  const rsHtml = rs.map((st, i) => `<button class="sug rail" data-r="${i}">
      <b><span class="ln">${esc(lineLabel(st))}</span>${esc(st.n)}역</b>
      <span>${esc(st.op)} · 역 안 ${st.t.length}곳</span>
      <span class="wc on"><svg class="ic"><use href="#i-train"/></svg>${esc(st.src)} 제공</span></button>`).join('');
  if (!list.length) {
    box.innerHTML = rsHtml + `<div class="note"><b>'${esc(q)}'로 찾은 곳이 없어요</b><br>
      건물·역·공원 이름이나 <b>도로명 주소</b>로 찾아 보세요. 예) 서울역, 여의도 한강공원, 세종대로 110</div>`;
    bindRailSug(box, rs);
    return;
  }
  box.innerHTML = rsHtml + list.map((p, i) => `<button class="sug" data-i="${i}"><b>${esc(p.name)}</b>
    <span>${p.cat ? `${esc(p.cat)} · ` : ''}${esc(p.addr)}</span>
    <span class="wc" id="wc-${i}">화장실 확인 중…</span></button>`).join('');
  box.querySelectorAll('.sug[data-i]').forEach((b) => (b.onclick = () => pickPlace(list[+b.dataset.i])));
  bindRailSug(box, rs);
  markToilets(list);                                   // 결과를 먼저 띄우고, 화장실 정보는 뒤이어 채운다
}

/** 업종 이름 — `가정,생활 > 백화점 > 롯데백화점`처럼 끝이 브랜드일 때가 많아 한 칸 앞(종류)을 쓴다 */
/** 제안에서 역을 고르면 그 역을 기준점으로 잡고 상세까지 바로 연다 */
function bindRailSug(box, rs) {
  box.querySelectorAll('.sug[data-r]').forEach((b) => (b.onclick = async () => {
    const st = rs[+b.dataset.r];
    S.mode = 'other';
    S.base = { la: st.la, lo: st.lo, addr: `${lineLabel(st)} ${st.n}역`, name: `${st.n}역` };
    S.query = { name: `${st.n}역`, la: st.la, lo: st.lo };
    pushRecent({ k: 'r', n: `${st.n}역`, la: st.la, lo: st.lo, st });
    await showList();
  }));
}

function catName(d) {
  if (d.category_group_name) return d.category_group_name;
  const p = String(d.category_name || '').split('>').map((x) => x.trim()).filter(Boolean);
  return p.length >= 3 ? p[p.length - 2] : (p.pop() || '');
}

/** 검색 결과마다 화장실을 붙인다 — **그 시설의 것**과 **그냥 가까운 것**을 구분해서.
    (구분하지 않으면 "있다"고 했다가 고른 뒤 "없다"고 하는 모순이 생긴다) */
async function markToilets(list) {
  await Promise.all(list.map(async (p, i) => {
    const el = $(`#wc-${i}`);
    if (!el) return;
    try {
      const recs = await nearbySmall(p.la, p.lo, 220);
      const near = recs.map((r) => ({ r, m: distM(p.la, p.lo, r.la, r.lo) })).filter((x) => x.m <= 200).sort((a, b) => a.m - b.m);
      const b = nameCore(p.name);
      const mine = near.filter((x) => {                 // 이름이 그 시설을 가리키는 것만 "이 시설의 화장실"
        const aName = nameCore(x.r.n);
        if (x.m > 150 || aName.length < 2 || b.length < 2) return false;
        if (aName.includes(b)) return !kindDiffers(aName, b);
        return b.includes(aName) && aName.length >= 4 && !kindDiffers(b, aName);
      });
      if (mine.length) {
        el.className = 'wc yes';
        el.innerHTML = `<svg class="ic"><use href="#i-wc"/></svg>${esc(mine[0].r.n)}${mine.length > 1 ? ` 외 ${mine.length - 1}곳` : ''}`;
      } else if (near.length) {
        el.className = 'wc near';
        el.textContent = `이 시설에는 없음 · 가까운 곳 ${Math.round(near[0].m)}m (${near[0].r.n})`;
      } else {
        el.className = 'wc none';
        el.textContent = '200m 안에 등록된 화장실 없음';
      }
    } catch (e) { el.textContent = ''; }
  }));
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
      done(data.slice(0, 12).map((d) => ({ name: d.place_name, addr: d.road_address_name || d.address_name, la: +d.y, lo: +d.x,
        cat: catName(d) })));                       // 업종을 함께 보여 준다(같은 주소에 여러 가게)
      return;
    }
    geocoder.addressSearch(q, (ad, st2) => {                    // 이름으로 못 찾으면 주소로(도로명·지번)
      done(st2 === kakao.maps.services.Status.OK
        ? ad.slice(0, 12).map((d) => ({
          name: (d.road_address && d.road_address.building_name) || d.address_name,   // 건물명이 있으면 이름으로
          addr: (d.road_address && d.road_address.address_name) || d.address_name,
          cat: (d.road_address && d.road_address.building_name) ? '건물' : '주소',
          la: +d.y, lo: +d.x }))
        : []);
    });
  }, { size: 12 });
}

/* 휴대폰 자판의 '검색'(돋보기)으로 보낼 때 **글자가 겹쳐 적히는** 일이 있었다 — '서해구' → '서해구서해구'(T34).
   한글 입력기가 아직 조립 중인 글자를 갖고 있는데 `blur()`로 입력칸을 떠나면, 입력기가 그 글자를 **한 번 더 확정해**
   입력칸에 붙인다(안드로이드 크롬). → 보낼 값을 **먼저 붙잡고**, 떠난 뒤에 입력칸을 그 값으로 되돌린다.
   입력기가 뒤늦게 붙이는 경우까지 있어 다음 차례(setTimeout 0)에 한 번 더 본다. */
$('#f-search').onsubmit = (e) => {
  e.preventDefault();
  const q = $('#q').value;
  $('#q').blur();
  $('#q').value = q;
  setTimeout(() => { if ($('#q').value !== q) $('#q').value = q; }, 0);
  doSearch(q);
};
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

/* ── 거르기(필터) ───────────────────────────
   급할 때 필요한 조건만 남겼다: 안심(비상벨)·장애인·기저귀·어린이 + 시설 종류.
   조건은 "있는 것만 남기기"다 — 데이터에 없다고 없는 것은 아니므로(ni) 조건을 켜면 표기가 있는 곳만 보인다. */
const FTYPES = ['공원', '역', '터미널', '관공서', '공공시설', '주유소', '시장·상가', '주차장·쉼터', '문화·관광', '체육', '병원·복지', '산', '바다', '하천', '대학', '종교', '민간시설'];

function passFilter(r) {
  const f = S.f;
  if (f.bell && r.bl !== 1) return false;
  if (f.acc && (r.x || [0, 0])[0] + (r.x || [0, 0])[1] <= 0) return false;
  if (f.dp && r.dp !== 1) return false;
  if (f.kid && (r.c || [0, 0])[0] + (r.c || [0, 0])[1] <= 0) return false;
  if (f.ft && r.ft !== f.ft) return false;
  return true;
}
const filterOn = () => !!(S.f.bell || S.f.acc || S.f.dp || S.f.kid || S.f.ft || S.gate);

/** 역 카드도 같은 잣대로 거른다.
    다만 **국가철도공단은 시설 정보를 주지 않는다** — 정보가 없는 것을 "없음"으로 읽어 지우면 안 되지만,
    "기저귀 있는 곳만"을 고른 사람에게 알 수 없는 곳을 섞어 보여 주는 것도 답이 아니다 → **거르는 중에는 뺀다.**
    종류 필터(공중·개방·간이·이동)는 역 화장실에 해당하는 값이 없으므로 켜져 있으면 뺀다. */
function passRail(st, now) {
  if (S.openOnly && !['open', 'likely'].includes(railState(st, now).k)) return false;
  if (S.gate && st.t.every((x) => x.g)) return false;    // "개찰구 밖만" — 밖에 한 곳도 없으면 뺀다
  if (S.f.ft) return S.f.ft === '역';                    // 종류를 '역'으로 고르면 **역이 답이다**(T27)
  if (!(S.f.bell || S.f.acc || S.f.dp || S.f.kid)) return true;
  return st.t.some((x) => x.m !== undefined
    && (!S.f.bell || x.bl === 1)
    && (!S.f.acc || x.ac[0] + x.ac[1] > 0)
    && (!S.f.dp || x.dp[0] + x.dp[1] > 0)
    && (!S.f.kid || x.ch[0] + x.ch[1] > 0));
}
const clearFilter = () => { S.f = { bell: 0, acc: 0, dp: 0, kid: 0, ft: '' }; S.gate = 0; };

function chipRows() {
  const c = (on, label, attr) => `<span class="chip${on ? ' on' : ''}" ${attr}>${label}</span>`;
  return `<div class="chips">${c(S.openOnly, '지금 열림', 'id="c-open"')}
      ${[300, 500, 1000].map((r) => c(S.radius === r, r < 1000 ? `${r}m` : '1km', `data-r="${r}"`)).join('')}</div>
    ${S.railsNear ? `<div class="chips">${c(S.gate, '개찰구 밖만', 'id="c-gate"')}<span class="chiphint">표 없이 들어갈 수 있는 역 화장실</span></div>` : ''}
    <div class="chips">${c(S.f.bell, '안심', 'data-f="bell"')}${c(S.f.acc, '장애인', 'data-f="acc"')}
      ${c(S.f.dp, '기저귀', 'data-f="dp"')}${c(S.f.kid, '어린이', 'data-f="kid"')}
      ${filterOn() ? '<span class="chip clear" id="c-clear">거르기 끄기</span>' : ''}</div>
    <div class="chips">${c(!S.f.ft, '모든 종류', 'data-ft=""')}${FTYPES.map((t) => c(S.f.ft === t, t, `data-ft="${t}"`)).join('')}</div>`;
}

/* ── 검색한 장소의 화장실 먼저 ─────────────
   이름으로 찾아온 사람에게는 그 장소가 답이다 — 묶음 규칙과 상관없이 맨 위에 따로 보여 준다.
   비교는 군더더기 말을 뺀 뒤 서로 포함하는지로 본다(같은 이름의 다른 지역을 집지 않게 300m 안만). */
const nameCore = (s) => String(s || '').replace(/\(.*?\)/g, '')
  .replace(/특별자치시|광역시|특별시/g, '시').replace(/특별자치도/g, '도')   // 서울특별시청 = 서울시청
  .replace(/공중화장실|개방화장실|간이화장실|화장실|주차장|공영|본점|점포/g, '')
  .replace(/[\s·,()\[\]{}\-_]/g, '');

/* 대형 민간시설 — 공공데이터에 없을 때 "신고된 곳만 들어온다"고 설명해야 하는 종류.
   공원·역처럼 공공시설이면 그 설명이 틀리므로, 이름으로 갈라서 말한다. */
const PRIVATE_BIG = /백화점|마트|아울렛|쇼핑|몰$|플라자|프라자|타워|빌딩|스퀘어|면세점|시네마|영화관|호텔|리조트|웨딩|골프|백화/;
/* 역·터미널 — 화장실은 반드시 있지만 운영기관(코레일·교통공사)이 관리해 지자체 공중화장실 대장에 빠지는 일이 잦다.
   등록된 역 1,052곳뿐이고, 같은 도시 안에서도 역마다 다르다(대구: 상인역 있음 · 동대구역·안심역 없음). */
const TRANSPORT = /역$|역\s|터미널|공항|정류장|환승센터|휴게소|철도|선착장|여객선/;

/* 종류어 — 이름이 포함돼도 덧붙은 말이 "다른 종류"면 다른 시설이다.
   (착한가격·화장실 모듈: 포함 + 종류 검사. 예: 동대구역 ≠ 동대구역치안센터, 계산역 ≠ 계산역아파트) */
const KIND = /치안센터|파출소|지구대|소방서|안전센터|아파트|빌라|오피스텔|주택|학교|대학교|유치원|어린이집|병원|의원|약국|주차장|공원|시장|상가|우체국|주민센터|행정복지센터|도서관|미술관|박물관|경기장|체육관|교회|성당|사찰|주유소|충전소|은행|호텔|모텔|카페|식당|편의점/g;

/** 긴 이름에서 짧은 이름을 뺀 나머지에 "다른 종류"가 있으면 서로 다른 시설 */
function kindDiffers(longer, shorter) {
  const rest = longer.split(shorter).join('');
  const inShort = shorter.match(KIND) || [];
  return (rest.match(KIND) || []).some((k) => !inShort.includes(k));
}

function isQueryHit(rec, m) {
  if (!S.query || m > 300) return false;
  const a = nameCore(rec.n), b = nameCore(S.query.name);
  if (a.length < 2 || b.length < 2) return false;
  if (a.includes(b)) return !kindDiffers(a, b);      // 화장실 이름이 검색한 이름을 품는다 → 확실(서울역 → 서울역(4호선))
  return b.includes(a) && a.length >= 4 && !kindDiffers(b, a);   // 반대 방향은 4자 이상일 때만
}                                                    // (T19: '상인공영주차장 화장실'의 '상인'이 '롯데백화점 상인점'에 들어가 오답)

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
  return `<div class="card${shut ? ' shut' : ''}" data-id="${rec.id}" data-m="${Math.round(m)}" role="button" tabindex="0">
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
async function showList(quiet) {
  if (!quiet) go('list');
  const body = $('#list-body');
  body.innerHTML = '<div class="loading">가까운 곳을 찾는 중…</div>';
  const now = new Date(), base = S.base;
  const [recs] = await Promise.all([nearby(base.la, base.lo), loadRail()]);
  const idx = S.index;
  // 기준일이 둘이다(지자체 자료·역 자료) — 하나만 적으면 역 정보의 기준일이 감춰진다

  // 거리 → 같은 좌표끼리 묶기
  const withD = recs.map((r) => ({ r, m: distM(base.la, base.lo, r.la, r.lo) })).sort((a, b) => a.m - b.m);
  const inR = (radius, openOnly, noFilter) => withD.filter((x) => x.m <= radius
    && (noFilter || passFilter(x.r))
    && (!openOnly || ['open', 'soon'].includes(cardState(x.r, now).k)));

  // 역 안 화장실 — 출처가 다른 별개 데이터를 **거리순 그대로** 섞는다(먼저 거리, 그다음 성격 · 6-27)
  S.railsNear = railNear(base.la, base.lo, S.radius).length > 0;   // 칩("개찰구 밖만")을 보일지 결정
  // 머리글은 **짧게**(좁은 화면에서 세 줄로 접힌다). 기준일이 둘이라는 것은 맨 아래와 알아보기에서 밝힌다
  $('#list-s').textContent = `${hhmm(now)} 기준 · 자료 ${idx.date}`;
  const rails = railNear(base.la, base.lo, S.radius).filter((x) => passRail(x.st, now));
  /* 역 이름으로 찾아온 사람에게 "역은 공공데이터에 없어요"라고 말하면 안 된다 —
     이제 역 안 화장실을 갖고 있다. 그 역이 가까이 잡히면 안내 문구를 바꾼다(T21의 교훈: 두 화면이 다른 말을 하면 안 된다). */
  /* 겹침은 **표시만** 한다(규약 4-1). 같은 역이 지자체 목록에도 있으면 서로 가리키게만 하고 값은 섞지 않는다 —
     섞으면 틀렸을 때 누구에게 알려야 하는지 알 수 없다. */
  for (const x of rails) {
    const key = nameCore(`${x.st.n}역`);
    x.also = key && withD.some((y) => y.m <= 250 && nameCore(y.r.n).includes(key));
    // 같은 이름의 역이 목록에 둘 이상이면(노선이 다른 것) 중복으로 오해하지 않게 꼬리표를 단다
    x.sameName = rails.filter((y) => y.st.n === x.st.n).length > 1;
  }
  const railHit = S.query && rails.find((x) => {
    if (x.m > 250) return false;
    const a = nameCore(S.query.name), b = nameCore(`${x.st.n}역`);
    return a && b && (a.includes(b) || b.includes(a));
  });

  // 검색한 장소의 화장실은 "지금 열림"과 상관없이 맨 위에(찾아온 목적지라 닫혀 있어도 알려 줘야 한다)
  const hits = (S.query ? withD.filter((x) => isQueryHit(x.r, x.m)) : []).slice(0, 6);   // 너무 많으면 목록이 밀린다
  const hitIds = new Set(hits.map((x) => x.r.id));
  let shown = inR(S.radius, S.openOnly).filter((x) => !hitIds.has(x.r.id));
  const near1 = withD[0];
  const hitHtml = hits.length
    ? `<div class="secline">찾으신 곳 · ${esc(S.query.name)}</div>`
      + hits.map((x) => cardHtml(x.r, x.m, now)).join('')
      + `<div class="secline">둘레 ${S.radius < 1000 ? `${S.radius}m` : '1km'} 안</div>`
    : (S.query && railHit
      ? `<div class="nohit"><b>${esc(S.query.name)}의 화장실은 아래 <span class="ln">${esc(lineLabel(railHit.st))}</span> 상자에 있어요</b>
           역 화장실은 <b>지자체가 아니라 철도 운영기관</b>(${esc(railHit.st.src)})이 관리해 <b>따로</b> 보여 드립니다.</div>`
      : S.query
      ? `<div class="nohit">${PRIVATE_BIG.test(S.query.name)
            ? `<b>${esc(S.query.name)}에는 등록된 화장실이 없어요</b>
               백화점·마트 같은 <b>민간 건물</b>은 지자체에 신고된 곳만 공공데이터에 들어옵니다. 실제로는 있을 수 있으니 <b>안내 데스크에 물어보세요.</b>`
            : TRANSPORT.test(S.query.name)
              ? `<b>${esc(S.query.name)}은(는) 공공데이터에 없어요</b>
                 역·터미널 화장실은 <b>철도 운영기관이 관리</b>해 지자체 공중화장실 목록에서 빠지는 일이 잦습니다.
                 <b>역 안에는 대개 화장실이 있으니</b> 역 안내도를 봐 주세요.`
              : `<b>'${esc(S.query.name)}' 이름으로 등록된 곳은 없어요</b>
                 그 안에 있는 화장실이 <b>다른 이름으로</b> 등록돼 있을 수 있습니다 — 아래 목록을 봐 주세요.`}
          ${near1 ? `<br>가장 가까운 곳은 <b>${near1.m < 1000 ? `${Math.round(near1.m)}m` : `${(near1.m / 1000).toFixed(1)}km`}</b> 앞입니다.` : ''}</div>`
      : '');
  const forMap = hits.concat(shown);                     // 지도는 "찾으신 곳"까지 한 덩어리로 본다
  const gmap = new Map();
  for (const x of forMap) {
    const key = `${x.r.la},${x.r.lo}`;
    if (!gmap.has(key)) gmap.set(key, { m: x.m, list: [] });
    gmap.get(key).list.push(x.r);
  }
  S.groups = [...gmap.values()];
  S.rails = rails;                                       // 지도도 같은 목록을 본다

  const head = `<div class="basebar"><b><svg class="ic"><use href="#i-pin"/></svg>${esc(base.name || shortAddr(base.addr))}<span class="r">${base.name ? `${esc(shortAddr(base.addr))} · ` : ''}이 위치에서 ${S.radius < 1000 ? `${S.radius}m` : '1km'} 안</span></b><button id="b-change">위치 바꾸기</button></div>
    ${chipRows()}`;
  const foot = `<div class="foot">출처 행정안전부 공중화장실정보 · 기준일 ${idx.date}
    ${S.railsNear && RAIL && RAIL.date ? `<br>역 안 화장실 — 국가철도공단 ${RAIL.date['국가철도공단']} · 서울교통공사 ${RAIL.date['서울교통공사']}` : ''}<br>
    실제와 다를 수 있습니다. 시설 상태·개방 시간은 <b>원천데이터 관리기관</b>에 확인해 주세요.<br>
    <a href="https://www.data.go.kr/tcs/opd/ndm/view.do" target="_blank" rel="noopener">공공데이터 오류 신고</a>
    · <button class="linklike" data-go2="info">알아보기</button></div>`;

  if (!shown.length && !rails.length) {
    const wider = [1000, 2000, 5000].find((r) => r > S.radius && inR(r, S.openOnly).length);
    const all = inR(S.radius, false).length;
    body.innerHTML = head + hitHtml + `<div class="empty"><svg><use href="#i-pin"/></svg>
        <b>${S.radius < 1000 ? `${S.radius}m` : `${S.radius / 1000}km`} 안에 ${S.openOnly ? '지금 열린 곳이' : '화장실이'} 없어요</b>
        <div class="sub">${wider ? `${wider < 1000 ? `${wider}m` : `${wider / 1000}km`} 안에 ${inR(wider, S.openOnly).length}곳` : '가까운 곳에 등록된 화장실이 없습니다'}${S.openOnly && all ? ` · 닫힘·시간 확인 ${all - shown.length}곳` : ''}</div>
      </div>
      ${wider ? `<button class="btn main" id="b-wide">${wider < 1000 ? `${wider}m` : `${wider / 1000}km`}까지 넓혀 보기</button>` : ''}
      ${filterOn() ? `<button class="btn ghost" style="margin-top:8px" id="b-clear2">거르기 끄면 ${inR(S.radius, S.openOnly, true).length}곳</button>` : ''}
      ${S.openOnly && all ? '<button class="btn ghost" style="margin-top:8px" id="b-all">닫힌 곳·시간 확인 필요 포함</button>' : ''}` + foot;
    const byId0 = new Map(withD.map((x) => [x.r.id, x]));
    body.querySelectorAll('.card[data-id]').forEach((c) => (c.onclick = () => {
      const x = byId0.get(c.dataset.id);
      if (x) openDetail(x.r, x.m);
    }));
    if (wider) $('#b-wide').onclick = () => { S.radius = wider; showList(); };
    if ($('#b-all')) $('#b-all').onclick = () => { S.openOnly = false; showList(); };
  } else {
    const groups = new Map();
    for (const x of shown) {
      const key = `${x.r.la},${x.r.lo}`;
      if (!groups.has(key)) groups.set(key, { m: x.m, list: [] });
      groups.get(key).list.push(x.r);
    }
    const cards = [...groups.values()].map((g, i) => ({ m: g.m,
      html: g.list.length > 1 ? groupHtml(g.list, g.m, now, i) : cardHtml(g.list[0], g.m, now) }))
      .concat(rails.map((x, i) => ({ m: x.m, html: railCard(x.st, x.m, now, i, x.also, x.sameName) })))
      .sort((a, b) => a.m - b.m).map((x) => x.html).join('');
    const hidden = inR(S.radius, false).length - shown.length;
    body.innerHTML = head + hitHtml + cards
      + (S.openOnly && hidden ? `<button class="btn ghost" id="b-all">닫힌 곳·시간 확인 필요 ${hidden}곳 보기</button>` : '')
      + foot;
    if ($('#b-all')) $('#b-all').onclick = () => { S.openOnly = false; showList(); };
    // 카드를 누르면 상세로 (묶음 카드는 펼치기)
    const byId = new Map(withD.map((x) => [x.r.id, x]));
    body.querySelectorAll('.card[data-id]').forEach((c) => (c.onclick = () => {
      const x = byId.get(c.dataset.id);
      if (x) openDetail(x.r, x.m);
    }));
    body.querySelectorAll('[data-rail]').forEach((c) => (c.onclick = () => {
      const x = rails[+c.dataset.rail];
      if (x) openRailDetail(x.st, x.m);
    }));
    body.querySelectorAll('[data-g]').forEach((c) => (c.onclick = () => {
      const on = $(`#kids-${c.dataset.g}`).classList.toggle('on');
      c.querySelector('.more2').textContent = on ? '접기 ›' : '펼쳐 보기 ›';
    }));
  }
  body.querySelectorAll('[data-go2]').forEach((b) => (b.onclick = () => go(b.dataset.go2)));
  $('#b-change').onclick = () => go(S.mode === 'gps' ? 'pin' : 'pin');
  $('#c-open').onclick = () => { S.openOnly = !S.openOnly; showList(); };
  if ($('#c-gate')) $('#c-gate').onclick = () => { S.gate = S.gate ? 0 : 1; showList(); };
  body.querySelectorAll('.chip[data-r]').forEach((c) => (c.onclick = () => { S.radius = +c.dataset.r; showList(); }));   // 목록에서 바로 반경 바꾸기
  body.querySelectorAll('.chip[data-f]').forEach((c) => (c.onclick = () => { S.f[c.dataset.f] = S.f[c.dataset.f] ? 0 : 1; showList(); }));
  body.querySelectorAll('.chip[data-ft]').forEach((c) => (c.onclick = () => { S.f.ft = c.dataset.ft; showList(); }));
  if ($('#c-clear')) $('#c-clear').onclick = () => { clearFilter(); showList(); };
  if ($('#b-clear2')) $('#b-clear2').onclick = () => { clearFilter(); showList(); };
  body.scrollTop = 0;
}

/* 시각이 흐르면 화면도 따라가야 한다 — 저녁이 됐는데 낮 배경이거나, 닫힌 곳이 아직 "열림"이면 안 된다.
   5분마다·앱으로 돌아올 때 다시 그린다(목록은 보던 자리를 지킨다). */
function refreshByTime() {
  if (document.hidden) return;
  background(document.documentElement.dataset.theme === 'dark');
  if (S.screen === 'list' && S.base) {
    const b = $('#list-body'), y = b.scrollTop;
    showList(true).then(() => { b.scrollTop = y; });
  } else if (S.screen === 'map' && S.base && typeof openMap === 'function') {
    showList(true).then(() => openMap());
  }
}
setInterval(refreshByTime, 5 * 60 * 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshByTime(); });

/* 오프라인 준비 — 한 번 본 화면·지도 칸을 저장해 둔다(자세한 규칙은 sw.js) */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}

Promise.all([loadIndex(), loadRail()]).then(([idx, rail]) => {   // 알아보기 머리에 지금 데이터의 수치를 적는다
  const el = $('#info-s');
  if (el) el.textContent = `화장실 ${idx.toilets.toLocaleString()}곳 · 기준일 ${idx.date}`
    + (rail && rail.count ? ` · 역 ${rail.count.toLocaleString()}곳 ${rail.date['국가철도공단']}` : '');
});

loadIndex();     // 첫 화면을 보는 동안 칸 목록을 미리 받아 둔다

/* 검수·시험용: ?la=37.5665&lo=126.9780[&acc=15] 로 열면 위치 허용 없이 그 자리에서 시작한다 */
(function devStart() {
  const q = new URLSearchParams(location.search);
  if (!q.has('la') || !q.has('lo')) return;
  S.gps = { la: +q.get('la'), lo: +q.get('lo'), acc: +(q.get('acc') || 15) };
  loadIndex().then(() => openPin('gps'));
})();
