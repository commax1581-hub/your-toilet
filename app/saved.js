/* 저장한 곳 · 최근 본 곳 — **이 휴대폰 안에만** 남는다.
   지금까지 규칙은 "설정만 저장한다"였고, 이것이 그 예외다(결정 6-28).
   조건 셋: ① 기기 밖으로 보내지 않는다 ② 한 번에 지울 수 있다 ③ 화면에 그렇게 밝힌다.
   저장 못 하는 상황(사생활 보호 모드·저장 공간 꽉 참)에서도 앱이 멈추면 안 되므로 모든 읽기·쓰기를 감싼다. */
'use strict';

const MAX_RECENT = 20;

const BOX = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || '[]'); } catch (e) { return []; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
};

/** 무엇이든 한 줄로 가리키는 열쇠 — 화장실 `t:번호` · 역 `r:기관|노선|역` · 자리 `p:좌표` */
function keyOf(it) {
  if (it.k === 't') return `t:${it.rec.id}`;
  if (it.k === 'r') return `r:${it.st.op}|${it.st.ln}|${it.st.n}`;
  return `p:${it.la.toFixed(5)},${it.lo.toFixed(5)}`;
}

const favs = () => BOX.get('fav');
const isFav = (it) => favs().some((x) => x.key === keyOf(it));

function toggleFav(it) {
  const key = keyOf(it), list = favs();
  const at = list.findIndex((x) => x.key === key);
  if (at >= 0) list.splice(at, 1);
  else list.unshift({ ...it, key, ts: Date.now() });
  BOX.set('fav', list);
  return at < 0;                                        // 방금 담았으면 true
}

/** 최근 본 곳 — 같은 것을 다시 보면 맨 위로 올리고, 20개까지만 둔다 */
function pushRecent(it) {
  const key = keyOf(it);
  const list = BOX.get('recent').filter((x) => x.key !== key);
  list.unshift({ ...it, key, ts: Date.now() });
  BOX.set('recent', list.slice(0, MAX_RECENT));
}

const clearAllSaved = () => { BOX.set('fav', []); BOX.set('recent', []); };

/** 저장·최근에 담긴 것 하나를 줄로 그린다(거리는 지금 기준점이 있을 때만) */
/** 폐기된 번호인가 — 같은 관리번호에 **다른 시설**이 들어와 번호를 끊은 곳(사례지식 6-33).
    저장해 둔 사람에게 알리지 않으면 **다른 화장실을 보고 찾아간다.** */
const isRetired = (it) => it.k === 't' && S.index && (S.index.retired || []).includes(it.rec.id);

function savedRow(it, i, where) {
  const m = S.base ? distM(S.base.la, S.base.lo, it.la, it.lo) : null;
  const dead = isRetired(it);
  const dist = m == null ? '' : `<span class="sdist">${m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`}</span>`;
  const icon = it.k === 'r' ? 'i-train' : it.k === 'p' ? 'i-pin' : 'i-toilet';
  const sub = it.k === 'r' ? `${esc(lineLabel(it.st))} · ${esc(it.st.src)}`
    : it.k === 'p' ? esc(it.addr || '저장한 자리')
      : esc(shortAddr(it.rec.a));
  return `<div class="srow${it.k === 'r' ? ' rail' : ''}${dead ? ' dead' : ''}" data-${where}="${i}" role="button" tabindex="0">
      <svg class="sic"><use href="#${icon}"/></svg>
      <div class="stx"><b>${esc(it.n)}</b><span>${dead ? '이 자리에는 다른 시설이 들어왔어요 — 확인이 필요합니다' : sub}</span></div>${dead ? '' : dist}
      <button class="sdel" data-del="${where}:${i}" aria-label="${esc(it.n)} 지우기"><svg><use href="#i-x"/></svg></button>
    </div>`;
}

/** 담긴 것을 눌렀을 때 — 화장실·역은 상세로, 자리는 그 자리에서 다시 찾기.
    **먼저 데이터를 갖춘다.** 하단 탭이 생기면서 목록을 거치지 않고 바로 들어올 수 있게 됐는데,
    상세 화면은 기준일(index.json·rail.json)을 읽는다 — 없으면 아무 일도 일어나지 않았다(T25). */
async function openSaved(it) {
  await Promise.all([loadIndex(), loadRail()]);
  if (it.k === 't') return openDetail(it.rec, S.base ? distM(S.base.la, S.base.lo, it.rec.la, it.rec.lo) : null);
  if (it.k === 'r') return openRailDetail(it.st, S.base ? distM(S.base.la, S.base.lo, it.st.la, it.st.lo) : null);
  S.mode = 'other';
  S.query = null;
  S.base = { la: it.la, lo: it.lo, addr: it.addr || '저장한 자리', name: it.n };
  await showList();
}

function renderSaved() {
  const list = favs();
  const places = list.filter((x) => x.k === 'p'), spots = list.filter((x) => x.k !== 'p');
  const body = $('#saved-body');
  body.innerHTML = `
    ${S.base ? `<button class="btn ghost" id="b-savehere"><svg><use href="#i-star"/></svg>지금 보고 있는 자리 저장 — ${esc(S.base.name || shortAddr(S.base.addr))}</button>` : ''}
    <h3 class="ssec">자주 가는 자리 ${places.length ? `<span>${places.length}</span>` : ''}</h3>
    ${places.length ? places.map((x, i) => savedRow(x, list.indexOf(x), 'fav')).join('')
      : '<div class="sempty">집·회사처럼 <b>자주 가는 자리</b>를 저장해 두면, 그 둘레 화장실을 한 번에 볼 수 있어요.</div>'}
    <h3 class="ssec">저장한 화장실 ${spots.length ? `<span>${spots.length}</span>` : ''}</h3>
    ${spots.length ? spots.map((x) => savedRow(x, list.indexOf(x), 'fav')).join('')
      : '<div class="sempty">화장실 정보 화면에서 오른쪽 위 <b>저장</b>을 누르면 여기에 담깁니다.</div>'}
    <div class="sfoot"><b>이 휴대폰 안에만 남습니다.</b> 서버로 보내지 않습니다.</div>
    ${list.length ? '<button class="btn ghost danger" id="b-clearfav"><svg><use href="#i-trash"/></svg>저장한 곳 모두 지우기</button>' : ''}`;
  bindSaved(body, 'fav', list);
  if ($('#b-savehere')) {
    $('#b-savehere').onclick = () => {
      toggleFav({ k: 'p', n: S.base.name || shortAddr(S.base.addr), addr: S.base.addr, la: S.base.la, lo: S.base.lo });
      renderSaved();
    };
  }
  if ($('#b-clearfav')) $('#b-clearfav').onclick = (e) => askClear(e.currentTarget, '저장한 곳', () => { BOX.set('fav', []); renderSaved(); });
}

function renderRecent() {
  const list = BOX.get('recent');
  const body = $('#recent-body');
  body.innerHTML = list.length
    ? list.map((x, i) => savedRow(x, i, 'rec')).join('')
      + `<div class="sfoot"><b>이 휴대폰 안에만 남습니다.</b> 서버로 보내지 않습니다.</div>
         <button class="btn ghost danger" id="b-clearrec"><svg><use href="#i-trash"/></svg>최근 본 곳 지우기</button>`
    : '<div class="sempty">본 화장실과 찾은 자리가 여기에 <b>20개까지</b> 남습니다. 다시 찾을 때 주소를 또 치지 않아도 돼요.</div>';
  bindSaved(body, 'rec', list);
  if ($('#b-clearrec')) $('#b-clearrec').onclick = (e) => askClear(e.currentTarget, '최근 본 곳', () => { BOX.set('recent', []); renderRecent(); });
}

/** 지우기는 되돌릴 수 없다 — 버튼을 한 번 더 누르게 한다(따로 창을 띄우지 않고 그 자리에서) */
function askClear(btn, what, run) {
  if (btn.dataset.ask) return run();
  btn.dataset.ask = '1';
  btn.classList.add('armed');
  btn.innerHTML = `<svg><use href="#i-trash"/></svg>정말 지울까요? 한 번 더 누르면 ${what}이 모두 지워집니다`;
  setTimeout(() => {
    if (!btn.isConnected) return;
    delete btn.dataset.ask;
    btn.classList.remove('armed');
    btn.innerHTML = `<svg><use href="#i-trash"/></svg>${what} 모두 지우기`;
  }, 4000);
}

function bindSaved(body, where, list) {
  body.querySelectorAll(`[data-${where}]`).forEach((el) => (el.onclick = (e) => {
    if (e.target.closest('.sdel')) return;
    const it = list[+el.dataset[where]];
    if (it) openSaved(it);
  }));
  body.querySelectorAll('.sdel').forEach((b) => (b.onclick = (e) => {
    e.stopPropagation();
    const [w, i] = b.dataset.del.split(':');
    const key = w === 'fav' ? 'fav' : 'recent';
    const arr = BOX.get(key);
    arr.splice(+i, 1);
    BOX.set(key, arr);
    (w === 'fav' ? renderSaved : renderRecent)();
  }));
}

/* ── 미리 받아 두기 — 지하에서는 인터넷이 잘 안 된다 ──────────
   지금 자리 둘레의 칸을 미리 받아 두면 서비스 워커가 저장해, 신호가 없어도 목록이 열린다.
   (지도는 카카오 서버라 저장할 수 없다 — 목록·상세만 된다) */
async function preloadArea(btn) {
  if (!S.base) { btn.textContent = '먼저 위치를 정해 주세요'; return; }
  const idx = await loadIndex();
  const r0 = Math.floor(S.base.la / TILE), c0 = Math.floor(S.base.lo / TILE);
  const keys = [];
  for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++) {
    const k = `${r0 + dr}_${c0 + dc}`;
    if (idx.tiles[k]) keys.push(k);
  }
  btn.disabled = true;
  let done = 0;
  for (const k of keys) {
    await fetch(tileUrl(k, idx)).catch(() => {});
    btn.textContent = `받는 중… ${++done}/${keys.length}`;
  }
  await fetch('data/rail.json').catch(() => {});
  btn.disabled = false;
  btn.textContent = `이 둘레 ${keys.length}칸을 받아 뒀어요 — 다시 받기`;
}
