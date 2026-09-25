/* 휴대폰 사용성 — 앱 안 브라우저 안내 · 홈 화면에 추가
   착한가격 지도 `app/mobile.js`의 규칙을 옮겨 왔다(모듈: 외부플랫폼-레퍼런스).
   옮기면서 둘을 바꿨다: ① 이모지 대신 아이콘(보기 설정·접근성 규칙) ② 문구를 짧게 끊어 **어중간한 줄바꿈**을 막는다.

   카카오톡 안에서 열면 **내 위치와 홈 화면 추가가 막힌다** — 이 앱은 위치가 전부라 특히 크다. */
'use strict';

const UA = navigator.userAgent;
const IN_APP = /KAKAOTALK/i.test(UA) ? 'kakao'
  : /NAVER\(inapp|Instagram|FBAN|FBAV|Line\/|DaumApps|everytimeApp|BAND\//i.test(UA) ? 'other' : '';
const IS_IOS = /iPhone|iPad|iPod/.test(UA);

const MLS = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};

/** 기본 브라우저로 열기 — 카카오톡은 전용 주소, 안드로이드는 인텐트, 아이폰은 안내만 */
function openExternal() {
  const url = location.href;
  if (IN_APP === 'kakao') location.href = `kakaotalk://web/openExternal?url=${encodeURIComponent(url)}`;
  else if (/Android/.test(UA)) location.href = `intent://${url.replace(/^https?:\/\//, '')}#Intent;scheme=https;package=com.android.chrome;end`;
  else alert('오른쪽 위(또는 아래) 메뉴에서 "다른 브라우저로 열기"를 눌러 주세요.');
}

/** 앱 안 브라우저 띠 — 닫으면 그 방문 동안 다시 띄우지 않는다 */
function inAppBanner() {
  if (!IN_APP) return;
  if (sessionStorage.getItem('inappClosed')) return;
  const who = IN_APP === 'kakao' ? '카카오톡' : '앱';
  document.body.insertAdjacentHTML('afterbegin', `<div class="inapp" id="inapp">
      <svg class="ic"><use href="#i-q"/></svg>
      <span><b>${who} 안에서는 내 위치를 쓸 수 없어요.</b><br>브라우저로 열면 가까운 화장실을 찾아 드립니다.</span>
      <button class="go" id="inappOpen">브라우저로 열기</button>
      <button class="x" id="inappX" aria-label="안내 닫기"><svg><use href="#i-x"/></svg></button>
    </div>`);
  $('#inappOpen').onclick = openExternal;
  $('#inappX').onclick = () => {
    $('#inapp').remove();
    try { sessionStorage.setItem('inappClosed', '1'); } catch (e) {}
  };
}

/* ── 홈 화면에 추가 ── */
const isInstalled = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone || MLS.get('installed') === '1';
addEventListener('appinstalled', () => { MLS.set('installed', '1'); hideInstall(); });

function browserName() {
  if (IN_APP === 'kakao') return '카카오톡 안 브라우저';
  if (/NAVER\(inapp/i.test(UA)) return '네이버 앱 안 브라우저';
  if (IN_APP) return '앱 안 브라우저';
  if (/Whale/i.test(UA)) return '네이버 웨일';
  if (/SamsungBrowser/i.test(UA)) return '삼성 인터넷';
  if (/EdgA|Edg\//i.test(UA)) return '엣지';
  if (/Firefox|FxiOS/i.test(UA)) return '파이어폭스';
  if (IS_IOS && /CriOS/i.test(UA)) return '크롬(아이폰)';
  if (IS_IOS) return '사파리';
  if (/Chrome/i.test(UA)) return '크롬';
  return '';
}

/** 브라우저마다 누르는 자리가 다르다 — 한 줄씩 끊어 적는다(긴 문장은 작은 화면에서 어중간하게 접힌다) */
function installSteps() {
  if (IN_APP) {
    return ['지금은 <b>앱 안</b>에서 열려 있어 추가할 수 없어요.',
      '아래 <b>브라우저로 열기</b>를 누른 뒤 다시 시도해 주세요.'];
  }
  if (IS_IOS && !/CriOS|FxiOS|EdgiOS/i.test(UA)) {
    return ['① 화면 아래 <b>공유</b> 단추', '② <b>홈 화면에 추가</b>', '③ 오른쪽 위 <b>추가</b>'];
  }
  if (IS_IOS) return ['아이폰은 <b>사파리</b>에서만 추가할 수 있어요.', '주소를 복사해 사파리에서 열어 주세요.'];
  if (/SamsungBrowser/i.test(UA)) return ['① 아래 <b>메뉴</b>', '② <b>현재 페이지 추가</b>', '③ <b>홈 화면</b>'];
  if (/Whale/i.test(UA)) return ['① 아래 <b>메뉴</b>', '② <b>홈 화면에 추가</b>', '③ <b>추가</b>'];
  if (/EdgA/i.test(UA)) return ['① 아래 <b>메뉴</b>', '② <b>휴대폰에 추가</b>'];
  if (/Firefox/i.test(UA)) return ['① 오른쪽 위 <b>메뉴</b>', '② <b>설치</b>'];
  return ['① 오른쪽 위 <b>메뉴</b>', '② <b>홈 화면에 추가</b>', '③ <b>추가</b>'];
}

function showInstall() {
  const b = browserName();
  $('#inst-b').textContent = b ? `지금 쓰는 브라우저: ${b}` : '';
  $('#inst-steps').innerHTML = installSteps().map((s) => `<li>${s}</li>`).join('');
  $('#inst-ext').hidden = !IN_APP;
  $('#s-inst').classList.add('on');
}
const hideInstall = () => {
  $('#s-inst').classList.remove('on');
  document.querySelectorAll('.instchip').forEach((e) => e.remove());
};

/** 화장실을 한 번 본 뒤에 한 번만 권한다 — 처음부터 띄우면 방해가 된다. 닫으면 7일 쉰다. */
function installNudge() {
  if (isInstalled() || IN_APP || document.querySelector('.instchip')) return;
  if (Date.now() < +(MLS.get('instSnooze') || 0)) return;
  MLS.set('instSnooze', String(Date.now() + 7 * 864e5));
  document.body.insertAdjacentHTML('beforeend', `<div class="instchip" role="dialog" aria-label="홈 화면에 추가">
      <svg class="ic"><use href="#i-toilet"/></svg>
      <span><b>홈 화면에 두면 더 빨라요</b><small>아이콘을 눌러 바로 열 수 있습니다</small></span>
      <button class="go" id="instAdd">추가</button>
      <button class="x" id="instX" aria-label="닫기"><svg><use href="#i-x"/></svg></button>
    </div>`);
  $('#instAdd').onclick = () => { document.querySelector('.instchip').remove(); showInstall(); };
  $('#instX').onclick = () => document.querySelector('.instchip').remove();
}

function initMobile() {
  if (MLS.get('installed') !== '1' && isInstalled()) MLS.set('installed', '1');
  inAppBanner();
  $('#b-inst').hidden = isInstalled();
  $('#b-inst').onclick = showInstall;
  $('#inst-ext').onclick = openExternal;
  document.querySelectorAll('#s-inst [data-close]').forEach((b) => (b.onclick = hideInstall));
}
