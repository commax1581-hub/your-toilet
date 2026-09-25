/* 상세 화면 — 카드에서 누르면 열린다.
   카드가 한 줄로 말한 것을 여기서 풀어 말하고(사례지식 2-13 상세), 확인·이동 수단을 연결한다.
   링크 형식은 착한가격 모듈 문서(외부플랫폼-레퍼런스 4장). 구글은 국내 도보 길찾기가 없어 "위치 보기"만(6-9). */
'use strict';

const enc = encodeURIComponent;
let govSites = null;

/** 상세의 자세한 안내 문구 — [제목, 설명] */
function longNotice(rec, st) {
  const n = [];
  if (rec.g === 'P') {
    n.push(rec.pc
      ? ['시설 위치 기준', '공공데이터에 정확한 도로명·지번 주소가 없어 <b>시설 이름을 기준</b>으로 안내합니다. 시설 안 어디인지는 알 수 없어요. 도착하면 안내판·안내소를 확인하거나 시설 관계자에게 물어보세요.']
      : ['이름으로 찾은 위치', '공공데이터에 정확한 주소가 없어 <b>시설 이름으로 찾은 위치</b>입니다. <b>실제 위치와 다를 수 있어요.</b> 도착하면 안내판·안내소를 확인하거나 시설 관계자에게 물어보세요.']);
  } else if (rec.w === 'M') {
    n.push(['산지에 있어요', '산·공원처럼 <b>넓은 곳</b>이라 지도의 점이 화장실 자리와 다를 수 있어요. 보통 주차장이나 입구 쪽에 있습니다.']);
  } else if (rec.w === 'W') {
    n.push(['범위가 넓어요', '공원처럼 <b>넓은 곳</b>이라 지도의 점이 화장실 자리와 다를 수 있어요. 보통 주차장이나 입구 쪽에 있습니다. 안내판을 확인하세요.']);
  }
  if (rec.t === 3) n.push(['이동식 화장실', '행사·공사에 따라 <b>자리가 바뀔 수 있는</b> 이동식입니다.']);
  if (rec.gs) n.push(['주유소·충전소', '사무실 안쪽이나 건물 뒤편에 있을 수 있어요. <b>직원에게 물어보고</b> 이용하세요.']);
  if (rec.gt === 1) n.push(['개찰구 안', '지하철 <b>개찰구 안</b>에 있어 교통카드로 들어가야 이용할 수 있어요.']);
  else if (rec.gt === 0) n.push(['개찰구 밖', '지하철 <b>개찰구 밖</b>이라 표 없이 이용할 수 있어요.']);
  if (rec.h.ir) n.push(['적힌 시각 기준', '공공데이터의 개방시간 코드는 <b>불규칙</b>인데 상세에 시각이 적혀 있어 그 시각으로 안내합니다. 실제 개방 시간은 달라질 수 있어요.']);
  if (st.holi) n.push([st.holi + ' 확인', '관공서·사무실 건물은 ' + st.holi + '에 닫혀 있을 수 있어요. 공공데이터에 ' + st.holi + ' 시간이 따로 적혀 있지 않아 <b>확인이 필요합니다.</b>']);
  else if (st.k === 'unknown') n.push(['시간 확인 필요', '공공데이터에 여는 시간이 "근무시간"처럼 적혀 있어 지금 열려 있는지 알 수 없어요. 관리기관에 전화로 확인할 수 있습니다.']);
  if (rec.ni) n.push(['시설 정보 없음', '변기 수가 공공데이터에 적혀 있지 않습니다. <b>없다는 뜻은 아닙니다.</b>']);
  else if (rec.fq) n.push(['여성 칸 표기 없음', '여성용 변기 수가 0으로 적혀 있어 <b>남녀 공용 한 칸</b>일 수 있습니다.']);
  return n.map((x) => `<div class="dnote"><b>${x[0]}</b>${x[1]}</div>`).join('');
}

/** 큰 픽토그램 — 없는 것도 흐리게 보여 준다(없다고 단정하지 않되, 있는 것과 구분) */
function facBig(rec) {
  const one = (color, icon, label, num, on) => `<div class="fbox${on ? '' : ' off'}">
      <svg${on ? ` style="color:var(--${color})"` : ''}><use href="#i-${icon}"/></svg>
      <div class="fl">${label}</div><div class="fn">${on ? num : '—'}</div></div>`;
  const m = rec.m || [0, 0], x = rec.x || [0, 0], c = rec.c || [0, 0];
  return '<div class="fgrid">'
    + one('male', 'male', '남성', `대 ${m[0]} · 소 ${m[1]}`, m[0] + m[1] > 0)
    + one('female', 'female', '여성', rec.fq ? '표기 없음' : `${rec.f}칸`, rec.fq ? true : rec.f > 0)
    + one('acc', 'acc', '장애인', `남 ${x[0]} · 여 ${x[1]}`, x[0] + x[1] > 0)
    + one('baby', 'child', '어린이', `남 ${c[0]} · 여 ${c[1]}`, c[0] + c[1] > 0)
    + one('baby', 'diaper', '기저귀 교환대', rec.dp ? '있음' : '없음', rec.dp === 1)
    + one('open', 'bell', '비상벨', rec.bl ? '있음' : '없음', rec.bl === 1)
    + one('acc', 'cctv', '입구 CCTV', rec.cc ? '있음' : '없음', rec.cc === 1)
    + '</div>';
}

/** 주소로 시군구 홈페이지 찾기(오류 신고 안내) */
async function sigunguHome(addr) {
  if (!govSites) govSites = await fetch('data/gov_sites.json').then((r) => r.json()).catch(() => ({}));
  const p = String(addr || '').split(' ');
  for (const key of Object.keys(govSites)) {
    const part = key.split(' ');
    if (p[0] && part[0] && p[0].slice(0, 2) === part[0].slice(0, 2) && p.slice(1, 4).includes(part[1])) {
      return { 기관: govSites[key].기관, 홈페이지: govSites[key].홈페이지 };
    }
  }
  return null;
}

function openDetail(rec, m) {
  const now = new Date(), st = statePill(rec, now), k = KINDS[rec.t] || KINDS[0];
  const ll = `${rec.la},${rec.lo}`;
  const tel = String(rec.tel || '').replace(/[^0-9+-]/g, '');
  const old = rec.dy && rec.dy <= new Date().getFullYear() - 4;
  const L = {
    kakaoWalk: `https://map.kakao.com/link/to/${enc(rec.n)},${ll}`,
    naverWalk: `https://map.naver.com/p/directions/-/${rec.lo},${rec.la},${enc(rec.n)}/-/walk`,
    roadview: `https://map.kakao.com/link/roadview/${ll}`,
    place: rec.p ? `https://place.map.kakao.com/${rec.p}` : `https://map.kakao.com/link/map/${enc(rec.n)},${ll}`,
    google: `https://www.google.com/maps/search/?api=1&query=${ll}`,
    naverMap: `https://map.naver.com/p/search/${enc(rec.n + ' ' + rec.a)}`,
  };
  $('#dt-s').textContent = `${hhmm(now)} 기준 · 공공데이터 ${S.index.date}`;
  $('#detail-body').innerHTML = `
    <div class="dhead">
      <div class="dn">${esc(rec.n)}</div>
      <div class="da">${esc(rec.a)}</div>
      <div class="meta"><span class="pill ${k.c}"><svg><use href="${k.i}"/></svg>${k.l}</span>${st.html}${accBadge(rec)}</div>
      ${m != null ? `<div class="dm"><svg><use href="#i-walk"/></svg>${m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`} · 걸어서 약 ${Math.max(1, Math.round(m / WALK))}분</div>` : ''}
    </div>
    ${longNotice(rec, st.s)}
    <div class="dsec"><h3>시설</h3>${facBig(rec)}</div>
    <div class="dsec"><h3>여는 시간</h3>
      <div class="dtime">${st.html}<div class="raw">공공데이터 표기 · <b>${esc(rec.ht || '적혀 있지 않음')}</b></div></div>
    </div>
    <div class="dsec"><h3>길찾기 (도보)</h3>
      <div class="dbtns">
        <a class="btn main" href="${L.kakaoWalk}" target="_blank" rel="noopener"><svg><use href="#i-walk"/></svg>카카오맵 길찾기</a>
        <a class="btn ghost" href="${L.naverWalk}" target="_blank" rel="noopener"><svg><use href="#i-walk"/></svg>네이버 도보 길찾기</a>
      </div>
      <div class="dsub">휴대폰에서 카카오맵 앱으로 열리면 목적지가 <b>좌표로 보일 수 있습니다</b>(앱이 이름을 받지 않습니다).${rec.p ? ' 아래 <b>카카오 장소</b>로 열면 이름 그대로 보입니다.' : ''}</div>
    </div>
    <div class="dsec"><h3>지도에서 보기</h3>
      <div class="dbtns">
        <a class="btn ghost" href="${L.place}" target="_blank" rel="noopener"><svg><use href="#i-pin"/></svg>${rec.p ? '카카오 장소' : '카카오맵'}</a>
        <a class="btn ghost" href="${L.naverMap}" target="_blank" rel="noopener"><svg><use href="#i-pin"/></svg>네이버 지도</a>
        <a class="btn ghost" href="${L.google}" target="_blank" rel="noopener"><svg><use href="#i-pin"/></svg>구글 지도</a>
      </div>
      <div class="dsub">구글 지도는 국내 장소 이름을 갖고 있지 않아 <b>좌표로 표시</b>됩니다(위치는 정확합니다).</div>
    </div>
    <div class="dsec"><h3>입구 확인 (로드뷰)</h3>
      <div class="dbtns">
        <a class="btn ghost" href="${L.roadview}" target="_blank" rel="noopener"><svg><use href="#i-eye"/></svg>카카오 로드뷰</a>
      </div>
      <div class="dsub">국내 로드뷰는 카카오가 가장 넓습니다. 네이버 거리뷰는 <b>좌표로 바로 여는 방법이 없고</b>(파노라마 고유 번호로만 열림), 구글 스트리트뷰는 <b>국내에 없는 곳이 많아</b>(검은 화면) 넣지 않았습니다.</div>
    </div>
    <div class="dsec"><h3>관리기관</h3>
      <div class="dorg"><b>${esc(rec.o || '표기 없음')}</b>
        ${tel ? `<a class="btn ghost" href="tel:${tel}"><svg><use href="#i-tel"/></svg>${esc(rec.tel)}</a>` : '<span class="dsub">전화번호가 없습니다</span>'}</div>
      <div class="dsub">지금 열려 있는지, 시설이 그대로인지는 관리기관이 가장 정확합니다.</div>
    </div>
    <div class="dsec"><h3>이 정보는</h3>
      <div class="dsub">출처 행정안전부 공중화장실정보(공공데이터포털) · 공공데이터 기준일 ${S.index.date}${rec.dy ? ` · 지자체가 적은 정보 기준 <b>${rec.dy}년</b>` : ''}
${rec.dy ? ' · ' : ''}번호 ${esc(rec.id)}${rec.ids ? ` · 합친 등록 ${rec.ids.length}건` : ''}
        ${old ? '<br><b>정보가 오래됐습니다.</b> 지금과 다를 수 있어요.' : ''}</div>
      <div class="dfix"><b>정보가 틀렸나요?</b><br>① 위 관리기관에 전화 ② <span id="d-gov">해당 시군구 홈페이지</span> ③ <a href="https://www.data.go.kr/tcs/opd/ndm/view.do" target="_blank" rel="noopener">공공데이터포털 오류 신고</a>
        <div class="dsub">정보는 각 지자체가 관리하니, 틀린 내용은 관리기관에 알려 주세요.</div></div>
    </div>`;
  markDetail({ k: 't', n: rec.n, la: rec.la, lo: rec.lo, rec });
  go('detail');
  $('#detail-body').scrollTop = 0;
  sigunguHome(rec.a).then((g) => {
    const el = $('#d-gov');
    if (g && el) el.outerHTML = `<a href="${g.홈페이지}" target="_blank" rel="noopener">${esc(g.기관)} 홈페이지</a>`;
  });
}
