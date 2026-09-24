/* 지도로 보기 — 목록과 같은 결과를 지도에 놓는다.
   핀은 구분(공중·개방)으로 색을, 같은 자리는 숫자를, 닫힌 곳은 흐리게. 아래 카드와 핀이 서로 연동된다.
   지도를 옮기면 "이 지역에서 다시 찾기"가 뜬다(마음대로 다시 찾지 않는다 — 사용자가 누를 때만). */
'use strict';

let map2 = null, overlays = [], baseDot = null, cardIdx = 0, mapGroups = [], ignoreMove = true;

function pinHtml(g, i, now) {
  const open = g.list.some((r) => ['open', 'soon'].includes(cardState(r, now).k));
  const k = KINDS[g.list[0].t] || KINDS[0];
  const label = g.list.length > 1 ? g.list.length : '';
  return `<div class="mpin ${k.c}${open ? '' : ' shut'}${i === cardIdx ? ' on' : ''}" data-i="${i}">
      <svg><use href="${k.i}"/></svg>${label ? `<b>${label}</b>` : ''}</div>`;
}

/** 지도 화면 열기 — 목록이 만든 묶음(S.groups)을 그대로 쓴다 */
async function openMap() {
  go('map');
  try {
    await kakaoReady();
  } catch (e) {
    $('#mapcards').innerHTML = '<div class="mcard"><b>지도를 불러오지 못했어요</b><span>목록으로 보실 수 있습니다.</span></div>';
    return;
  }
  const now = new Date(), base = S.base;
  mapGroups = S.groups || [];
  cardIdx = 0;
  const center = new kakao.maps.LatLng(base.la, base.lo);
  if (!map2) {
    map2 = new kakao.maps.Map($('#map2'), { center, level: 4 });
    // 우리가 지도를 움직인 것(처음 맞추기·카드 넘김)과 사용자가 움직인 것을 가른다
    const moved = () => { if (!ignoreMove) $('#b-again').hidden = false; };
    kakao.maps.event.addListener(map2, 'dragend', moved);
    kakao.maps.event.addListener(map2, 'zoom_changed', moved);
  } else {
    map2.relayout();
    map2.setCenter(center);
  }
  $('#map-s').textContent = `${hhmm(now)} 기준 · ${mapGroups.length}곳`;
  $('#b-again').hidden = true;

  overlays.forEach((o) => o.setMap(null));
  overlays = [];
  if (baseDot) baseDot.setMap(null);
  baseDot = new kakao.maps.Circle({ center, radius: 6, strokeWeight: 3, strokeColor: '#fff', fillColor: '#2563eb', fillOpacity: 1 });
  baseDot.setMap(map2);

  const bounds = new kakao.maps.LatLngBounds();
  bounds.extend(center);
  mapGroups.forEach((g, i) => {
    const pos = new kakao.maps.LatLng(g.list[0].la, g.list[0].lo);
    const el = document.createElement('div');
    el.innerHTML = pinHtml(g, i, now);
    el.firstElementChild.onclick = () => selectCard(i, true);
    const ov = new kakao.maps.CustomOverlay({ position: pos, content: el, yAnchor: 1, clickable: true });
    ov.setMap(map2);
    overlays.push(ov);
    bounds.extend(pos);
  });
  ignoreMove = true;
  if (mapGroups.length) map2.setBounds(bounds, 60, 60, 60, 220);
  setTimeout(() => { ignoreMove = false; $('#b-again').hidden = true; }, 700);

  // 아래 카드 — 좌우로 넘기면 지도가 따라간다
  $('#mapcards').innerHTML = mapGroups.map((g, i) => {
    const r = g.list[0], k = KINDS[r.t] || KINDS[0], st = statePill(r, now);
    const name = g.list.length > 1 ? `${groupName(g.list)}` : r.n;
    return `<div class="mcard" data-i="${i}">
        <div class="h"><b>${esc(name)}</b><span class="d">${g.m < 1000 ? `${Math.round(g.m)}m` : `${(g.m / 1000).toFixed(1)}km`}</span></div>
        <div class="meta"><span class="pill ${k.c}"><svg><use href="${k.i}"/></svg>${k.l}</span>${st.html}</div>
        <div class="a">${esc(shortAddr(r.a))}</div>
      </div>`;
  }).join('');
  $('#mapcards').querySelectorAll('.mcard').forEach((c) => (c.onclick = () => {
    const g = mapGroups[+c.dataset.i];
    openDetail(g.list[0], g.m);
  }));
  $('#mapcards').onscroll = () => {                       // 넘긴 카드에 맞춰 지도를 움직인다
    const box = $('#mapcards'), i = Math.round(box.scrollLeft / (box.firstElementChild.offsetWidth + 10));
    if (i !== cardIdx && mapGroups[i]) selectCard(i, false);
  };
}

/** 카드·핀 고르기 — 핀에서 누르면 카드를 그리로, 카드를 넘기면 지도를 그리로 */
function selectCard(i, fromPin) {
  cardIdx = i;
  const g = mapGroups[i];
  if (!g) return;
  overlays.forEach((o, j) => {
    const el = o.getContent().firstElementChild;
    if (el) el.classList.toggle('on', j === i);
  });
  if (fromPin) {
    const box = $('#mapcards');
    box.scrollTo({ left: i * (box.firstElementChild.offsetWidth + 10), behavior: 'smooth' });
  }
  ignoreMove = true;                                      // 카드를 넘겨서 움직인 것은 "지도를 옮겼다"가 아니다
  map2.panTo(new kakao.maps.LatLng(g.list[0].la, g.list[0].lo));
  setTimeout(() => { ignoreMove = false; }, 600);
}

$('#b-map').onclick = () => openMap();
$('#b-list').onclick = () => go('list');
$('#b-recenter').onclick = () => {
  if (!map2) return;
  ignoreMove = true;
  map2.panTo(new kakao.maps.LatLng(S.base.la, S.base.lo));
  setTimeout(() => { ignoreMove = false; $('#b-again').hidden = true; }, 600);
};
$('#b-again').onclick = async () => {                      // 지도를 옮긴 자리에서 다시 찾기
  const c = map2.getCenter();
  S.query = null;
  S.base = { la: c.getLat(), lo: c.getLng(), addr: '지도에서 고른 자리', name: '' };
  $('#b-again').hidden = true;
  geocoder.coord2Address(c.getLng(), c.getLat(), (res, st) => {
    if (st === kakao.maps.services.Status.OK && res.length) {
      const r = res[0];
      S.base.addr = (r.road_address && r.road_address.address_name) || (r.address && r.address.address_name) || '이 위치';
      S.base.name = (r.road_address && r.road_address.building_name) || '';
    }
  });
  await showList(true);                                    // 목록을 다시 만들고(화면은 지도에 머문다)
  openMap();
};
