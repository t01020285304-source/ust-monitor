/* ==========================================================================
   🇺🇸 미국 국채 위기 모니터 (공개용 단독 사이트) — builder/build.py 가 만든 JSON(data 브랜치)을 읽어 그린다
   원본: 가격결정자_리서치/web/ust.js — 개인 메모·내 일정 추가 기능은 공개용이라 뺐어요
   원본: US_Treasury_Monitor_Dashboard.html 의 기능을 이 사이트 구조(서버 수집·출처 표시·다크 테마)에 맞게 재구성
   ========================================================================== */
(function () {
  'use strict';
  let M, $, esc, fN, sgn, src, lineSvg, main;
  const ST = { tab: 'op', D: null, sel: 0 };
  const TABS = [['op', '⭐ 종합 의견'], ['force', '🧯 강제매도 진단'], ['pipes', '💧 돈의 배관 18'], ['auc', '🏷️ 입찰 결과'], ['chain', '🔗 입찰 붕괴 연쇄'], ['cal', '📅 이벤트 일정'], ['liq', '💧 유동성 완충'], ['repo', '🔄 레포'],
    ['absorb', '🧲 흡수력'], ['rates', '📈 금리 원인'], ['issue', '🏛️ 발행 구조'], ['int', '💸 이자 부담'], ['credit', '⚠️ 신용위기'], ['japan', '🗾 일본·캐리'], ['contra', '🔀 역발상'], ['guide', '📖 해석법·용어']];
  const STL = { ok: '정상', warn: '경계', bad: '위험', na: '—' };

  // 데이터: config.js 의 DATA_URL(GitHub data 브랜치) → 실패하면 사이트에 함께 올린 data/ust.json
  async function getJson(u) {
    const r = await fetch(u, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }
  // 더블클릭(file://)으로 열면 JSON 읽기가 막혀서 data/ust-data.js(같은 내용)를 스크립트로 불러온다
  const snapshot = () => window.UST_SNAPSHOT ? Promise.resolve(window.UST_SNAPSHOT) : new Promise((ok, no) => {
    const s = document.createElement('script'); s.src = 'data/ust-data.js';
    s.onload = () => window.UST_SNAPSHOT ? ok(window.UST_SNAPSHOT) : no(new Error('데이터 파일이 비어 있어요'));
    s.onerror = () => no(new Error('data/ust-data.js 가 없어요 — python builder/build.py 로 먼저 만들어 주세요'));
    document.head.appendChild(s);
  });
  async function api() {
    if (location.protocol === 'file:') return snapshot();
    const bust = '?t=' + Math.floor(Date.now() / 6e5);          // 10분 단위로 새로 받기
    const urls = [(window.UST_CFG || {}).DATA_URL, 'data/ust.json'].filter(Boolean);
    let last;
    for (const u of urls) { try { return await getJson(u + bust); } catch (e) { last = e; } }
    throw last || new Error('데이터 주소가 없어요');
  }
  const B = v => v == null || !isFinite(v) ? '—' : Math.abs(v) >= 1000 ? `$${fN(v / 1000, 2)}T` : `$${fN(v, v >= 100 ? 0 : 1)}B`;
  const usd = v => v == null ? '—' : v >= 1e12 ? `$${fN(v / 1e12, 2)}T` : v >= 1e9 ? `$${fN(v / 1e9, 1)}B` : `$${fN(v / 1e6, 0)}M`;
  const pc = (v, d = 1) => v == null || !isFinite(v) ? '—' : fN(v, d) + '%';
  const bp = v => v == null || !isFinite(v) ? '—' : sgn(v, 0) + 'bp';
  const badge = (st, t) => `<span class="mk-badge st-${st || 'na'}">${esc(t ?? STL[st] ?? '—')}</span>`;
  const stOf = t => /🚨|🔴|위험|위기|공포|부족|부진|과부담|바닥|긴장|심각|D|F/.test(t || '') ? 'bad' : /🟠|🟡|⚠|경계|조짐|주의|높은|중간/.test(t || '') ? 'warn' : 'ok';
  const card = (title, body, cls = '') => `<section class="mk-card ${cls}"><h3>${title}</h3>${body}</section>`;
  const foot = links => links && links.length ? `<div class="mk-foot">${links.map(l => src(l.label, l.url)).join(' ')}</div>` : '';
  const kv = (k, v, sub, st) => `<div class="ust-kv ${st ? 'st-' + st : ''}"><div class="mk-sub">${k}</div><div class="mk-fv">${v}</div>${sub ? `<div class="mk-sub">${sub}</div>` : ''}</div>`;
  const tip = (t, d) => `<span class="ust-term" title="${esc(d)}">${esc(t)}</span>`;

  // ══ 페이지 ═══════════════════════════════════════════════════
  async function page(mainEl, tab) {
    if (tab && TABS.some(t => t[0] === tab)) ST.tab = tab;
    const ix = +(location.hash.split('/')[1] || NaN); if (isFinite(ix)) ST.sel = ix;   // #auc/9 = 9번째 입찰 리포트
    M = window.MK; ({ $, esc, fN, sgn, src, lineSvg } = M); main = mainEl;
    main.innerHTML = `<h1 class="mk-h1">🗽 미국 국채 위기 모니터 <span class="mk-sub">입찰 · 유동성 · 금리 · 신용 · 일본 캐리 — 재무부·연준·FRED·일본 재무성 원자료로 매일 자동 판독</span></h1>
      <div id="uBody"><div class="mk-loading">최신 판독 결과를 불러오는 중…</div></div>`;
    await load(false);
  }
  // 화면을 열어 둔 동안 10분마다 새 판독 결과가 있는지 확인 (바뀌었을 때만 다시 그림)
  setInterval(async () => {
    if (document.hidden || !ST.D || location.protocol === 'file:') return;
    try { const d = await api(); if ((d.built_at || d.fetched_at) !== (ST.D.built_at || ST.D.fetched_at)) { ST.D = d; draw(); } } catch (e) { }
  }, 6e5);
  async function load(force) {
    try { ST.D = await api(); } catch (e) { $('#uBody').innerHTML = `<div class="mk-err">불러오지 못했어요 — ${esc(e.message)}</div>`; return; }
    draw();
  }
  function draw() {
    const D = ST.D, y = window.scrollY;
    $('#uBody').innerHTML = `<div class="ust-top"><span class="mk-sub">${esc((D.built_at || D.fetched_at).replace('T', ' ').slice(0, 16))} (한국시간) 판독 · 평일 매시간 자동 갱신 · 이 화면은 10분마다 새 자료 확인 ${ageNote(D)}</span> <button class="btn sm" id="uRe">⟳ 다시 불러오기</button>
        ${D.errors.length ? `<span class="mk-sub bad" title="${esc(D.errors.join('\n'))}">일부 자료 ${D.errors.length}개를 받지 못했어요</span>` : ''}</div>
      ${(D.asof || []).length ? `<div class="ust-asof mk-sub">📅 자료 기준일 (미국 날짜): ${D.asof.map(x => `<span title="${esc(x.src)}">${esc(x.k)} <b>${esc((x.d || '—').slice(5).replace('-', '/'))}</b></span>`).join(' · ')} <span class="tiny">— 공식 통계는 발표 주기대로(대부분 하루 1번), 시세는 최대 15분 지연</span>${freshLine(D)}</div>` : ''}
      <div class="pf-tabs">${TABS.map(([k, l]) => `<button class="${ST.tab === k ? 'on' : ''}" data-ut="${k}">${l}</button>`).join('')}</div><div id="uTab"></div>`;
    $('#uRe').onclick = async () => { $('#uRe').textContent = '받는 중…'; await load(true); };
    document.querySelectorAll('[data-ut]').forEach(b => b.onclick = () => go(b.dataset.ut));
    $('#uTab').innerHTML = ({ op: tOp, force: D => stressHtml(D.stress8), pipes: D => pipesHtml(D.pipes18, D.bdc), auc: tAuc, chain: tChain, cal: tCal, liq: tLiq, repo: tRepo, absorb: tAbsorb, rates: tRates, issue: tIssue, int: tInt, credit: tCredit, japan: tJapan, contra: tContra, guide: tGuide }[ST.tab])(D);
    bind();
    window.scrollTo(0, y);
  }
  function go(t) { ST.tab = t; history.replaceState(null, '', '#' + t); draw(); window.scrollTo(0, 0); }
  // 자료가 오래됐으면 알려 주기 (자동 갱신이 멈췄을 때 친구들이 옛날 숫자를 오늘 것으로 오해하지 않게)
  function ageNote(D) {
    const t = Date.parse(D.built_at || D.fetched_at); if (!isFinite(t)) return '';
    const h = (Date.now() - t) / 36e5;
    return h > 30 ? `<b class="bad">· ${Math.floor(h / 24)}일 ${Math.floor(h % 24)}시간 전 자료예요</b>` : '';
  }
  function bind() {
    document.querySelectorAll('[data-go]').forEach(b => b.onclick = e => { e.preventDefault(); go(b.dataset.go); });
    const s = $('#uSel'); if (s && s.tagName) s.onchange = () => { ST.sel = +s.value; draw(); };
    const p = $('#uPrint'); if (p && p.tagName) p.onclick = printNews;
    const g = $('#uGuideX'); if (g && g.tagName) g.onclick = () => { try { localStorage.setItem('ustGuideHide', '1'); } catch (e) { } $('#uGuide').remove(); };
  }

  // ── 배관도 (SVG) ─────────────────────────────────────────────
  // 상자 안 글자: ' · ' 단위로 줄을 나누고 한 줄 26자, 최대 2줄
  const lines = t => { const out = []; String(t).split(' · ').forEach(seg => { if (out.length && (out[out.length - 1] + ' · ' + seg).length <= 26) out[out.length - 1] += ' · ' + seg; else out.push(seg.length > 26 ? seg.slice(0, 25) + '…' : seg); }); return out.slice(0, 2); };
  function plumbSvg(P) {
    const pos = { treasury: [40, 30], fed: [40, 250], dealer: [330, 30], reservoir: [330, 250], repo: [620, 250], foreign: [620, 30], credit: [910, 250], gauge: [910, 30], pivot: [40, 140] };
    const W = 240, H = 78;
    const col = { ok: 'var(--green)', warn: 'var(--amber)', bad: 'var(--red)' };
    const by = Object.fromEntries(P.pipes.map(p => [p.key, p]));
    const link = (a, b) => { const [x1, y1] = pos[a], [x2, y2] = pos[b]; const s = by[a] && by[b] && (by[a].st === 'bad' || by[b].st === 'bad') ? 'bad' : by[a] && by[b] && (by[a].st === 'warn' || by[b].st === 'warn') ? 'warn' : 'ok';
      return `<line x1="${x1 + W / 2}" y1="${y1 + H / 2}" x2="${x2 + W / 2}" y2="${y2 + H / 2}" stroke="${col[s]}" stroke-width="5" stroke-opacity=".35" stroke-dasharray="10 8" class="ust-flow"/>`; };
    const pairs = [['treasury', 'dealer'], ['dealer', 'foreign'], ['foreign', 'gauge'], ['treasury', 'pivot'], ['pivot', 'fed'], ['fed', 'reservoir'], ['reservoir', 'repo'], ['repo', 'credit'], ['dealer', 'reservoir'], ['gauge', 'credit']];
    return `<svg class="ust-plumb" viewBox="0 0 1190 350" role="img" aria-label="미국 국채 시스템 배관도">${pairs.map(p => link(...p)).join('')}
      ${P.pipes.map(p => { const [x, y] = pos[p.key]; return `<g class="ust-node" data-go="${p.tab}" style="cursor:pointer"><rect x="${x}" y="${y}" width="${W}" height="${H}" rx="12" fill="var(--panel)" stroke="${col[p.st]}" stroke-width="2.5"/>
        <circle cx="${x + W - 16}" cy="${y + 16}" r="7" fill="${col[p.st]}"/><text x="${x + 12}" y="${y + 26}" class="ust-nt">${esc(p.name)}</text>
        ${lines(p.text).map((t, i) => `<text x="${x + 12}" y="${y + 48 + i * 17}" class="ust-ns">${esc(t)}</text>`).join('')}</g>`; }).join('')}</svg>`;
  }


  // 국채 금리가 '지금 받을 수 있는 최신'인지 판정 — 재무부는 미국 영업일 장 마감 금리를 그날 저녁(동부 18시경 = 한국 다음 날 오전 7시경)에 공개
  function freshLine(D) {
    const a = (D.asof || []).find(x => x.k === '국채 금리'); if (!a || !a.d) return '';
    const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
    const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const prevBiz = d => { const x = new Date(d); do { x.setDate(x.getDate() - 1); } while (x.getDay() === 0 || x.getDay() === 6); return x; };
    const nextBiz = d => { const x = new Date(d); do { x.setDate(x.getDate() + 1); } while (x.getDay() === 0 || x.getDay() === 6); return x; };
    const wk = et.getDay() !== 0 && et.getDay() !== 6;
    const exp = wk && et.getHours() >= 18 ? new Date(et) : prevBiz(et);              // 평일 18시(동부) 이후면 오늘 마감값, 아니면 직전 영업일 마감값이 최신
    const want = iso(exp), nxt = nextBiz(exp), kr = new Date(nxt); kr.setDate(kr.getDate() + 1);
    const md = s => `${+s.slice(5, 7)}/${+s.slice(8, 10)}`, built = String(D.fetched_at || '').replace('T', ' ').slice(5, 16);
    return a.d >= want
      ? `<div class="tiny" style="margin-top:2px">✅ 국채 금리는 지금 받을 수 있는 최신(${md(a.d)} 미국 장 마감)이에요 · 다음 공식 발표: ${md(iso(nxt))} 장 마감 금리 → 한국 시간 ${md(iso(kr))} 오전 7시경${built ? ` · 마지막 갱신 ${built}` : ''} <span class="dim">(미국 공휴일은 계산에서 제외)</span></div>`
      : `<div class="tiny warn" style="margin-top:2px">⚠ 재무부가 ${md(want)} 장 마감 금리를 이미 공개했을 시간인데 아직 반영 전이에요 — 다음 갱신 때 들어와요${built ? ` · 마지막 갱신 ${built}` : ''} <span class="dim">(미국 공휴일이면 정상)</span></div>`;
  }
  // ══ 1. 종합 의견 ══════════════════════════════════════════════
  function tOp(D) {
    const V = D.verdicts, R = D.recession, P = D.plumb;
    let hide = false; try { hide = localStorage.getItem('ustGuideHide') === '1'; } catch (e) { }
    return `<div class="mk-card mk-over st-${{ bad: 'bad', warn: 'warn', good: 'ok', neutral: 'na' }[D.mood.key]}"><div class="mk-sub">오늘의 종합 분위기 (초보자용 — 데이터를 몰라도 “오늘 무엇을 조심해야 하는지”만)</div>
        <div class="mk-big2">${esc(D.mood.label)}</div>
        <ol class="ust-3">${D.three.map(t => `<li>${esc(t)}</li>`).join('')}</ol></div>
      <div class="ust-scores">${D.scores.map(s => `<div class="mk-card st-${s.st || 'na'}"><div class="mk-sub">${esc(s.k)}</div><div class="mk-fv">${s.v == null ? '—' : esc(s.v)}${typeof s.v === 'number' ? '<span class="mk-sub">/100</span>' : ''}</div>${badge(s.st, s.badge)}<div class="mk-foot">${esc(s.why)}</div></div>`).join('')}</div>
      ${D.stress8 ? `<div class="s8-mini st-${D.stress8.case.lv}"><b>🧯 강제매도 진단</b> ${esc(D.stress8.case.t)} — ${D.stress8.questions.map(q => `${q.q.slice(0, 1)} ${q.yes ? '⚠️' : '✅'}`).join(' ')} <a href="#" data-go="force">자세히 ›</a></div>` : ''}
      ${D.pipes18 ? `<div class="s8-mini st-${D.pipes18.state.lv}"><b>💧 돈의 배관 18</b> ${esc(D.pipes18.state.t)} — 압력 ${D.pipes18.rows.filter(r => r.lv === 'warn' || r.lv === 'bad').map(r => r.n + '번').join(' · ') || '없음'} <a href="#" data-go="pipes">자세히 ›</a></div>` : ''}
      ${card('📰 오늘의 시황 — 쉽게 읽는 국채·금융 이야기 ' + badge({ bad: 'bad', warn: 'warn', good: 'ok', neutral: 'na' }[D.mood.key], D.mood.label), D.narrative.map(p => `<p class="ust-p">${esc(p)}</p>`).join(''))}
      ${card(`🚰 미국 국채 시스템 배관도 ${badge(P.st, P.title)}`, `${plumbSvg(P)}<div class="small" style="margin-top:6px">9개 지점 중 <b class="bad">이상 ${P.bad}</b> · <b class="warn">경계 ${P.warn}</b> — 상자를 누르면 해당 탭으로 이동해요. 가장 위험한 조합: <b>10년물 압력계 ↑ + 유동성 저수조 ↓ + 레포 분산 ↑</b> (2019년 레포 위기 패턴)</div>
        <div class="mk-foot">전이 경로 A: 국채 입찰 → Primary Dealer → 레포 → 신용 (빠름, ${esc(D.repo.pathA)}) · 경로 B: 은행·사모신용 (분기 공시 기반이라 자동 판정하지 않아요)</div>`)}
      ${hide ? '' : card('🎓 초보자 가이드: 이 5가지만 기억하세요 <button class="btn sm" id="uGuideX" style="margin-left:auto">접기</button>', `<ol class="ust-3">
        <li><b>배관도부터</b> — 빨간 상자가 어디인지 먼저 보세요.</li><li><b>숫자 하나하나보다 색깔</b> — 초록·주황·빨강 신호등만 봐도 돼요.</li>
        <li><b>“오늘의 시황”을 매일 읽기</b> — 같은 글이 며칠째 나빠지는지가 중요해요.</li><li><b>점선 밑줄 용어</b>에 마우스를 올리면 설명이 나와요.</li>
        <li><b>급하면 위의 3줄만</b>.</li></ol><div class="small warn">⚠️ 이 화면만 보고 투자 결정하지 마세요 — 시장 전체의 ‘날씨’를 보는 도구예요.</div>`, '').replace('<section class="mk-card ', '<section id="uGuide" class="mk-card ')}
      <h2 class="mk-h2">⭐ 5대 지표 종합 의견 <span class="mk-sub">QRA(국채 발행 계획) · FOMC · 일본은행 · CPI · 고용 — 공식 자료로 자동 판정</span></h2>
      <div class="mk-card st-${V.avg == null ? 'na' : V.avg >= 0.2 ? 'ok' : V.avg >= -0.2 ? 'na' : 'warn'}"><div class="mk-big2">${esc(V.title || '판정 불가')} <span class="mk-sub">종합 점수 ${V.avg == null ? '—' : sgn(V.avg, 2)} (${V.n}/5)</span></div><div>권장 행동: <b>${esc(V.action || '—')}</b></div></div>
      <div class="ust-v5">${['qra', 'fomc', 'boj', 'cpi', 'nfp'].map(k => { const x = V.items[k]; const n = { qra: '🏛️ QRA 국채 발행 계획', fomc: '🦅 FOMC (연준)', boj: '🗾 일본은행', cpi: '🛒 물가 (CPI)', nfp: '👷 고용 (NFP)' }[k];
        return `<div class="mk-card st-${!x ? 'na' : x.score > 0 ? 'ok' : x.score < 0 ? (x.score <= -1 ? 'bad' : 'warn') : 'na'}"><b>${n}</b><div class="mk-big2" style="font-size:17px">${x ? esc(x.title) : '자료 없음'}</div><div class="small">${x ? esc(x.summary) : ''}</div><div class="mk-sub">점수 ${x ? sgn(x.score, 1) : '—'}</div></div>`; }).join('')}</div>
      <div class="mk-foot">점수: +1 위험자산에 우호 ~ −1 부정. 평균 ≥+0.6 Risk-On · ≥+0.2 약한 우호 · ≥−0.2 중립 · ≥−0.6 약한 부정 · 그 아래 Risk-Off. CPI·고용은 시장 예상치 자료가 없어 실제값 수준으로만 판정해요.</div>
      ${recessionCard(R)}
      <div class="mk-grid2" style="margin-top:14px">
        ${card('🔀 3가지 시나리오별 대응', `<table class="t"><tr><th>시나리오</th><th>확인 지표</th><th>대응</th></tr>
          <tr><td class="ok"><b>낙관</b></td><td>역레포·지준 안정, 입찰 B등급 이상, 10년물 하락</td><td>위험자산 유지</td></tr>
          <tr><td><b>기본</b></td><td>응찰 2.0~2.5배, MOVE 100~120</td><td>현금 15~20%, 이벤트 확인</td></tr>
          <tr><td class="bad"><b>비관</b></td><td>입찰 D등급, Primary Dealer 25%↑, 달러 조달 경색</td><td>장기 듀레이션·고밸류 축소, 현금·달러·금</td></tr></table>`)}
        ${card('☕ 매일 아침 10분 체크리스트', `<ol class="ust-3"><li>입찰 등급 C 이하가 나왔나? (<a href="#" data-go="auc">입찰 결과</a>)</li><li>역레포 $100B 이하 + 지준 감소인가? (<a href="#" data-go="liq">유동성</a>)</li>
          <li>10년물이 하루 ±10bp 움직였다면 원인은? (<a href="#" data-go="rates">금리 원인</a>)</li><li>MOVE 120 이상인가? (<a href="#" data-go="contra">역발상</a>)</li><li>이번 주 일정이 몰린 날(클러스터)은? (<a href="#" data-go="cal">일정</a>)</li><li>이 탭의 분위기·3줄 다시 읽기</li></ol>`)}
      </div>
      <div class="mk-foot">자동 판독 결과이며 투자 권유가 아니에요. 원본 대시보드의 고정 문구(특정 날짜의 3줄 요약 등)는 매일 바뀌는 실제 자료로 대체했어요.</div>`;
  }
  // ══ 💧 돈의 배관 18지표 — 공급 계획 → 결제 → 완충재 → 가격 → 긴급 창구 → 레버리지 → 사모신용 → 은행 → 달러 → MMF ══════
  function pipesHtml(P, B) {
    if (!P || !P.rows) return '<div class="mk-sub">돈의 배관 18지표 자료를 받지 못했어요.</div>';
    const ic = { ok: '🟢', warn: '🟠', bad: '🔴', na: '·' }, S = P.state;
    const grps = []; P.rows.forEach(r => { let g = grps.find(x => x.g === r.grp); if (!g) grps.push(g = { g: r.grp, rows: [] }); g.rows.push(r); });
    const flow = `<div class="p18-flow">${grps.map(g => { const w = g.rows.some(r => r.lv === 'bad') ? 'bad' : g.rows.some(r => r.lv === 'warn') ? 'warn' : g.rows.every(r => !r.avail || r.lv === 'na') ? 'na' : 'ok';
      return `<span class="p18-st st-${w}">${esc(g.g)}</span>`; }).join('<span class="p18-ar">→</span>')}</div>`;
    const head = `<div class="mk-card mk-over st-${S.lv}"><div class="mk-sub">💧 돈의 배관 18지표 — 정부가 빌린 돈이 어디서 막히는지 (공급 계획부터 MMF까지 순서대로)</div>
      <div class="mk-big2">${ic[S.lv]} ${esc(S.t)}</div><div class="small">${esc(S.d)}</div><div class="small" style="margin-top:4px">지금 할 일: <b>${esc(S.act)}</b></div>${flow}
      <div class="mk-sub" style="margin-top:6px">3단계: 🟢 완화·정상화 → 🟠 선택적 조정(일부 구간만 압력) → 🔴 전이성 충격(여러 구간이 동시에 압력)</div></div>`;
    const nar = `<section class="mk-card s8-nar"><h3>📝 종합 해설</h3>${(P.narrative || []).map((t, i) => `<p class="${i === 0 ? 's8-lead' : ''}">${esc(t)}</p>`).join('')}</section>`;
    const tbl = `<div class="tablewrap"><table class="t p18-t"><tr><th>#</th><th>지표</th><th class="r">지금</th><th>변화</th><th>상태</th><th>무엇을 보나</th></tr>
      ${grps.map(g => `<tr class="p18-g"><td colspan="6">${esc(g.g)}</td></tr>` + g.rows.map(r => `<tr class="${r.avail ? '' : 'p18-off'}"><td class="mono">${r.n}</td><td><b>${esc(r.name)}</b>${r.asof ? `<div class="mk-sub"><b>${esc(r.asof)}</b>${/^\d{4}-/.test(r.asof) ? ' 기준' : ''}</div>` : ''}</td>
        <td class="r mono">${esc(r.val)}</td><td class="small">${esc(r.chg || '')}</td><td>${r.avail ? `${ic[r.lv]} ${{ ok: '안정', warn: '주의', bad: '위험', na: '참고' }[r.lv]}` : '<span class="mk-sub">대체 확인</span>'}</td>
        <td class="small">${esc(r.why)}${r.how ? `<div class="mk-sub">↳ ${esc(r.how)}</div>` : ''}${r.tab && r.tab !== 'pipes' ? ` <a href="#" data-go="${r.tab}">자세히 ›</a>` : ''}${r.tab === 'pipes' ? ' <a href="#" onclick="document.getElementById(&quot;p18bdc&quot;).scrollIntoView({behavior:&quot;smooth&quot;});return false">아래 표 ›</a>' : ''}${r.url ? ` <a class="mk-src" href="${esc(r.url)}" target="_blank" rel="noopener">원문 ↗</a>` : ''}</td></tr>`).join('')).join('')}</table></div>`;
    const pc1 = v => v == null ? '—' : fN(v * 100, 1) + '%', na = a => !a ? '—' : fN(a[0], 1) + '%' + (a.length > 1 ? ` <span class="mk-sub">(직전 ${fN(a[1], 1)}%)</span>` : '');
    const bdc = !B || !B.rows || !B.rows.length ? `<div class="mk-sub">사모신용 공시를 받지 못했어요${B && B.errors && B.errors.length ? ' — ' + esc(B.errors[0]) : ''}.</div>` : `<div class="tablewrap"><table class="t"><tr><th>펀드</th><th>공시</th><th class="r">펀드 빚 ÷ 순자산</th><th class="r">PIK 이자 비중</th><th class="r">Non-accrual 원가</th><th class="r">Non-accrual 공정가치</th><th class="r">남은 차입 한도</th></tr>
      ${B.rows.map(r => `<tr><td><b>${esc(r.name)}</b><div class="mk-sub">${esc(r.desc)}</div></td><td class="small"><a class="mk-src" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.form)} ↗</a><div class="mk-sub">${esc(r.period)} 기준 · ${esc(r.filed)} 공시</div>${r.tender ? `<a class="mk-src" href="${esc(r.tender)}" target="_blank" rel="noopener">환매(공개매수) 공시 ↗</a>` : ''}</td>
        <td class="r mono ${r.lev >= 1.25 ? 'warn' : ''}">${r.lev == null ? '—' : fN(r.lev, 2) + '배'}</td><td class="r mono ${r.pik >= 0.12 ? 'bad' : r.pik >= 0.08 ? 'warn' : ''}">${pc1(r.pik)}${r.pik_period ? `<div class="mk-sub">${esc(r.pik_period)}</div>` : ''}</td>
        <td class="r mono">${na(r.na_cost)}</td><td class="r mono ${r.na_fv && r.na_fv[0] >= 3 ? 'bad' : r.na_fv && r.na_fv[0] >= 1.5 ? 'warn' : ''}">${na(r.na_fv)}</td><td class="r mono">${r.room == null ? '—' : usd(r.room)}</td></tr>`).join('')}</table></div>
      <div class="small" style="margin-top:6px">읽는 법: <b>PIK</b>가 오르면 이자를 현금으로 못 받는 대출이 늘어난 것 · <b>Non-accrual</b>은 원가보다 공정가치가 훨씬 낮으면 이미 손실을 반영하는 중 · <b>남은 한도</b>가 줄면 펀드가 새 대출·환매에 쓸 돈이 줄어요. 기준: PIK 8%↑ 주의 · 12%↑ 위험, Non-accrual(공정가치) 1.5%↑ 주의 · 3%↑ 위험.</div>
      <div class="mk-foot">${esc(B.note)} · ${esc(B.src)}${B.errors && B.errors.length ? ' · 받지 못한 펀드: ' + esc(B.errors.join(' / ')) : ''}</div>`;
    return `${head}${nar}<section class="mk-card">${tbl}<div class="mk-foot">📚 ${esc(P.basis)} · 출처: ${esc(P.src)} · 회색 줄은 공식 무료 자료가 없어 ‘대체 확인’ 방법을 적어 둔 항목이에요.</div></section>
      <section class="mk-card" id="p18bdc"><h3>🏦 사모신용(BDC) 모니터 ${badge(B && B.lv, { ok: '안정', warn: '주의', bad: '위험' }[B && B.lv] || '—')} <span class="mk-sub">대형 BDC 5곳 · 분기 공시</span></h3>${bdc}</section>`;
  }
  // ══ 🧯 강제매도 위험 진단 (8지표) — 국채 모니터 탭 · 기존 지표 탭 · 공개 사이트가 같은 화면을 씀 ══════
  function stressHtml(S8, opt = {}) {
    const Mk = window.MK, e_ = Mk.esc, n_ = Mk.fN;
    if (!S8 || !S8.rows) return '<div class="mk-sub">강제매도 진단 자료를 받지 못했어요.</div>';
    const ic = { ok: '🟢', warn: '🟠', bad: '🔴', na: '·' }, cls = { ok: 'ok', warn: 'warn', bad: 'bad', na: 'na' };
    const val = r => r.v == null ? '—' : r.disp === '%' ? n_(r.v, 2) + '%' : r.unit === 'bp' ? n_(r.v, 0) + 'bp' : r.unit === '%p' ? n_(r.v, 1) + '%p' : n_(r.v, 2);
    const chg = (r, x) => x == null ? '—' : r.unit === 'bp' ? (x > 0 ? '+' : '') + n_(x, 0) + 'bp' : (x > 0 ? '+' : '') + n_(x, r.key === 'vix' || r.unit === '%p' ? 1 : 2);
    const C = S8.case;
    const FREQ = { real: '미 재무부 · 매일(당일 저녁 공개)', ccc: 'ICE BofA · 매일(하루 뒤 공개)', hy: 'ICE BofA · 매일(하루 뒤 공개)', ig: 'ICE BofA · 매일(하루 뒤 공개)',
      sofr: 'NY 연준 · 매일(다음 날 아침 공개)', nfci: '시카고 연은 · 매주(수요일 공개)', sloos: '연준 · 분기 조사', vix: 'Cboe · 장중(최대 15분 지연)' };
    const nar = (S8.narrative || []).length ? `<section class="mk-card s8-nar"><h3>📝 종합 해설 <span class="mk-sub">8개 지표를 한 번에 읽기 — 폭락 예측이 아니라 '위험의 종류' 진단</span></h3>${S8.narrative.map((t, i) => `<p class="${i === 0 ? 's8-lead' : ''}">${e_(t)}</p>`).join('')}</section>` : '';
    const head = `<div class="mk-card mk-over st-${cls[C.lv]}"><div class="mk-sub">🧯 강제매도 위험 진단 — 누군가 버티지 못하고 팔아야 하는 상황이 커지나 (8대 지표)</div>
      <div class="mk-big2">${ic[C.lv]} ${e_(C.t)}</div><div class="small">${e_(C.d)}</div>
      <div class="s8-q">${S8.questions.map(q => `<div class="s8-qi ${q.yes ? 'yes' : ''}"><b>${q.yes ? '⚠️ 예' : '✅ 아니오'}</b> ${e_(q.q)}<div class="mk-sub">${e_(q.ev)}</div></div>`).join('')}</div></div>`;
    if (opt.compact) return head;
    if (opt.mini) return `<div class="s8-mini st-${C.lv}"><b>🧯 강제매도 진단</b> ${e_(C.t)} — ${S8.questions.map(q => `${q.q.slice(0, 1)} ${q.yes ? '⚠️' : '✅'}`).join(' ')} <a href="${opt.href || '#'}">8개 지표 자세히 ›</a></div>`;
    const tbl = `<div class="tablewrap"><table class="t s8-t"><tr><th>지표</th><th class="r">지금</th><th class="r">1주 변화</th><th class="r">1개월 변화</th><th>상태</th><th>무엇을 보나</th></tr>
      ${S8.rows.map(r => `<tr><td><b>${e_(r.name)}</b><div class="mk-sub">${e_(r.sid || '')} · <b>${e_(r.date || '')}</b> 기준</div><div class="mk-sub">${e_(FREQ[r.key] || '')}</div></td><td class="r mono">${val(r)}</td><td class="r mono">${chg(r, r.c1w)}</td><td class="r mono">${chg(r, r.c1m)}${r.key === 'sloos' ? '<div class="mk-sub">직전 분기 대비</div>' : ''}</td>
        <td>${ic[r.lv]} ${{ ok: '안정', warn: '주의', bad: '위험', na: '—' }[r.lv]}${r.txt ? `<div class="mk-sub">${e_(r.txt)}</div>` : ''}</td><td class="small">${e_(r.why)}${r.rule ? `<div class="mk-sub">${e_(r.rule)}</div>` : ''}${r.url ? ` <a class="mk-src" href="${e_(r.url)}" target="_blank" rel="noopener">원문 ↗</a>` : ''}</td></tr>`).join('')}</table></div>
      ${S8.ccc_lead ? '<div class="small warn" style="margin-top:6px">⚠️ CCC 스프레드가 하이일드 전체보다 두드러지게 커지고 있어요 — 가장 약한 기업부터 돈줄이 막히는 모습이에요.</div>' : ''}`;
    const wk = `<details style="margin-top:10px"><summary class="small"><b>📅 매주 금요일 기록</b> — 최근 6주 (자료 기록에서 자동)</summary><div class="tablewrap"><table class="t small mono"><tr><th>지표</th>${S8.weeks.map(d => `<th class="r">${d.slice(5).replace('-', '/')}</th>`).join('')}</tr>
      ${S8.weekly.map(w => `<tr><td>${e_(w.name)}</td>${w.vals.map(v => `<td class="r">${v == null ? '—' : w.unit === '%' ? n_(v, 2) : w.unit === 'bp' ? n_(v, 0) : n_(v, 2)}</td>`).join('')}</tr>`).join('')}</table></div></details>`;
    const ex = `<details style="margin-top:6px"><summary class="small"><b>📖 판단 예시 4가지</b></summary><ol class="small">
      <li><b>실질금리만 상승 · 신용 안정</b> → 기업 부실보다 금리·밸류에이션 충격을 먼저 검토</li>
      <li><b>CCC·하이일드 확대</b> → 위험기업 자금조달 압박·부실 가능성 집중 점검</li>
      <li><b>우량채까지 확대 + 단기자금시장 불안</b> → 신용시장 전반 확산 여부 확인 · 차입·레버리지·유동성 재점검</li>
      <li><b>VIX만 급등 · 신용·자금시장 안정</b> → 주가 급락만으로 금융시스템 위기라 결론 내리지 않기</li></ol>
      <div class="mk-sub">폭락이 언제 오는지 아는 사람보다, 폭락이 와도 팔지 않아도 되는 사람이 훨씬 강하다 — 지표가 경고할 때 내 보유 기업의 현금 · 2년 내 채무 만기 · 차입비용 · 현금흐름을 확인하세요.${opt.pfLink ? ' <a href="#pf">💼 내 포트폴리오의 \'버팀\' 확인 ›</a>' : ''}</div></details>`;
    return `${nar}<section class="mk-card s8">${head}${tbl}${wk}${ex}<div class="mk-foot">${e_(S8.note)} · ${e_(S8.src)}</div></section>`;
  }
  function recessionCard(R) {
    return card(`💰 경기침체 선행지표 — 은행이 돈줄을 잠그고 있나요? ${badge(R.trig >= 2 ? 'bad' : R.trig || R.warn >= 2 ? 'warn' : 'ok', R.badge)}`, `<div class="mk-big2" style="font-size:18px">${esc(R.title)}</div>
      <div class="ust-g3">${R.sig.map(s => `<div class="ust-kv st-${{ crisis: 'bad', danger: 'bad', warning: 'warn', neutral: 'na', ok: 'ok', na: 'na' }[s.lv]}"><div class="mk-sub">${esc(s.name)}</div><div class="mk-fv">${s.v == null ? '—' : fN(s.v, s.unit === 'bp' ? 0 : 1) + s.unit}</div>${badge({ crisis: 'bad', danger: 'bad', warning: 'warn', neutral: 'na', ok: 'ok', na: 'na' }[s.lv], s.label)}<div class="mk-sub">${esc(s.hint)}</div></div>`).join('')}</div>
      <div class="small" style="margin-top:8px"><b>🌱 신용위기의 끝 감지</b> — ${R.end.map(e => `${esc(e.name)}: <b>${esc(e.label || '자료 없음')}</b>`).join(' · ')}</div>
      <div class="small" style="margin-top:6px">신용 수축 고리: 은행 대출 축소 → 기업 투자 ↓ → 고용 ↓ → 소비 ↓ → 실적 ↓ → 부도 ↑ → 은행이 더 조임</div>
      <details class="small" style="margin-top:6px"><summary>🧠 ‘금리 인하 = 호재’는 왜 틀릴 수 있을까?</summary>돈의 가격(금리)이 내려가도 돈의 문(은행 대출 심사)이 닫혀 있으면 돈이 실물로 흘러가지 않아요. 경기침체는 뉴스에서 발표되기 전에 은행 대출 창구에서 먼저 시작돼요.
        <br><b>틀릴 수 있는 이유</b>: SLOOS는 분기 조사(늦음) · 대출 잔액은 경기에 늦게 반응 · 하이일드 스프레드는 유동성에 민감 · 과거 패턴이 반복된다는 보장 없음</details>
      <div class="mk-foot">SLOOS ${esc(R.sloos_date || '')} 조사 · 대기업 C&I ${R.sloos_ci == null ? '—' : sgn(R.sloos_ci, 1) + '%p'} · 전체 ${R.sloos_all == null ? '—' : sgn(R.sloos_all, 1) + '%p'} (분기 변화 ${R.sloos_q == null ? '—' : sgn(R.sloos_q, 1)} ${esc(R.sloos_trend || '')}) · 기준: +10%p 이하 완화적 / +10~20 조짐 / +20 이상 뚜렷한 긴축 / +40 이상 신용경색<br>${R.src.map(l => src(l.label, l.url)).join(' ')}</div>`);
  }

  // ══ 2. 입찰 결과 ══════════════════════════════════════════════
  const gcol = g => ({ A: 'ok', B: 'ok', C: 'warn', D: 'bad' }[g] || 'na');
  function tAuc(D) {
    const A = D.auctions, rows = A.rows;
    const a = rows[Math.min(ST.sel, rows.length - 1)];
    return `<div class="ust-g4">${kv('평균 응찰배율 (최근 20건)', fN(A.avg_btc, 2) + '배', '2.5배↑ 강함 · 2.0배↓ 약함', A.avg_btc >= 2.5 ? 'ok' : A.avg_btc >= 2.0 ? 'warn' : 'bad')}
        ${kv('평균 Primary Dealer 낙찰', pc(A.avg_dealer), `중장기물만 ${pc(A.coupon_avg_dealer)} (판정 기준)`, A.coupon_avg_dealer > 25 ? 'bad' : A.coupon_avg_dealer > 15 ? 'warn' : 'ok')}
        ${kv('평균 Indirect Bidder 낙찰', pc(A.avg_indirect), 'Primary Dealer를 통한 국내외 고객 주문 — 외국인만이 아님', A.avg_indirect >= 60 ? 'ok' : A.avg_indirect >= 50 ? 'warn' : 'bad')}${kv('평균 Direct Bidder 낙찰', pc(A.avg_direct), '', '')}</div>
      <div class="mk-foot">단기채(Bill)는 원래 Primary Dealer 비중이 높아서, 위험 판정(배관도·연쇄 등급)은 <b>중장기물(Note·Bond) 최근 12건</b>(평균 응찰 ${fN(A.coupon_avg_btc, 2)}배 · Primary Dealer ${pc(A.coupon_avg_dealer)})으로 해요.</div>
      ${card('📋 최근 입찰 결과', `<div class="tablewrap" style="max-height:420px;overflow:auto"><table class="t"><tr><th>날짜</th><th>종류</th><th>만기</th><th class="r">최고 낙찰금리</th><th class="r">응찰배율</th><th class="r">Primary Dealer</th><th class="r">Indirect Bidder</th><th class="r">Direct Bidder</th><th class="r">규모</th><th>등급</th></tr>
        ${rows.map((r, i) => `<tr class="ust-row" onclick="this.dispatchEvent(new CustomEvent('pick',{bubbles:true}))" data-i="${i}"><td class="mono">${esc(r.date)}</td><td>${esc(r.type_kr)}${r.reopening ? ' <span class="mk-sub">재개행</span>' : ''}</td><td>${esc(r.label || r.term)}</td><td class="r mono">${fN(r.type === 'Bill' ? r.disc_high : r.y_high, 3)}%</td>
          <td class="r mono ${r.btc >= 2.5 ? 'ok' : r.btc >= 2.0 ? 'warn' : 'bad'}">${fN(r.btc, 2)}</td><td class="r mono ${r.dealer > 25 ? 'bad' : r.dealer > 18 ? 'warn' : 'ok'}">${pc(r.dealer)}</td><td class="r mono">${pc(r.indirect)}</td><td class="r mono">${pc(r.direct)}</td><td class="r mono">${usd(r.accepted)}</td><td>${badge(gcol(r.grade), r.grade)}</td></tr>`).join('')}</table></div>
        <div class="mk-foot">등급: A 응찰 2.5배↑·Primary Dealer 18%↓ · B 2.2배↑·22%↓ · C 2.0배↑·28%↓ · D 그 외. 줄을 누르면 아래 신문형 리포트가 그 입찰로 바뀌어요. 테일(낙찰금리 − 발행 전 시세)은 발행 전 시세(WI) 자료가 공개되지 않아 계산하지 않아요.</div>${foot(A.src)}`)}
      ${a ? newsPaper(a) : ''}
      ${card('📈 중장기물(Note·Bond) 응찰배율 흐름 <span class="mk-sub">점선 = 2.5배 (강한 수요 기준)</span>', (() => { const k = rows.filter(r => r.type !== 'Bill').slice().reverse(); return k.length > 1 ? lineSvg(k.map(r => [r.date, r.btc]), { h: 140, ref: 2.5, fmt: v => fN(v, 2) + '배' }) : '<div class="mk-empty">자료 부족</div>'; })())}`;
  }
  // ── 📰 TREASURY NEWS — 미 재무부 입찰 결과 보도자료 양식 (한국어 해설 포함) ──────────
  const TN_CSS = `
.tn{background:#fff;color:#111;border-radius:6px;padding:22px 24px;font:13px/1.55 "Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.tn *{box-sizing:border-box}.tn a{color:#175cd3}
.tn-mast{display:grid;grid-template-columns:1fr auto auto;gap:14px;align-items:center;border-top:3px solid #111;padding-top:6px}
.tn-mast h1{font:900 46px/1 Georgia,"Times New Roman",serif;letter-spacing:.14em;margin:0;border-bottom:3px solid #111;padding-bottom:4px}
.tn-mast .dept{font:600 13px Georgia,serif;letter-spacing:.12em;margin-top:4px}
.tn-seal{width:96px;height:96px}
.tn-badge{border:2px solid #1f4fa0;border-radius:10px;text-align:center;overflow:hidden;min-width:170px}
.tn-badge b{display:block;background:#1f4fa0;color:#fff;font-size:16px;padding:6px 10px;line-height:1.3}.tn-badge span{display:block;padding:6px 8px;font-weight:700;font-size:15px}
.tn-rel{display:flex;justify-content:space-between;gap:10px;font:13px Georgia,serif;margin:10px 0 4px}
.tn-h{text-align:center;font:800 24px Georgia,serif;margin:6px 0 2px}.tn-h small{display:block;font:800 18px "Malgun Gothic",sans-serif}
.tn-body{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(0,1fr);gap:14px;margin-top:10px}
.tn table{width:100%;background:#fff;color:#111;border-collapse:collapse;font-size:13px}.tn td,.tn th{background:#fff;color:#111;font-size:13px;border:1px solid #9a9a9a;padding:5px 8px;vertical-align:middle}
.tn th{background:#f3f3f3;font-weight:700;text-align:center}.tn td.tn-n{text-align:right;font-family:Georgia,"Times New Roman",serif;white-space:nowrap}
.tn td.tn-k{font-family:Georgia,serif}.tn td.tn-k em{color:#d92d20;font-style:normal;font-family:"Malgun Gothic",sans-serif;margin-left:8px}
.tn td.tn-v{text-align:center;font-family:Georgia,serif}.tn th em{display:block;color:#d92d20;font-style:normal;font-weight:700}
.tn tr.sub td{background:#fff36b;font-weight:800}.tn tr.soma td{background:#d6ecff}.tn tr.tot td{font-weight:800}
.tn .dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.tn .d-c{background:#16a34a}.tn .d-n{background:#f97316}.tn .d-f{background:#7c3aed}.tn .d-s{background:#2563eb}
.tn-fn{font:12px/1.5 Georgia,serif;margin-top:8px}.tn-fn div{margin:1px 0}.tn-fn .hl{background:#fff36b;display:inline}
.tn-side{display:flex;flex-direction:column;gap:10px}
.tn-box{border:2px solid var(--b);border-radius:10px;background:var(--bg);padding:10px 12px}
.tn-box h4{margin:0 0 6px;color:var(--b);font-size:17px}.tn-box ul{margin:0;padding-left:16px}.tn-box li{margin:3px 0}
.tn-red{--b:#e0574f;--bg:#fff5f4}.tn-ora{--b:#f0a35e;--bg:#fff8ef}.tn-grn{--b:#4caf50;--bg:#f3fbf2}.tn-yel{--b:#e6b800;--bg:#fffbe6}.tn-blu{--b:#3b82f6;--bg:#f1f6ff}.tn-pur{--b:#a855f7;--bg:#faf5ff}
.tn-big{font-size:34px;font-weight:900;color:#d92d20;line-height:1.1}
.tn-bot{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}
.tn-bot2{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:10px;margin-top:10px}
.tn-bot .tn-box table td,.tn-bot .tn-box table th{font-size:12.5px;padding:4px 6px}
.tn .up{color:#d92d20;font-weight:700}.tn .dn{color:#1d4ed8;font-weight:700}.tn .mut{color:#666;font-size:12px}
@media (max-width:900px){.tn-body,.tn-bot,.tn-bot2{grid-template-columns:1fr}.tn-mast{grid-template-columns:1fr}.tn-mast h1{font-size:32px}}
@media print{.tn{padding:0}.tn-box,.tn table{break-inside:avoid}}`;
  const USD = v => v == null || !isFinite(v) ? '—' : '$' + Math.round(v).toLocaleString('en-US');
  const ENG_D = d => { if (!d) return '—'; const x = new Date(d + 'T00:00:00'); return x.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); };
  const KOR_D = d => { if (!d) return '—'; const x = new Date(d + 'T00:00:00'); return `${x.getFullYear()}년 ${x.getMonth() + 1}월 ${x.getDate()}일 (${'일월화수목금토'[x.getDay()]})`; };
  const KOR_MD = d => { const x = new Date(d + 'T00:00:00'); return `${x.getMonth() + 1}월 ${x.getDate()}일`; };
  const P3 = v => v == null ? '—' : fN(v, 3) + '%';
  const SEAL = `<svg class="tn-seal" viewBox="0 0 100 100" aria-label="재무부 인장"><circle cx="50" cy="50" r="47" fill="#fff" stroke="#111" stroke-width="3"/><circle cx="50" cy="50" r="33" fill="none" stroke="#111" stroke-width="1.5"/>
    <defs><path id="tnArc" d="M50,50 m-40,0 a40,40 0 1,1 80,0 a40,40 0 1,1 -80,0"/></defs><text font-size="7.6" font-weight="700" font-family="Georgia" letter-spacing="1.2"><textPath href="#tnArc" startOffset="2%">THE DEPARTMENT OF THE TREASURY • 1789 •</textPath></text>
    <path d="M30 40 h40 M50 33 v34 M36 40 l-6 14 h12 z M64 40 l-6 14 h12 z" fill="none" stroke="#111" stroke-width="2"/><path d="M36 60 h28 v6 h-28z" fill="#111"/><circle cx="50" cy="32" r="2.5" fill="#111"/></svg>`;

  function newsPaper(a) {
    const D = ST.D.auctions.rows, bill = a.type === 'Bill', p = a.prev;
    const r = (x, y) => y ? x / y * 100 : null;            // 비중 = 경쟁입찰 낙찰 합계 대비 (재무부 방식)
    const compA = a.comp_a, btc = a.sub_a ? a.sub_t / a.sub_a : a.btc;
    const sh = { pd: r(a.pd_a, compA), dir: r(a.dir_a, compA), ind: r(a.ind_a, compA), fima: r(a.fima_a, compA) };
    const hi = bill ? a.disc_high : a.y_high, lab = bill ? 'Rate' : 'Yield';
    const kTerm = bill ? `${a.days}일 만기 단기국채` : { Note: '중기 국채', Bond: '장기 국채', TIPS: '물가연동 국채', FRN: '변동금리 국채' }[a.type] || '국채';
    const top = [
      ['Term and Type of Security', '만기 및 증권 종류', `${esc(a.label)}<br><span class="mut">(${esc(kTerm)}${a.reopening ? ' · 재개행' : ''})</span>`],
      ['CUSIP Number', '증권식별번호', esc(a.cusip)],
      [`High ${lab} <sup>1</sup>`, bill ? '최고 낙찰 할인율' : '최고 낙찰 수익률', P3(hi)],
      ...(bill ? [] : [['Interest Rate', '표면금리(쿠폰)', P3(a.coupon)]]),
      ['Allotted at High', '최고금리 배정비율', a.alloc_high == null ? '—' : fN(a.alloc_high, 2) + '%'],
      ['Price', '발행 가격 (100달러 기준)', a.price == null ? '—' : fN(a.price, 6)],
      ...(bill ? [['Investment Rate <sup>2</sup>', '투자수익률 (연환산)', P3(a.inv_rate)]] : []),
      [`Median ${lab} <sup>${bill ? 3 : 2}</sup>`, bill ? '중간 낙찰 할인율' : '중간 낙찰 수익률', P3(bill ? a.disc_med : a.y_med)],
      [`Low ${lab} <sup>${bill ? 4 : 3}</sup>`, bill ? '최저 낙찰 할인율' : '최저 낙찰 수익률', P3(bill ? a.disc_low : a.y_low)],
      ['Issue Date', '발행일', ENG_D(a.issue)], ['Maturity Date', '만기일', ENG_D(a.maturity)]];
    const fnN = bill ? 5 : 4;
    const fns = [`<sup>1</sup>All tenders at lower ${bill ? 'rates' : 'yields'} were accepted in full.`, ...(bill ? ['<sup>2</sup>Equivalent coupon-issue yield.'] : []),
      `<sup>${bill ? 3 : 2}</sup>50% of the amount of accepted competitive tenders was tendered at or below that ${bill ? 'rate' : 'yield'}.`,
      `<sup>${bill ? 4 : 3}</sup>5% of the amount of accepted competitive tenders was tendered at or below that ${bill ? 'rate' : 'yield'}.`,
      `<span class="hl"><sup>${fnN}</sup>Bid-to-Cover Ratio: ${USD(a.sub_t)}/${USD(a.sub_a)} = ${fN(btc, 2)}</span>`,
      `<sup>${fnN + 1}</sup>Awards to Treasury Retail = ${USD(a.retail)}.`,
      `<sup>${fnN + 2}</sup>For descriptions of these terms, see the Auction FAQs available at <a href="https://www.treasurydirect.gov/help-center/faqs/auction-faqs/" target="_blank" rel="noopener">https://www.treasurydirect.gov/help-center/faqs/auction-faqs/</a>.`];
    // 직전 같은 만기 비교
    const pv = p ? { hi: bill ? p.disc_high : p.y_high, inv: p.inv_rate, btc: p.btc, ind: p.comp_a ? p.ind_a / p.comp_a * 100 : null } : null;
    const chg = (now, was, unit, dec) => { if (now == null || was == null) return '—'; const d = now - was; return `<span class="${d > 0 ? 'up' : d < 0 ? 'dn' : ''}">${d >= 0 ? '+' : ''}${fN(d, dec)}${unit}${d > 0 ? ' ↑' : d < 0 ? ' ↓' : ''}</span>`; };
    const cmpRows = pv ? [[bill ? '최고 낙찰 할인율' : '최고 낙찰 수익률', P3(pv.hi), P3(hi), chg(hi, pv.hi, '%p', 3)], ...(bill ? [['투자수익률', P3(pv.inv), P3(a.inv_rate), chg(a.inv_rate, pv.inv, '%p', 3)]] : []),
      ['응찰률', fN(pv.btc, 2) + '배', fN(btc, 2) + '배', chg(btc, pv.btc, '배', 2)], ['Indirect Bidder 비중', pc(pv.ind), pc(sh.ind), chg(sh.ind, pv.ind, '%p', 1)]] : [];
    // 해석 및 시사점
    const imp = [];
    if (pv && hi != null && pv.hi != null) { const d = hi - pv.hi; imp.push(`<b>${bill ? '최고 낙찰 할인율과 투자수익률' : '최고 낙찰 수익률'}</b>이 ${KOR_MD(p.date)}보다 ${Math.abs(d) < 0.01 ? '비슷해' : d > 0 ? '높아져, 미국 정부의 ' + (bill ? '단기 ' : '') + '차입금리 부담이 커졌어요' : '낮아져, 정부의 차입 부담이 줄었어요'}${Math.abs(d) < 0.01 ? ' 큰 변화가 없어요' : ''}.`); }
    if (pv) imp.push(`<b>응찰률</b>은 ${fN(pv.btc, 2)}배에서 ${fN(btc, 2)}배로 ${btc < pv.btc - 0.05 ? '하락해 수요 경쟁이 약해졌어요' : btc > pv.btc + 0.05 ? '상승해 수요 경쟁이 강해졌어요' : '비슷한 수준이에요'}.`);
    imp.push(`<b>Indirect Bidder 비중</b>이 ${pc(sh.ind)}로 ${sh.ind >= 60 ? '높게 나타나, Primary Dealer를 통한 국내외 고객 주문이 큰 비중을 차지하고 있어요' : sh.ind >= 45 ? '평균 수준이에요' : '낮아 최종 투자자 수요가 약해 보여요'} (Indirect Bidder = 국내외 고객 주문 — 외국인만이 아니에요).`);
    if (sh.pd > 25) imp.push(`<b>Primary Dealer</b>가 ${pc(sh.pd)}를 떠안았어요 — ${bill ? '단기채는 원래 Primary Dealer 비중이 높은 편이지만' : '중장기물에서'} 25%를 넘으면 시장 수요가 부족했다는 신호예요.`);
    return `<section class="mk-card ust-paper" id="uPaper"><div class="ust-paper-h"><select id="uSel" class="ust-sel">${D.slice(0, 30).map((x, i) => `<option value="${i}" ${i === ST.sel ? 'selected' : ''}>${esc(x.date)} · ${esc(x.label || x.term)} · 응찰 ${fN(x.btc, 2)}배</option>`).join('')}</select>
        <button class="btn sm" id="uPrint">🖨️ 인쇄 · PDF로 저장</button></div>
      <style>${TN_CSS}</style>
      <div id="uNews" class="tn">
        <div class="tn-mast"><div><h1>TREASURY NEWS</h1><div class="dept">Department of the Treasury • Bureau of the Fiscal Service</div></div>${SEAL}
          <div class="tn-badge"><b>미국 재무부<br>국채 입찰 결과</b><span>${KOR_D(a.date)}<br>(원문 기준)</span></div></div>
        <div class="tn-rel"><div>For Immediate Release<br>${ENG_D(a.date)}</div><div style="text-align:right">CONTACT: Treasury Auctions<br>202-504-3550</div></div>
        <div class="tn-h">TREASURY AUCTION RESULTS<small>미국 재무부 국채 입찰 결과</small></div>
        <div class="tn-body"><div>
          <table>${top.map(([k, kr, v]) => `<tr><td class="tn-k">${k}<em>${kr}</em></td><td class="tn-v">${v}</td></tr>`).join('')}</table>
          <table style="margin-top:8px"><tr><th></th><th>Tendered<em>(응찰 금액)</em></th><th>Accepted<em>(낙찰 금액)</em></th></tr>
            <tr><td class="tn-k"><span class="dot d-c"></span>Competitive<em>경쟁 입찰자</em></td><td class="tn-n">${USD(a.comp_t)}</td><td class="tn-n">${USD(a.comp_a)}</td></tr>
            <tr><td class="tn-k"><span class="dot d-n"></span>Noncompetitive<em>비경쟁 입찰자</em></td><td class="tn-n">${USD(a.nc_a)}</td><td class="tn-n">${USD(a.nc_a)}</td></tr>
            <tr><td class="tn-k"><span class="dot d-f"></span>FIMA (Noncompetitive)<em>FIMA(비경쟁)</em></td><td class="tn-n">${USD(a.fima_t)}</td><td class="tn-n">${USD(a.fima_a)}</td></tr>
            <tr class="sub"><td class="tn-k">Subtotal<em>소계 (SOMA 제외)</em></td><td class="tn-n">${USD(a.sub_t)}</td><td class="tn-n">${USD(a.sub_a)}</td></tr>
            <tr class="soma"><td class="tn-k"><span class="dot d-s"></span>SOMA<em>연준 보유분</em></td><td class="tn-n">${USD(a.soma_t)}</td><td class="tn-n">${USD(a.soma_a)}</td></tr>
            <tr class="tot"><td class="tn-k">Total<em>총계 (SOMA 포함)</em></td><td class="tn-n">${USD(a.tendered)}</td><td class="tn-n">${USD(a.accepted)}</td></tr></table>
          <table style="margin-top:8px"><tr><th></th><th>Tendered<em>(응찰 금액)</em></th><th>Accepted<em>(낙찰 금액)</em></th><th>비중 (%)</th></tr>
            <tr><td class="tn-k">Primary Dealer<em>뉴욕 연은 지정 국채 딜러(증권회사)</em></td><td class="tn-n">${USD(a.pd_t)}</td><td class="tn-n">${USD(a.pd_a)}</td><td class="tn-n">${pc(sh.pd)}</td></tr>
            <tr><td class="tn-k">Direct Bidder<em>기관이 자기 계정으로 직접 입찰</em></td><td class="tn-n">${USD(a.dir_t)}</td><td class="tn-n">${USD(a.dir_a)}</td><td class="tn-n">${pc(sh.dir)}</td></tr>
            <tr><td class="tn-k">Indirect Bidder<em>Primary Dealer를 통한 국내외 고객 주문</em></td><td class="tn-n">${USD(a.ind_t)}</td><td class="tn-n">${USD(a.ind_a)}</td><td class="tn-n">${pc(sh.ind)}</td></tr>
            <tr class="tot"><td class="tn-k">Total Competitive<em>경쟁입찰 합계</em></td><td class="tn-n">${USD(a.comp_t)}</td><td class="tn-n">${USD(a.comp_a)}</td><td class="tn-n">100.0%</td></tr></table>
          <div class="tn-fn">${fns.map(f => `<div>${f}</div>`).join('')}</div>
        </div><div class="tn-side">
          <div class="tn-box tn-red"><h4>상단 주요 항목 설명</h4><ul>
            <li><b>High ${lab}</b> (최고 낙찰 ${bill ? '할인율' : '수익률'}): 낙찰된 가장 높은 ${bill ? '할인율' : '수익률'}(금리). 이보다 낮은 금리로 응찰한 물량은 모두 낙찰됨.</li>
            <li><b>Allotted at High</b>: 최고금리에서 배정된 비율. (예: ${a.alloc_high == null ? '—' : fN(a.alloc_high, 2) + '%'} = 최고금리 응찰 물량의 ${a.alloc_high == null ? '—' : fN(a.alloc_high, 2) + '%'}만 배정)</li>
            <li><b>Price</b>: 100달러 액면가 기준 실제 발행 가격.</li>
            ${bill ? '<li><b>Investment Rate</b>: 투자수익률(연환산, Bond Equivalent Yield). 실제 투자자가 얻게 되는 연간 수익률.</li>' : '<li><b>Interest Rate</b>: 매년 받는 이자(쿠폰). 낙찰 수익률 > 쿠폰이면 100달러보다 싸게 발행돼요.</li>'}
            <li><b>Median ${lab}</b>: 중간 낙찰 ${bill ? '할인율' : '수익률'}. 낙찰된 물량의 중간에 해당하는 금리.</li>
            <li><b>Low ${lab}</b>: 최저 낙찰 ${bill ? '할인율' : '수익률'}. 가장 낮게 낙찰된 금리.</li></ul>
            ${bill ? '<div style="margin-top:4px">할인율이 높을수록 발행 가격은 낮아지고, 투자수익률은 높아져요.</div>' : ''}</div>
          <div class="tn-box tn-ora"><h4>응찰자 종류 설명</h4>
            <div><span class="dot d-c"></span><b>Competitive</b> (경쟁 입찰자) — 일반 투자자, 시장 금리로 응찰 (High ${lab} 적용)</div>
            <div><span class="dot d-n"></span><b>Noncompetitive</b> (비경쟁 입찰자) — 소액 투자자, 금리를 정하지 않고 응찰 (High ${lab} 적용)</div>
            <div><span class="dot d-f"></span><b>FIMA</b> (비경쟁, 해외 중앙은행 등) — 해외 중앙은행 등 FIMA 계정의 비경쟁 응찰</div>
            <div><span class="dot d-s"></span><b>SOMA</b> (연방준비제도 보유분) — 연준의 통화정책 목적 보유 (통계 계산 시 제외)</div></div>
          <div class="tn-box tn-grn"><h4>낙찰자별 비중 설명</h4><ul>
            <li><b>Primary Dealer</b>: 뉴욕 연은이 지정한 국채 딜러(증권회사). 모든 입찰에 합리적 가격으로 참여할 의무 — 시장 조성·인수 담당.</li>
            <li><b>Direct Bidder</b>: Primary Dealer를 거치지 않고 기관이 자기 계정으로 직접 입찰한 물량.</li>
            <li><b>Indirect Bidder</b>: Primary Dealer를 통해 들어온 고객 주문. 외국 중앙은행·해외 기관도 포함되지만 국내 고객 주문도 들어가요 — <b>Indirect Bidder = 외국인이 아니에요</b>. 실제 해외 몫은 「🧲 흡수력」 탭의 투자자 유형별 배정에서 확인.</li></ul>
            <div class="mut" style="margin-top:4px">비중 = 각 낙찰 금액 ÷ 경쟁입찰 낙찰 합계 ${USD(compA)}</div></div>
          <div class="tn-box tn-yel"><h4>응찰률 (Bid-to-Cover Ratio)</h4><div>총 응찰 금액 ÷ 총 낙찰 금액 (SOMA 제외)</div><div class="tn-big">= ${fN(btc, 2)}배</div>
            <div>발행 예정 금액 대비 약 ${fN(btc, 2)}배의 자금이 응찰했다는 의미예요. (수요가 많을수록 응찰률이 높음)</div></div>
        </div></div>
        <div class="tn-bot">
          <div class="tn-box tn-pur"><h4>핵심 수치 요약</h4><table>
            <tr><td>만기</td><td>${esc(a.label)}${bill ? ` (${a.days}일)` : ''}</td></tr><tr><td>최고 낙찰 ${bill ? '할인율' : '수익률'}</td><td>${P3(hi)}</td></tr>
            ${bill ? `<tr><td>투자수익률</td><td>${P3(a.inv_rate)}</td></tr>` : `<tr><td>표면금리(쿠폰)</td><td>${P3(a.coupon)}</td></tr>`}
            <tr><td>중간 낙찰 ${bill ? '할인율' : '수익률'}</td><td>${P3(bill ? a.disc_med : a.y_med)}</td></tr><tr><td>최저 낙찰 ${bill ? '할인율' : '수익률'}</td><td>${P3(bill ? a.disc_low : a.y_low)}</td></tr>
            <tr><td>발행 가격</td><td>${a.price == null ? '—' : fN(a.price, 6)} (100달러 기준)</td></tr><tr><td>응찰률</td><td>${fN(btc, 2)}배</td></tr></table></div>
          <div class="tn-box tn-blu"><h4>${p ? `${KOR_MD(p.date)}${p.days && bill ? `(${p.days}일)` : ''}과 비교` : '직전 같은 만기와 비교'}</h4>${p ? `<table><tr><th>항목</th><th>${esc(p.date)}${bill && p.days ? `<br>(${p.days}일)` : ''}</th><th>${esc(a.date)}${bill ? `<br>(${a.days}일)` : ''}</th><th>변화</th></tr>
            ${cmpRows.map(rw => `<tr><td>${rw[0]}</td><td class="tn-n">${rw[1]}</td><td class="tn-n">${rw[2]}</td><td class="tn-n">${rw[3]}</td></tr>`).join('')}</table>` : '<div class="mut">최근 자료에 같은 만기 입찰이 없어요.</div>'}</div>
          <div class="tn-box tn-grn"><h4>해석 및 시사점</h4><ul>${imp.map(t => `<li>${t}</li>`).join('')}</ul></div>
        </div>
        <div class="tn-bot2">
          <div class="tn-box tn-grn"><h4>주요 지표 해석</h4><ul>
            <li><b>응찰률 ${fN(btc, 2)}배</b>: 발행 예정 금액보다 약 ${fN(btc, 1)}배 많은 자금이 응찰 → ${btc >= 2.5 ? '수요 양호' : btc >= 2.0 ? '수요 보통' : '수요 부진'}</li>
            <li><b>Indirect Bidder 비중</b>: ${pc(sh.ind)} (${USD(a.ind_a).slice(1)} / ${USD(compA).slice(1)}) → ${sh.ind >= 60 ? '최종 투자자(국내외 고객 주문) 수요가 큰 비중을 차지' : '최종 투자자 수요는 평소 수준 이하'} · 실제 해외 몫은 「🧲 흡수력」 탭의 투자자 유형별 배정에서 확인</li>
            <li><b>Primary Dealer 비중</b>: ${pc(sh.pd)} (${USD(a.pd_a).slice(1)} / ${USD(compA).slice(1)})</li>
            <li><b>Direct Bidder 비중</b>: ${pc(sh.dir)} (${USD(a.dir_a).slice(1)} / ${USD(compA).slice(1)})</li>
            <li><b>FIMA 비중</b>: ${fN(sh.fima, 2)}% (${USD(a.fima_a).slice(1)} / ${USD(compA).slice(1)})</li></ul>
            <div style="margin-top:6px"><b>📝 종합 해설</b> — ${esc(a.comment || '')}</div></div>
          <div class="tn-side"><div class="tn-box tn-blu"><h4>참고: SOMA란?</h4>연준(Fed)이 통화정책 목적으로 보유하는 국채예요. 시장 수요를 분석할 때는 SOMA를 제외하고 계산해요.</div>
            <div class="tn-box tn-pur"><h4>FIMA란?</h4>해외 중앙은행 및 국제통화당국(Foreign and International Monetary Authorities)의 계정으로, 주로 외국 정부의 달러 보유 및 준비금 운용 목적의 비경쟁 입찰이에요.</div>
            ${a.pdf ? `<div class="mut">원문: <a href="${esc(a.pdf)}" target="_blank" rel="noopener">재무부 공식 결과 PDF ↗</a> · 자료: 미 재무부 Fiscal Data (auctions_query)</div>` : ''}</div>
        </div>
      </div></section>`;
  }
  function printNews() {
    const el = document.getElementById('uNews'); if (!el) return;
    const w = window.open('', '_blank'); if (!w) { alert('팝업이 막혀 있어요 — 허용해 주세요.'); return; }
    const a = ST.D.auctions.rows[ST.sel];
    w.document.write(`<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Treasury News ${esc(a.date)} ${esc(a.label || '')}</title><style>@page{size:A4;margin:8mm}body{margin:0;background:#fff}${TN_CSS}</style></head><body>${el.outerHTML}<script>setTimeout(()=>print(),400)<\/script></body></html>`);
    w.document.close();
  }
  document.addEventListener('pick', e => { const tr = e.target.closest('[data-i]'); if (tr) { ST.sel = +tr.dataset.i; draw(); const p = document.getElementById('uPaper'); if (p) p.scrollIntoView({ behavior: 'smooth' }); } });

  // ══ 3. 입찰 붕괴 연쇄반응 ═══════════════════════════════════════
  function tChain(D) {
    const C = D.chain, A = D.auctions, L = D.liq;
    const bar = (v, max, st) => `<div class="ust-bar"><i class="st-${st}" style="width:${Math.max(5, Math.min(100, v / max * 100))}%"></i></div>`;
    const btc = A.coupon_avg_btc, dl = A.coupon_avg_dealer;
    return `<div class="ust-g4">
        <div class="mk-card">${kv('경보 1 · 응찰배율', fN(btc, 2) + '배', '중장기물 평균 · 2.5↑ 양호 / 2.0↓ 위험', btc >= 2.5 ? 'ok' : btc >= 2.0 ? 'warn' : 'bad')}${bar(btc || 0, 3, btc >= 2.5 ? 'ok' : btc >= 2.0 ? 'warn' : 'bad')}</div>
        <div class="mk-card">${kv('경보 2 · Primary Dealer 떠안음', pc(dl), '15%↓ 양호 / 25%↑ 위험', dl < 15 ? 'ok' : dl < 25 ? 'warn' : 'bad')}${bar(40 - (dl || 0), 40, dl < 15 ? 'ok' : dl < 25 ? 'warn' : 'bad')}</div>
        <div class="mk-card">${(() => { const T = D.absorb && D.absorb.three; return T ? kv('경보 3 · 테일 (근사)', `${T.tail.n1}/${T.tail.n}건`, `최근 45일 중장기물 입찰 중 평소보다 2bp 이상 꼬리 · 최대 ${T.tail.max == null ? '—' : sgn(T.tail.max, 1) + 'bp'}`, T.tail.flag ? 'bad' : T.tail.n1 ? 'warn' : 'ok') : kv('경보 3 · 테일', '—', '자료 없음', ''); })()}</div>
        <div class="mk-card">${kv('경보 4 · 2차 시장 유동성', L.rrp_now == null ? '—' : B(L.rrp_now), `역레포 ${esc(L.rrp_badge || '')} · MOVE ${fN(D.contra.move, 0)}`, L.rrp_st)}</div></div>
      <div class="mk-card st-${C.grade <= 'B' ? 'ok' : C.grade === 'C' ? 'warn' : 'bad'}" style="margin-top:14px"><div class="mk-sub">입찰 건전성 종합 평가 — 위험 점수 ${C.risk}/100 (응찰 40 + 딜러 40 + 역레포 20)</div>
        <div class="mk-big2">${esc(C.grade)} · ${esc(C.grade_kr)}</div><div class="ust-bar"><i class="st-${C.risk <= 35 ? 'ok' : C.risk <= 55 ? 'warn' : 'bad'}" style="width:${C.risk}%"></i></div><div class="small">${esc(C.grade_desc)}</div></div>
      ${card('🚨 실전 모니터링 — 위험 신호', `<table class="t">${C.watch.map(w => `<tr><td>${w.on ? '<b class="bad">● 켜짐</b>' : '<span class="mk-sub">○ 꺼짐</span>'}</td><td>${esc(w.t)}${w.v != null ? ` <span class="mk-sub">(${bp(w.v)})</span>` : ''}</td></tr>`).join('')}</table>
        <div class="small" style="margin-top:6px"><b class="bad">최악의 조합 (Red Alert)</b>: 입찰 부진 + 유동성 악화가 동시에</div>`)}
      ${card('💥 국채 입찰이 무너지면 제일 먼저 터지는 자산 순서 <span class="mk-sub">“가장 비싸고, 가장 먼 미래를 반영한 자산부터 무너진다”</span>', `<ol class="ust-chain">
        <li><b>장기 듀레이션 기술주</b> — 이익이 먼 미래에 있는 고평가 성장주(P/E 50↑·적자 기업). 현금이 많은 빅테크는 상대적으로 버텨요.</li>
        <li><b>국채 베이시스 트레이드</b> — 헤지펀드가 50~100배 레버리지로 국채 현물·선물 가격 차이를 노리는 거래(추정 $8천억~1조 달러 이상). 2020년 3월에 한 번 터졌어요.</li>
        <li><b>상업용 부동산(CRE)과 지역 은행</b> — CRE 대출이 자산의 30%를 넘는 중소은행. 사무실·상가·물류센터 순 (지역은행 ETF KRE로 확인).</li>
        <li><b>주택·모기지 → 소비</b> — 입찰 약화 → 장기금리 ↑ → 모기지 금리 ↑ → 주택 거래 위축 → 소비 둔화.</li></ol>
        <div class="mk-foot">근거: 미 재무부(Nellie Liang 연설) · FOMC 2026년 1월 의사록 · BIS · FSOC 2025 · IMF 국제금융안정보고서 (원본 대시보드 정리) · Primary Dealer 포지션은 ${'<a href="#secret">비밀지표 9 — Primary Dealer</a>'}에서 확인</div>`)}`;
  }

  // ══ 4. 이벤트 일정 ════════════════════════════════════════════
  function tCal(D) {
    const today = new Date().toLocaleDateString('sv-SE');
    const ev = D.events_auto.slice().sort((a, b) => a.date.localeCompare(b.date));
    const cnt = {}; ev.forEach(e => { cnt[e.date] = (cnt[e.date] || 0) + 1; });
    const clusters = Object.keys(cnt).filter(d => cnt[d] >= 2);
    const nextC = clusters.find(d => d >= today);
    const in7 = new Date(Date.now() + 7 * 864e5).toLocaleDateString('sv-SE');
    const aw = ev.filter(e => e.type === 'auction' && e.date >= today && e.date <= in7);
    const TY = { auction: '경매', policy: '정책', fed: 'Fed', rating: '신용등급', geopolitics: '지정학', other: '기타' };
    const IM = { high: '🔴', med: '🟡', low: '🟢' };
    return `<div class="ust-g4">${kv('클러스터 경보일 (최근 2주 + 앞으로 4주)', clusters.length + '일', nextC ? `다음: ${nextC} — ${ev.filter(e => e.date === nextC).slice(0, 3).map(e => esc(e.title)).join(' / ')}` : '앞으로 몰린 날 없음', clusters.length ? 'warn' : 'ok')}
        ${kv('이번 주 중장기물 입찰', aw.length + '건', aw[0] ? `다음: ${esc(aw[0].date)} ${esc(aw[0].title)}` : '없음', '')}${kv('이번 주 단기채(Bill) 입찰', D.bills_week + '건', 'MMF가 받쳐 주는 시장', '')}
        ${kv('다음 FOMC', D.fomc_next ? esc(D.fomc_next.date) : '—', D.fomc_next && D.fomc_next.sep ? '경제전망(점도표) 포함' : '', '')}</div>
      ${card('🗓️ 정책·시장 이벤트 타임라인 <span class="mk-sub">같은 날 2개 이상 = 클러스터 (변동성 커질 수 있는 날)</span>', `<table class="t">${ev.map(e => `<tr class="${e.date < today ? 'ust-past' : ''} ${cnt[e.date] >= 2 ? 'ust-clu' : ''}">
          <td class="mono" style="white-space:nowrap">${cnt[e.date] >= 2 ? '🔴 ' : ''}<b>${esc(e.date)}</b></td><td>${IM[e.imp] || ''}</td><td><span class="mk-badge st-na">${esc(TY[e.type] || e.type)}</span></td><td>${esc(e.title)}</td><td class="mk-sub">${esc(e.src)}</td></tr>`).join('')}</table>
        <div class="mk-foot">자동: 미 재무부 입찰 결과·예정(Fiscal Data) · FOMC(연준 공식 일정) · 일본은행 회의(공식 일정) · QRA는 재무부 관행(2·5·8·11월 첫째 주 월·수)으로 추정한 날짜예요. 물가·고용 발표일은 공개 일정 자료가 없어 직접 추가해 주세요.</div>`)}
      ${card('🏯 일본은행 회의 일정', D.japan.boj_list.length ? `<div class="small">${D.japan.boj_list.map(b => `<span class="mk-chiplink">${esc(b.date)}${b.outlook ? ' (전망보고서)' : ''}</span>`).join(' ')}</div>` : '<div class="mk-sub">일정을 받지 못했어요</div>')}`;
  }

  // ══ 5. 유동성 완충 ════════════════════════════════════════════
  function tLiq(D) {
    const L = D.liq, so = D.soma;
    return `<div class="ust-g4">${kv(tip('역레포 (ON RRP)', 'MMF 등이 남는 돈을 연준에 맡겨 둔 곳 — 시장의 비상용 물탱크'), L.rrp_now == null ? '—' : B(L.rrp_now), badge(L.rrp_st, L.rrp_badge) + ' $100B 이하 = 위험 수위', L.rrp_st)}
        ${kv(tip('TGA (정부 통장)', '재무부가 연준에 둔 통장. 늘면 시중 돈이 빨려 들어가고, 줄면 풀려요'), B(L.tga_now), `30일 ${L.tga_30 == null ? '—' : sgn(L.tga_30, 0) + 'B'} ${L.tga_30 > 0 ? '(시중 돈 흡수)' : '(시중에 방출)'}`, '')}
        ${kv(tip('은행 지준', '은행이 연준에 맡긴 돈 — 금융 시스템의 혈액량'), L.res_now == null ? '—' : '$' + fN(L.res_now, 2) + 'T', `13주 ${L.res_13w == null ? '—' : sgn(L.res_13w, 0) + 'B'}`, L.res_13w < -100 ? 'warn' : 'ok')}
        ${kv(tip('SRF (상설 레포)', '은행이 급할 때 연준에서 국채를 맡기고 돈을 빌리는 창구'), L.srf_now == null ? '—' : B(L.srf_now), '$0 정상 · $1~10B 경계 · $10B↑ 비상', L.srf_st)}</div>
      <div class="mk-grid2" style="margin-top:14px">${card('역레포 잔고 ($B)', lineSvg(L.rrp, { h: 150, area: true, fmt: v => B(v) }) + foot([L.src[0]]))}${card('TGA 잔고 ($B)', lineSvg(L.tga, { h: 150, area: true, fmt: v => B(v) }) + foot([L.src[1]]))}</div>
      <div class="mk-grid2" style="margin-top:14px">${card('은행 지준 ($T)', lineSvg(L.res, { h: 150, area: true, fmt: v => '$' + fN(v, 2) + 'T' }) + foot([L.src[2]]))}
        ${card('3단계 유동성 배관', `<ol class="ust-chain"><li><b>역레포 감소</b> — 남는 돈이 국채(T-Bill)로 옮겨 가는 단계. 아직 괜찮아요.</li><li><b>역레포 소진</b> — 물탱크가 비면 이제 은행 지준이 직접 줄어요.</li><li><b>경색</b> — 지준이 부족해지면 레포 금리가 튀어요 (2019년 9월).</li></ol>
          <div class="small">비유: 역레포 = 비상용 물탱크 · TGA = 정부 수도꼭지 · 지준 = 수도관 압력. <b>TGA가 줄었다고 곧바로 유동성 공급은 아니에요</b> — 세금 환급·지출 시점이 섞여 있어요.</div>`)}</div>
      ${so ? card(`🏦 연준 국채 보유(SOMA): T-Bill 집중 매입 감지 ${badge(so.st, so.badge)}`, `<div class="ust-g3">${kv('5주간 T-Bill 보유 변화', sgn(so.bills_chg, 1) + 'B', '')}${kv('5주간 전체 국채 변화', sgn(so.total_chg, 1) + 'B', '')}${kv('증가분 중 T-Bill 비중', pc(so.share_of_chg, 0), '80%↑ = Bills Pivot 확정 · 50~80 조짐 · 음수 = 정상 QT', so.st)}</div>
        <table class="t" style="margin-top:8px"><tr><th>주</th><th class="r">T-Bill</th><th class="r">주간 변화</th><th class="r">전체 국채</th><th class="r">T-Bill 비중</th></tr>${so.hist.map(h => `<tr><td class="mono">${esc(h.date)}</td><td class="r mono">${B(h.bills)}</td><td class="r mono ${h.wchg >= 5 ? 'bad' : h.wchg >= 0 ? 'warn' : 'ok'}">${sgn(h.wchg, 1)}B</td><td class="r mono">${h.total == null ? '—' : '$' + fN(h.total, 2) + 'T'}</td><td class="r mono">${pc(h.share)}</td></tr>`).join('')}</table>${foot(so.src)}`) : ''}`;
  }

  // ══ 6. 레포 ═════════════════════════════════════════════════
  function tRepo(D) {
    const R = D.repo;
    return `<div class="mk-card st-${R.st}"><div class="mk-sub">Repo·단기자금 심층 판독</div><div class="mk-big2">${esc(R.verdict)}</div><div class="small">경로 A(빠른 전이) 상태: <b>${esc(R.pathA)}</b></div></div>
      <div class="ust-g4" style="margin-top:14px">${kv('SOFR (담보부 하루 금리)', pc(R.sofr, 2), '')}${kv('IORB (연준 지준 이자)', pc(R.iorb, 2), '')}
        ${kv('SOFR − IORB', bp(R.sofr_iorb), '≤0 정상 · +5~10 경계 · +10↑ 압박', R.sofr_iorb >= 10 ? 'bad' : R.sofr_iorb >= 5 ? 'warn' : 'ok')}${kv('SOFR 75분위 − 25분위', bp(R.spread75), '≤2 정상 · 3~5 경계 · 5↑ 분산 확대', R.spread75 >= 5 ? 'bad' : R.spread75 >= 3 ? 'warn' : 'ok')}</div>
      ${card('SOFR − IORB 추이 (bp)', lineSvg(R.hist, { h: 150, zero: true, fmt: v => sgn(v, 0) + 'bp' }))}
      ${card('읽는 법', `<ul class="mk-why"><li>SOFR가 IORB보다 높아지면 은행이 연준에 맡겨 두는 것보다 레포로 빌려주는 게 이득 → 시장에 현금이 모자라다는 뜻이에요.</li><li>분위 간격(75−25)이 벌어지면 “누구는 싸게, 누구는 비싸게” 빌린다 → 시장이 갈라지는 신호예요.</li>
        <li>주의: 분기말·월말·세금 납부일(4/15 등)에는 일시적으로 튀어요 — 며칠 이어지는지 보세요.</li><li>SRF 사용액이 늘면 민간 레포가 막혔다는 뜻이에요.</li></ul>${foot(R.src)}`)}`;
  }


  // ══ 🧲 국채 흡수력 (윌리엄 시리즈 320~324) ═══════════════════════════
  function tAbsorb(D) {
    const A = D.absorb;
    if (!A) return '<div class="mk-err">흡수력 자료를 받지 못했어요</div>';
    const T = A.three, Q = A.quality, I = A.investor, N = A.net;
    const fl = b => b ? '<b class="bad">● 약화</b>' : '<span class="ok">○ 양호</span>';
    const d3 = (v, d = 0) => v == null ? '—' : sgn(v, d);
    return `<div class="mk-card mk-over st-${T.st}"><div class="mk-sub">국채 흡수력 3요소 — Term Premium · Auction Tail · Dealer Capacity (칼럼 323)</div>
        <div class="mk-big2">${esc(T.verdict)}</div>
        <div class="small">“국채가 위험해서 금리가 오르는 게 아니라, 시장에 나온 물량을 받아줄 대차대조표가 부족해서 금리가 오를 수도 있다.” — 세 가지가 동시에 나빠지면 Fed가 아무것도 하지 않아도 장기금리가 스스로 올라갈 수 있어요.</div></div>
      <div class="ust-g3">
        <div class="mk-card st-${T.tp.flag ? 'warn' : 'ok'}">${kv('① 기간프리미엄 (Term Premium)', T.tp.v == null ? '—' : fN(T.tp.v, 2) + '%', `30일 ${d3(T.tp.d30)}bp · 1년 ${d3(T.tp.d1y)}bp · ${esc(T.tp.date || '')}`)}<div>${fl(T.tp.flag)}</div>
          <div class="mk-foot">내 돈을 10년 묶는 대가로 더 받는 위험수당. 연준 Kim-Wright 공식 추정치 · 30일 +15bp 또는 1년 +50bp 이상이면 약화</div></div>
        <div class="mk-card st-${T.tail.flag ? 'bad' : T.tail.n1 ? 'warn' : 'ok'}">${kv('② 입찰 꼬리 (Auction Tail, 근사)', `${T.tail.n1}/${T.tail.n}건`, `최근 45일 중장기물 · 평소보다 꼬리가 2bp 이상 큰 입찰`)}<div>${fl(T.tail.flag)}</div>
          <div class="mk-foot">예상보다 높은 금리를 줘야 팔렸다는 신호. 입찰 직전 시세(WI)는 비공개라 ‘낙찰금리 − 당일 시장금리’로 근사하고, 같은 만기의 평소 꼬리와 비교해요</div></div>
        <div class="mk-card st-${T.dealer.flag ? 'bad' : 'ok'}">${kv('③ Primary Dealer 여력 (Dealer Capacity)', T.dealer.ust == null ? '—' : '$' + fN(T.dealer.ust / 1000, 0) + 'B', `미 국채 순보유 8주 ${d3(T.dealer.ust_pct, 1)}% · 레포 차입 ${T.dealer.repo == null ? '—' : '$' + fN(T.dealer.repo / 1e6, 2) + 'T'} (${d3(T.dealer.repo_pct, 1)}%) · ${esc(T.dealer.asof || '')}`)}<div>${fl(T.dealer.flag)}</div>
          <div class="mk-foot">Primary Dealer가 국채를 얼마나 더 받아 중개할 수 있나. 보유 +10% 이상 & 레포 +5% 이상이면 대차대조표를 많이 쓰는 중(약화)</div></div>
      </div>
      ${T.tp.hist && T.tp.hist.length > 1 ? card('10년 기간프리미엄 추이 (%) <span class="mk-sub">연준 Kim-Wright 모형 — 사이트의 ‘나머지’ 근사치 대신 공식 추정치</span>', lineSvg(T.tp.hist, { h: 140, zero: true, fmt: v => fN(v, 2) + '%' })) : ''}
      ${card('🧐 입찰 흡수의 질 — 누가 받아 갔나 <span class="mk-sub">칼럼 324: Tail · Indirect · Dealer 3개를 같은 만기의 평소(최근 6회)와 함께 비교</span>', `<div class="tablewrap"><table class="t"><tr><th>입찰일</th><th>만기</th><th class="r">응찰배율</th><th class="r">꼬리(근사)</th><th class="r">평소보다</th><th class="r">Indirect Bidder / 평소</th><th class="r">Primary Dealer / 평소</th><th>판정</th></tr>
        ${Q.map(q => `<tr><td class="mono">${esc(q.date)}</td><td>${esc(q.label || q.term)}</td><td class="r mono">${fN(q.btc, 2)}</td><td class="r mono">${q.tail == null ? '—' : sgn(q.tail, 1) + 'bp'}</td>
          <td class="r mono ${q.flags.tail ? 'bad' : ''}">${q.tail_ex == null ? '—' : sgn(q.tail_ex, 1) + 'bp'}</td>
          <td class="r mono ${q.flags.ind ? 'bad' : ''}">${fN(q.indirect, 1)}% <span class="mk-sub">/ ${fN(q.ind_avg, 1)}</span></td><td class="r mono ${q.flags.dl ? 'bad' : ''}">${fN(q.dealer, 1)}% <span class="mk-sub">/ ${fN(q.dl_avg, 1)}</span></td>
          <td>${badge(q.st, q.verdict)}</td></tr>`).join('')}</table></div>
        <div class="mk-foot">판정: 꼬리가 평소보다 2bp 이상 · Indirect Bidder 비중이 평소보다 5%p 이상 낮음 · Primary Dealer 비중이 평소보다 5%p 이상 높음 — 0개 양호 / 1개 일부 약함 / 2개 이상 흡수 실패 의심. 응찰배율 하나만 높다고 성공이 아니에요 — 얼마나 신청했는지가 아니라 누가 실제로 물량을 들고 갔는지가 중요해요.</div>`)}
      ${I ? card('👥 투자자 유형별 실제 배정 <span class="mk-sub">재무부 Investor Class Auction Allotments — ‘Indirect Bidder = 외국인’이 아니라 실제로 누가 받았는지</span>', `<div class="tablewrap"><table class="t"><tr><th>발행일</th><th>종류</th><th class="r">발행($B)</th>${['inv_funds', 'dealers', 'foreign', 'pension_ins', 'depository', 'individuals'].map(k => `<th class="r">${esc(I.kr[k])}</th>`).join('')}</tr>
        ${I.rows.map(r => `<tr><td class="mono">${esc(r.issue)}</td><td>${esc(r.sec)}</td><td class="r mono">${fN(r.total, 1)}</td>${['inv_funds', 'dealers', 'foreign', 'pension_ins', 'depository', 'individuals'].map(k => { const v = r.share[k], b = r.base[k], dlt = b == null ? null : v - b;
          const bad = (k === 'dealers' && dlt > 3) || (k === 'foreign' && dlt < -3);
          return `<td class="r mono ${bad ? 'bad' : ''}">${fN(v, 1)}%${b != null ? `<div class="mk-sub">평소 ${fN(b, 1)}</div>` : ''}</td>`; }).join('')}</tr>`).join('')}</table></div>
        <div class="mk-foot">비중 = 연준(SOMA) 몫을 뺀 시장 물량 대비 · 평소 = 같은 종류 직전 6회 평균 · 빨간색 = Dealers and Brokers 몫이 평소보다 3%p↑ 또는 해외 몫이 3%p↓ · ${src('재무부 원자료', I.url)}</div>`) : ''}
      ${N ? card('🧾 Bill vs Coupon — 같은 돈을 빌려도 충격이 다르다 <span class="mk-sub">칼럼 320</span>', `<div class="ust-g4">${kv('최근 3개월 단기채(Bill) 순발행', '$' + fN(N.d_bills, 0) + 'B', `${esc(N.from)} → ${esc(N.asof)} · 주로 MMF가 흡수`)}${kv('최근 3개월 중장기채(Coupon) 순발행', '$' + fN(N.d_coupons, 0) + 'B', '은행·Primary Dealer·연기금·해외가 받아야 함')}
          ${kv('Bill 비중', N.share_bills == null ? '—' : fN(N.share_bills, 0) + '%', '')}${kv('예상 레포 금리 압력', '+' + fN(N.repo_bp, 1) + 'bp', `Bill ${fN(N.repo_bills, 1)} + Coupon ${fN(N.repo_coupons, 1)}`, N.repo_bp >= 15 ? 'warn' : 'ok')}</div>
        <div class="small">같은 $1,000억이라도 Coupon은 Primary Dealer가 먼저 받아 넘기는 과정이 필요해서 레포 충격이 Bill의 약 3배예요. 게다가 지금은 역레포 쿠션이 ${D.liq.rrp_now == null ? '—' : B(D.liq.rrp_now)}로 거의 바닥이라, “누가 새 국채를 받아줄지”가 더 중요해졌어요.</div>
        <table class="t" style="margin-top:8px"><tr><th>칼럼 320의 4가지 체크</th><th>지금</th></tr>
          <tr><td>① 총 차입 규모</td><td>${A.qra && A.qra.estimates && A.qra.estimates.quarters[0] ? `${esc(A.qra.estimates.quarters[0].q)} $${fN(A.qra.estimates.quarters[0].borrow, 0)}B · ${esc((A.qra.estimates.quarters[1] || {}).q || '')} $${fN((A.qra.estimates.quarters[1] || {}).borrow, 0)}B` : '—'}</td></tr>
          <tr><td>② Bill과 Coupon 비중</td><td>최근 3개월 순발행 Bill ${fN(N.share_bills, 0)}% · Coupon ${fN(100 - N.share_bills, 0)}% (1년: Bill $${fN(N.y_bills, 0)}B · Coupon $${fN(N.y_coupons, 0)}B)</td></tr>
          <tr><td>③ Primary Dealer가 얼마나 떠안는지</td><td>중장기물 최근 12건 평균 ${fN(D.auctions.coupon_avg_dealer, 1)}% · 흡수 실패 의심 ${Q.filter(q => q.n >= 2).length}건 (위 표)</td></tr>
          <tr><td>④ 레포 금리가 같이 오르는지</td><td>SOFR − IORB ${D.repo.sofr_iorb == null ? '—' : sgn(D.repo.sofr_iorb, 0) + 'bp'} · 상하위 분산 ${D.repo.spread75 == null ? '—' : sgn(D.repo.spread75, 0) + 'bp'} → ${esc(D.repo.verdict)}</td></tr></table>
        <div class="mk-foot">${esc(N.basis)} · 순발행 = 재무부 MSPD 시장성 국채 잔액 변화</div>`) : ''}
      <div class="mk-foot">${(A.src || []).map(l => src(l.label, l.url)).join(' ')}<br>근거: ${esc(A.basis)}</div>`;
  }
  function qraCard(D) {
    const Q = D.absorb && D.absorb.qra;
    if (!Q) return '';
    const E_ = Q.estimates, P = Q.policy;
    return card('🗺️ QRA — 국채 공급 지도 <span class="mk-sub">칼럼 321: Fed가 돈의 가격을 보여 준다면 재무부는 시장이 받아내야 할 물량을 보여 줘요</span>', `
      ${E_ ? `<div class="ust-g3">${E_.quarters.map((q, i) => kv(`${i ? '다음' : '이번'} 분기 순차입 추정 · ${esc(q.q)}`, '$' + fN(q.borrow, 0) + 'B', `분기 말 현금 잔고 가정 $${fN(q.cash, 0)}B`)).join('')}
        ${E_.change ? kv('지난 발표와 바뀐 부분 (가장 중요)', `${E_.change.amt >= 0 ? '+' : '−'}$${fN(Math.abs(E_.change.amt), 0)}B`, `${esc(E_.change.vs)} 발표 대비 ${E_.change.amt >= 0 ? '더 빌림' : '덜 빌림'}`, E_.change.amt > 50 ? 'warn' : 'ok') : ''}</div>` : ''}
      ${P ? `<div class="small" style="margin-top:6px"><b>리펀딩</b>: 총 $${fN(P.offering, 0)}B 발행 → 만기 상환 $${fN(P.refund, 1)}B · 민간에서 새로 가져가는 현금 <b>$${fN(P.new_cash, 1)}B</b></div>
        <div class="pk-chips" style="margin-top:6px">${P.secs.map(x => `<span class="pk-chip">${x.y}년물 $${fN(x.amt, 0)}B</span>`).join('')}</div>
        ${P.guidance.length ? `<ul class="mk-why">${P.guidance.map(g => `<li class="trx">${esc(g)}</li>`).join('')}</ul>` : ''}` : ''}
      <div class="small">체크 3가지: ① 총 조달액 ② 어느 만기에 몰리나 ③ <b>예상과 바뀐 부분</b> — 시장은 예상치를 이미 가격에 반영하니 차이가 더 중요해요.
        ${Q.next && Q.next.length ? `다음 발표: <b>${Q.next.slice(0, 2).map(esc).join(' (차입 추정) · ')} (정책 발표)</b>` : ''}</div>
      <div class="mk-foot">${E_ ? src('차입 추정치 원문', E_.url) : ''} ${P ? src('리펀딩 정책 발표 원문', P.url) : ''} ${src('최신 QRA 자료', Q.page)}</div>`);
  }
  function buybackCard(D) {
    const Bb = D.absorb && D.absorb.buyback;
    if (!Bb) return '';
    const mx = Math.max(1, ...Bb.months.map(m => m[1]));
    return card('🔁 재무부 바이백 (Buyback) — 국채 시장조성 능력을 사는 중 <span class="mk-sub">칼럼 322: QE(통화정책)가 아니라 부채·유동성 관리</span>', `
      <div class="ust-g4">${kv('최근 90일 매입', '$' + fN(Bb.total_90d, 1) + 'B', '')}${kv('장기물 회당 최대', Bb.long_max_now == null ? '—' : '$' + fN(Bb.long_max_now, 1) + 'B', Bb.long_max_prev ? `이전 $${fN(Bb.long_max_prev, 1)}B → 확대` : '', Bb.long_max_prev ? 'warn' : '')}
        ${kv('Primary Dealer가 팔려고 내놓은 물량 ÷ 매입', Bb.ratio_avg == null ? '—' : fN(Bb.ratio_avg, 1) + '배', '최근 10회 평균 — 클수록 팔고 싶은 국채가 많음', Bb.ratio_avg >= 5 ? 'warn' : 'ok')}${kv('목적', 'Liquidity Support · Cash Management', '거래 뜸한 옛 국채 유동성 · 정부 현금 관리')}</div>
      <div class="small" style="margin:6px 0"><b>월별 매입($B)</b> ${Bb.months.map(m => `<span class="ust-bbm"><i style="height:${Math.round(m[1] / mx * 40)}px"></i><em>${esc(m[0].slice(2))}</em><b>${fN(m[1], 0)}</b></span>`).join('')}</div>
      <table class="t"><tr><th>최근 90일 · 목적 · 만기</th><th class="r">횟수</th><th class="r">매입</th><th class="r">내놓은 물량</th><th class="r">배수</th></tr>${Bb.by_bucket.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="r mono">${v.n}</td><td class="r mono">$${fN(v.acc, 1)}B</td><td class="r mono">$${fN(v.off, 1)}B</td><td class="r mono">${v.acc ? fN(v.off / v.acc, 1) + '배' : '—'}</td></tr>`).join('')}</table>
      <div class="small" style="margin-top:6px">체크 4가지: ① 매입 규모가 커지는지 ② 어느 만기를 집중적으로 사는지 ③ 옛 국채(Off-the-run) 유동성이 나빠지는지 ④ Primary Dealer가 얼마나 많이 팔려고 하는지. 바이백 확대가 반복되면 “호재인가?”보다 <b>“왜 재무부가 여기까지 유동성을 직접 관리하려 하지?”</b>를 먼저 물으세요.</div>
      <div class="mk-foot">${Bb.src.map(l => src(l.label, l.url)).join(' ')}</div>`);
  }
  // ══ 7. 금리 원인 ═══════════════════════════════════════════
  function tRates(D) {
    const R = D.rates;
    const comp = [['실질금리 (성장 기대)', R.d_real], ['기대인플레 (물가 걱정)', R.d_bei], ['기간프리미엄 (공급·재정 부담, 나머지)', R.d_tp]];
    const mx = Math.max(10, ...comp.map(c => Math.abs(c[1] || 0)));
    return `<div class="mk-card st-${stOf(R.badge)}"><div class="mk-sub">🔬 금리 상승 원인 자동 분리 — 10년물 ≈ 실질금리 + 기대인플레 + 기간프리미엄</div><div class="mk-big2">${esc(R.title)}</div><div class="small">${esc(R.desc)}</div><div class="small" style="margin-top:4px">🔍 ${esc(R.liq_note)}</div></div>
      <div class="ust-g4" style="margin-top:14px">${kv('10년물', pc(R.y10, 2), '30일 ' + bp(R.d_nom))}${kv('2년물', pc(R.y2, 2), '')}${kv('30년물', pc(R.y30, 2), '')}${kv('실질금리 · 기대인플레', `${pc(R.real, 2)} · ${pc(R.bei, 2)}`, '')}</div>
      ${card('30일 변화 분해', `<div class="ust-decomp">${comp.map(([k, v]) => `<div><span>${k}</span><div class="ust-dbar"><i class="${(v || 0) >= 0 ? 'pos' : 'neg'}" style="width:${Math.abs(v || 0) / mx * 50}%;${(v || 0) >= 0 ? 'left:50%' : 'right:50%'}"></i></div><b class="mono">${bp(v)}</b></div>`).join('')}</div>
        ${R.tp_official && R.tp_official.v != null ? `<div class="small" style="margin-top:6px">📌 <b>공식 추정치</b>(연준 Kim-Wright 10년 기간프리미엄): <b>${fN(R.tp_official.v, 2)}%</b> · 30일 ${sgn(R.tp_official.d30, 0)}bp · 1년 ${sgn(R.tp_official.d1y, 0)}bp — 장기금리 = 미래 단기금리 기대 + 기간프리미엄 (칼럼 323). 자세히는 <a href="#" data-go="absorb">🧲 흡수력</a></div>` : ''}
        <div class="mk-foot">주의: 위 분해의 기간프리미엄은 ‘나머지’로 계산한 근사치예요(정식 ACM 모형 아님) · 30일 변화는 잡음이 있어요 · 유동성 지표와 함께 보세요.</div>`)}
      ${card('10년물 금리 (1년)', lineSvg(R.hist10, { h: 160, fmt: v => fN(v, 2) + '%' }) + foot(R.src))}
      ${card('📐 금리가 오르면 정부 이자는 얼마나 늘까? <span class="mk-sub">1년 안에 다시 빌려야 하는 단기채(Bills) 잔액만으로 계산한 최소치</span>', `<table class="t"><tr><th>금리 변화</th><th class="r">연간 추가 이자 (최소)</th></tr>${D.shock.map(s => `<tr><td>+${s.dp}%p</td><td class="r mono">${usd(s.bills_only)}</td></tr>`).join('')}</table>
        <div class="small" style="margin-top:6px"><b>Duration Trap</b>: 장기금리가 무서워 단기물로 버티면(2023년 옐런의 Bills Pivot), 금리가 높은 상태가 길어질수록 매년 갚아야 할 이자가 빠르게 늘어요. 1년 안에 만기가 오는 중기채까지 더하면 실제 부담은 이보다 커요.</div>`)}`;
  }

  // ══ 8. 발행 구조 · Bills Pivot ═══════════════════════════════
  function tIssue(D) {
    const d = D.debt, P = D.pivot;
    if (!d) return '<div class="mk-err">국채 잔액 자료를 받지 못했어요</div>';
    const C = d.comp, cl = { bills: '단기채(Bills)', notes: '중기채(Notes)', bonds: '장기채(Bonds)', tips: '물가연동(TIPS)', frn: '변동금리(FRN)' };
    const ckc = s => ({ fail: 'bad', warn: 'warn', pass: 'ok' }[s] || 'na');
    return `<div class="ust-g4">${kv('시장성 국채 잔액', usd(d.total_marketable), `${esc(d.date)} 기준 · 전체 공공부채 ${usd(d.public_total)}`)}${kv('단기채(Bills) 비중', pc(d.bills_share), badge(d.tbac_st, d.tbac) + ' 권고 15~20%', d.tbac_st)}${kv('중기채 비중', pc(C.notes), '')}${kv('장기채 비중', pc(C.bonds), '')}</div>
      ${card('국채 구성', `<div class="ust-stack">${Object.keys(cl).filter(k => C[k]).map((k, i) => `<div class="c${i}" style="flex:${C[k]}"><b>${fN(C[k], 1)}%</b><span>${cl[k]}</span></div>`).join('')}</div>
        <div class="small" style="margin-top:10px">TBAC(재무부 차입자문위원회) 권고 범위 15~20%</div><div class="ust-gauge"><span class="band" style="left:${15 / 40 * 100}%;width:${5 / 40 * 100}%"></span><i style="left:${Math.min(100, d.bills_share / 40 * 100)}%"></i></div><div class="mk-sub" style="display:flex;justify-content:space-between"><span>0%</span><span>20%</span><span>40%</span></div>
        <div class="small" style="margin-top:6px">신호등: <b class="bad">22% 초과 = 빨간불</b> · Bills 비중은 오르는데 장기물 발행은 그대로 = 주황불 (2023년 옐런 사례) · 15~20% = 초록불</div>${foot(d.src)}`)}
      ${d.bills_hist && d.bills_hist.length ? card('단기채 비중 추이 (%)', lineSvg(d.bills_hist, { h: 150, ref: 20, fmt: v => fN(v, 1) + '%' })) : ''}
      ${card(`🎯 Bills Pivot 감지기 — 4가지 체크포인트 ${badge(P.fails >= 3 ? 'bad' : P.fails >= 2 ? 'warn' : 'ok', P.verdict)}`, `<table class="t">${P.checks.map(c => `<tr><td>${badge(ckc(c.st), { fail: '경보', warn: '주의', pass: '정상' }[c.st] || '자료 없음')}</td><td><b>${c.n}. ${esc(c.name)}</b><div class="mk-sub">${esc(c.v)}</div></td></tr>`).join('')}</table>
        ${P.action ? `<div class="small" style="margin-top:6px">대응: <b>${esc(P.action)}</b></div>` : ''}
        <details class="small" style="margin-top:6px"><summary>📘 Bills Pivot의 3가지 숨은 의미</summary><ol><li>장기금리를 자극하고 싶지 않다</li><li>수요가 단기물에 몰려 있다 (MMF 자금)</li><li>차환(롤오버) 위험을 미래로 미룬다</li></ol>“재무부가 단기물 발행을 늘릴 때는, 돈이 필요한 것보다 장기금리가 더 무서운 상태인 경우가 많다.”</details>
        <div class="mk-foot">체크 ①은 최근 리펀딩(2·5·8·11월) 3·10·30년물 발행 규모를 3개월 전과 비교해 자동 판정해요 (원본은 고정값). ${src('재무부 분기 리펀딩', 'https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding')} ${src('TBAC', 'https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/treasury-borrowing-advisory-committee')}</div>`)}
      ${qraCard(D)}${buybackCard(D)}
      ${D.verdicts.items.qra ? card('🏛️ 최근 리펀딩 장기물 발행 규모', `<div class="small">${esc(D.verdicts.items.qra.summary)}</div><table class="t" style="margin-top:6px"><tr>${Object.entries(D.verdicts.items.qra.data.sizes).map(([k, v]) => `<th>${esc(k)}</th>`).join('')}</tr><tr>${Object.values(D.verdicts.items.qra.data.sizes).map(v => `<td class="mono">$${fN(v, 0)}B</td>`).join('')}</tr></table>`) : ''}`;
  }

  // ══ 9. 이자 부담 ════════════════════════════════════════════
  function tInt(D) {
    const I = D.interest;
    return `<div class="ust-g4">${kv('연방 이자 지출 (연율)', I.interest == null ? '—' : '$' + fN(I.interest / 1000, 2) + 'T', esc(I.date || '') + ' 분기')}
        ${kv('이자 ÷ 연방 경상수입', pc(I.to_rev), '25% 넘으면 ‘이자 악순환(Interest Expense Spiral)’ 경계', I.st)}${kv('이자 ÷ GDP', pc(I.to_gdp, 2), '3%를 넘으면 부담이 큰 수준')}
        ${kv('재정 악화 속도', I.speed == null ? '—' : fN(I.speed, 2) + '배', `이자 증가 ${pc(I.int_g)} ÷ 빚 증가 ${pc(I.debt_g)} · 1배 넘으면 나빠지는 중`, I.speed > 1 ? 'warn' : 'ok')}</div>
      ${card('이자 지출 ÷ 연방 경상수입 (%)', lineSvg(I.hist, { h: 160, ref: 25, fmt: v => fN(v, 1) + '%' }) + foot(I.src))}
      ${card('읽는 법', `<ul class="mk-why"><li>빚이 늘어나는 속도보다 이자가 늘어나는 속도가 빠르면 “빚을 갚으려고 빚을 내는” 악순환에 가까워져요.</li><li>이자 지출이 국방비를 넘어선 것은 미국 재정이 금리에 얼마나 민감해졌는지 보여 줘요.</li>
        <li>이 숫자는 미 상무부(BEA) 국민계정 기준 ‘총 이자 지출’이라, 의회예산처(CBO)의 ‘순이자’ 비율보다 조금 높게 나와요.</li></ul>
        <div class="mk-foot">원본 대시보드의 고정 수치(~$950B, ~18.6%) 대신 FRED 분기 자료로 매번 다시 계산해요. ${src('CBO 예산 전망', 'https://www.cbo.gov/topics/budget')}</div>`)}`;
  }

  // ══ 10. 신용위기 ═══════════════════════════════════════════
  function tCredit(D) {
    const C = D.credit;
    const stg = ['정상', '정크→투자등급', '투자등급→국채', '국채→달러', '위기'];
    const E_ = C.etf;
    return `<div class="ust-g4">${kv('하이일드(정크본드) 스프레드', fN(C.hy, 0) + 'bp', `${badge(stOf(C.hy_badge === '낙관' || C.hy_badge === '중립' ? '' : '🔴'), C.hy_badge)} 1주 ${bp(C.hy_w)}`, C.hy >= 600 ? 'bad' : C.hy >= 400 ? 'warn' : 'ok')}
        ${kv('투자등급 스프레드', fN(C.ig, 0) + 'bp', `${C.ig_badge} · 1주 ${bp(C.ig_w)}`, C.ig >= 200 ? 'bad' : C.ig >= 150 ? 'warn' : 'ok')}${kv('CCC 이하 스프레드', fN(C.ccc, 0) + 'bp', `${C.ccc_badge} · 1주 ${bp(C.ccc_w)}`, C.ccc >= 1500 ? 'bad' : C.ccc >= 1000 ? 'warn' : 'ok')}
        ${kv('HY ÷ IG 비율', fN(C.ratio, 2) + '배', C.ratio_badge, C.ratio >= 7 ? 'bad' : C.ratio >= 5 ? 'warn' : 'ok')}</div>
      ${card('🔥 자본 탈출 도미노 — 지금 몇 단계?', `<div class="ust-steps">${stg.map((s, i) => `<div class="${i === C.stage ? 'on' : ''} ${i <= (C.stage ?? -1) ? 'past' : ''}"><b>${i}</b><span>${s}</span></div>`).join('')}</div>
        <div class="small" style="margin-top:6px">순서: 정크본드 → 투자등급 회사채 → 국채 → 달러. 지금 <b>${C.stage ?? '—'}단계</b> (HY ${fN(C.hy, 0)}bp · IG ${fN(C.ig, 0)}bp · 비율 ${fN(C.ratio, 2)})</div>`)}
      <div class="mk-grid2" style="margin-top:14px">${card('채권 ETF 자금 흐름', `<table class="t"><tr><th>ETF</th><th class="r">가격</th><th class="r">하루</th><th class="r">3개월</th></tr>${Object.entries(E_).map(([k, x]) => `<tr><td><b>${k}</b> <span class="mk-sub">${{ HYG: '하이일드', JNK: '하이일드', LQD: '투자등급', TLT: '장기 국채' }[k]}</span></td><td class="r mono">${fN(x.px, 2)}</td><td class="r mono">${sgn(x.d1, 2)}%</td><td class="r mono">${sgn(x.m1, 1)}%</td></tr>`).join('')}</table>
          <div class="small" style="margin-top:6px">HYG ÷ TLT ${fN(C.hyg_tlt, 3)} → <b>${esc(C.flow)}</b></div>`)}
        ${card(`✨ 위기 종결 신호 감지기 ${badge(C.end_n === 3 ? 'ok' : C.end_n === 2 ? 'warn' : 'na', C.end_n === 3 ? '🎯 위기 종결 진입' : C.end_n + '/3 충족')}`, `<ul class="mk-why"><li>${C.end[0] ? '✅' : '⏳'} 최근 10일 HY 평균이 3~4주 전보다 낮아짐</li><li>${C.end[1] ? '✅' : '⏳'} 연준 국채 보유가 5주간 늘어남</li><li>${C.end[2] ? '✅' : '⏳'} 투자등급 스프레드 200bp 미만</li></ul>
          <div class="small">“채권은 진실, 주식은 드라마” — 채권 시장이 먼저 움직이고 주식이 뒤따라요. “너무 빠졌는데 반등하지 않을까?”는 가장 흔한 함정이에요.</div>`)}</div>
      <div class="mk-grid2" style="margin-top:14px">${card('하이일드 스프레드 (bp)', lineSvg(C.hist_hy, { h: 150, fmt: v => fN(v, 0) + 'bp' }))}${card('투자등급 스프레드 (bp)', lineSvg(C.hist_ig, { h: 150, fmt: v => fN(v, 0) + 'bp' }))}</div>
      ${foot(C.src)}
      ${recessionCard(D.recession)}`;
  }

  // ══ 11. 일본·캐리 ══════════════════════════════════════════
  function tJapan(D) {
    const J = D.japan;
    return `<div class="ust-g4">${kv('일본 10년물', pc(J.j10, 3), '1개월 ' + bp(J.j1m), J.j10 >= 2 ? 'bad' : J.j10 >= 1.5 ? 'warn' : 'ok')}${kv('미·일 10년 금리차', fN(J.spread, 0) + 'bp', `${esc(J.spread_badge || '')} · 정상 200bp↑ / 150 경계 / 100↓ 청산 압박`, J.spread < 100 ? 'bad' : J.spread < 150 ? 'warn' : 'ok')}
        ${kv('캐리 압력 점수', J.carry + '/100', esc(J.carry_badge), J.carry_st)}${kv('일본 해외 중장기채 (지난주)', J.flow_last == null ? '—' : sgn(J.flow_last, 0) + '억엔', `≈ ${J.flow_usd == null ? '—' : sgn(J.flow_usd, 1) + 'B 달러'} · ${esc(J.flow_trend || '')}`, J.flow_last < -10000 ? 'bad' : J.flow_last < 0 ? 'warn' : 'ok')}</div>
      ${card(`🌊 엔 캐리 트레이드 붕괴 5단계 — 지금 ${J.seq_top}단계`, `<div class="ust-steps">${J.seq.map(s => `<div class="${s.active ? 'on' : ''}"><b>${s.n}</b><span>${esc(s.name)}</span><em>${esc(s.text)}</em></div>`).join('')}</div>
        <div class="small" style="margin-top:6px">최악의 조합: 일본 금리 ↑ + 미·일 금리차 ↓ + 일본 자금이 해외채권을 팔기 시작. 캐리 점수 = 일본 10년물 수준(최대 50) + 1개월 상승폭(30) + 금리차(20).</div>`)}
      <div class="mk-grid2" style="margin-top:14px">${card('일본 국채 금리 (최근)', `<table class="t"><tr><th>날짜</th><th class="r">2년</th><th class="r">5년</th><th class="r">10년</th><th class="r">30년</th></tr>${J.curve.map(c => `<tr><td class="mono">${esc(c.date)}</td><td class="r mono">${fN(c.y2, 3)}</td><td class="r mono">${fN(c.y5, 3)}</td><td class="r mono">${fN(c.y10, 3)}</td><td class="r mono">${fN(c.y30, 3)}</td></tr>`).join('')}</table>`)}
        ${card('🗾 일본 주간 해외채권 플로우 (숨은 지원군 탐지)', `<div class="tablewrap" style="max-height:260px;overflow:auto"><table class="t"><tr><th>기간</th><th class="r">중장기채 순매수</th><th class="r">해외증권 전체</th></tr>${J.flow.map(f => `<tr><td class="mono small">${esc(f.period)}</td><td class="r mono ${f.long >= 0 ? 'ok' : 'bad'}">${sgn(f.long, 0)}</td><td class="r mono">${sgn(f.total, 0)}</td></tr>`).join('')}</table></div><div class="mk-foot">단위 억엔. + 순매수 / − 순매도. 일본 투자자가 해외 채권(상당 부분 미국 국채)을 사면 미국 금리를 눌러 주는 ‘숨은 지원군’이에요.</div>`)}</div>
      ${card('일본 10년물 (1년)', lineSvg(J.hist10, { h: 150, fmt: v => fN(v, 3) + '%' }) + foot(J.src))}`;
  }

  // ══ 12. 역발상 ═════════════════════════════════════════════
  function tContra(D) {
    const C = D.contra;
    return `<div class="ust-g3">${kv(tip('MOVE (채권 변동성)', '국채 옵션으로 본 ‘채권판 VIX’'), fN(C.move, 0), C.move_badge + ' · 120↑ 긴장 · 150↑ 위기', C.move >= 120 ? 'bad' : C.move >= 100 ? 'warn' : 'ok')}
        ${kv('VIX (주식 공포)', fN(C.vix, 1), C.vix_badge, C.vix >= 30 ? 'bad' : C.vix >= 20 ? 'warn' : 'ok')}${kv('하이일드 스프레드', fN(C.hy, 0) + 'bp', C.hy_badge, C.hy >= 600 ? 'bad' : C.hy >= 400 ? 'warn' : 'ok')}
        ${kv('유로/달러 (달러 조달 압력 대용)', fN(C.eurusd, 4), '30일 ' + sgn(C.eurusd_30, 1) + '% · ±2% 넘으면 주목', Math.abs(C.eurusd_30 || 0) > 2 ? 'warn' : '')}${kv('SOFR', pc(C.sofr, 2), '연준 기준금리와 크게 벌어지면 레포 스트레스')}${kv('금 ÷ S&P500', fN(C.gold_spx, 3), `금 ${fN(C.gold, 0)} · S&P ${fN(C.spx, 0)}`)}</div>
      ${card('MOVE 지수 (3개월)', lineSvg(C.move_hist, { h: 140, ref: 120, fmt: v => fN(v, 0) }))}
      ${card('📊 내러티브 vs 실제 자금 흐름 — 괴리 점수 ' + badge(D.scores[3].st, D.scores[3].badge), `<div class="small">유동성 점수 ${D.scores[1].v ?? '—'}/100 · VIX ${fN(C.vix, 1)} — 돈은 마르는데 공포 지수가 낮다면 시장이 “괜찮다”는 이야기를 너무 믿고 있다는 뜻이에요 (FOMO 매수 주의).</div>`)}
      ${card('🎯 역발상 지표 종합 읽기', `<table class="t"><tr><th>상황</th><th>뜻</th></tr><tr><td>S&P 신고가인데 HY 스프레드 확대</td><td>주식 하락 선행 신호</td></tr><tr><td>VIX 낮은데 MOVE 높음</td><td>채권이 먼저 겁먹음 — 주식이 뒤따를 수 있어요</td></tr>
        <tr><td>금 ÷ S&P 급등</td><td>안전자산 선호 — 위험 회피 시작</td></tr><tr><td>달러 급등 + 위험자산 약세</td><td>공포 달러 — 달러 조달 경색</td></tr><tr><td>모두가 “유동성 잔치”라 하는데 역레포·지준 감소</td><td>이야기와 실제 돈 흐름의 괴리</td></tr></table>${foot(C.src)}`)}
      ${card('🏛️ 기관별 말의 무게 <span class="mk-sub">원래 그런 말 안 하던 사람이 말했다 = 진짜 신호</span>', `<table class="t"><tr><th>기관</th><th>평소 성향</th><th>주목할 때</th></tr><tr><td>IMF</td><td>늘 경고하는 편</td><td>구체적 숫자·국가를 지목할 때</td></tr><tr><td>CBO</td><td>장기 재정 비관</td><td>단기 전망을 크게 바꿀 때</td></tr>
        <tr><td>연준</td><td>안정 강조</td><td>“유동성”·“시장 기능”을 언급할 때</td></tr><tr><td>재무부</td><td>낙관</td><td>바이백·발행 구조를 갑자기 바꿀 때</td></tr><tr><td>신용평가사</td><td>늦게 움직임</td><td>전망을 ‘부정적’으로 바꿀 때</td></tr></table>`)}`;
  }

  // ══ 13. 해석법 · 용어 · 출처 ════════════════════════════════════
  function tGuide() {
    return `${card('📖 국채 입찰 결과 해석 7단계', `<ol class="ust-chain">
        <li><b>기본 정보</b> — 만기·신규 발행인지 재개행(같은 국채 추가 발행)인지 확인하고, 반드시 <b>같은 종류의 이전 입찰</b>과 비교해요.</li>
        <li><b>쿠폰 vs 낙찰금리</b> — 낙찰금리 > 쿠폰 = 할인 발행(수요 부진), < 쿠폰 = 수요 강함.</li>
        <li><b>응찰배율</b> = 총 응찰 ÷ 발행액 — 2.5배↑ 강함 · 2.0~2.5 보통 · 2.0↓ 약함.</li>
        <li><b>테일</b> = 낙찰금리 − 발행 전 시세 — 음수 ‘Stop Through’(좋음) · 0~1bp 무난 · 1bp↑ 꼬리 · 3bp↑ 심각.</li>
        <li><b>Indirect Bidder</b> — Primary Dealer를 통해 들어온 국내외 고객 주문. 외국 중앙은행도 포함되지만 <b>‘Indirect Bidder = 외국인’이 아니에요</b>. 70%↑ 강함 · 60~70 보통 · 60↓ 약함.</li><li><b>Direct Bidder</b> — Primary Dealer를 거치지 않고 기관이 자기 계정으로 직접 입찰한 물량.</li>
        <li><b>Primary Dealer</b> — 15%↓ 건강 · 15~25 주의 · 25%↑ 강제 매수(Forced Buying).</li></ol>
        <table class="t" style="margin-top:8px"><tr><th>항목</th><th class="ok">양호</th><th class="warn">경계</th><th class="bad">위험</th></tr><tr><td>응찰배율</td><td>2.5↑ (직전보다 ↑)</td><td>2.0~2.5 (직전보다 ↓)</td><td>2.0↓</td></tr><tr><td>테일</td><td>0 이하</td><td>1~3bp</td><td>3bp↑</td></tr>
        <tr><td>Indirect Bidder</td><td>70%↑</td><td>60~70%</td><td>60%↓</td></tr><tr><td>Primary Dealer</td><td>15%↓</td><td>15~25%</td><td>25%↑</td></tr></table>
        <table class="t" style="margin-top:8px"><tr><th>만기</th><th>빈도</th><th>시장 영향</th></tr><tr><td>4·8주 단기채</td><td>매주</td><td>낮음</td></tr><tr><td>2·3년</td><td>매월</td><td>중간</td></tr><tr><td>5·7년</td><td>매월</td><td>중상 (7년 테일 주의)</td></tr><tr><td>10년</td><td>매월 (재개행 포함)</td><td>매우 높음</td></tr><tr><td>20년</td><td>매월</td><td>중상</td></tr><tr><td>30년</td><td>매월 (재개행 포함)</td><td>매우 높음</td></tr></table>`)}
      ${card('📚 용어 사전', `<div class="ust-gl">${[['T-Bills', '1년 이하 단기 국채'], ['T-Notes', '2~10년 중기 국채'], ['T-Bonds', '20·30년 장기 국채'], ['TIPS', '물가에 연동되는 국채'], ['FRN', '변동금리 국채'],
        ['TBAC', '재무부 차입자문위원회 — 월가 대형 금융사 모임'], ['Primary Dealer', '뉴욕 연은이 지정한 국채 딜러 — 모든 입찰에 합리적 가격으로 참여할 의무'], ['Direct Bidder', 'Primary Dealer를 거치지 않고 자기 계정으로 직접 입찰한 기관'], ['Indirect Bidder', 'Primary Dealer를 통한 국내외 고객 주문 (외국인만이 아님)'], ['ON RRP (역레포)', 'MMF 등이 연준에 하루짜리로 돈을 맡기는 창구'], ['TGA', '재무부의 연준 통장'], ['은행 지준', '은행이 연준에 맡긴 돈'],
        ['QRA', '분기 국채 발행 계획 발표 (2·5·8·11월)'], ['WAM', '국채 평균 잔존 만기'], ['롤오버', '만기 국채를 새 국채로 갈아타기'], ['응찰배율', '응찰액 ÷ 발행액'], ['Doom Loop', '금리↑ → 이자↑ → 적자↑ → 발행↑ → 금리↑ 악순환'],
        ['Duration Trap', '단기물로 버티다 금리 고착 시 이자 폭증'], ['Bills Pivot', '장기물 대신 단기물 발행을 늘리는 전략'], ['Stealth Easing', '공식 발표 없이 사실상 돈을 푸는 효과'], ['Forced Buying', '수요가 없어 딜러가 억지로 떠안음'], ['기간프리미엄', '돈을 오래 빌려주는 대가로 더 받는 금리']]
        .map(([k, d]) => `<div><b>${k}</b> — ${d}</div>`).join('')}</div>`)}
      ${card('🔗 데이터 출처 · 갱신 주기', `<table class="t"><tr><th>자료</th><th>주기</th><th>출처</th></tr><tr><td>입찰 결과·예정</td><td>입찰마다 (주 2~5회)</td><td>${src('미 재무부 Fiscal Data', 'https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/')}</td></tr>
        <tr><td>역레포 · SRF</td><td>매일</td><td>${src('NY 연준', 'https://www.newyorkfed.org/markets/desk-operations/reverse-repo')}</td></tr><tr><td>TGA</td><td>매일</td><td>${src('재무부 DTS', 'https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/')}</td></tr>
        <tr><td>국채 잔액 구성</td><td>매월</td><td>${src('재무부 MSPD', 'https://fiscaldata.treasury.gov/datasets/monthly-statement-public-debt/')}</td></tr><tr><td>금리·신용·레포·SOMA·물가·고용·이자</td><td>매일~분기</td><td>${src('FRED', 'https://fred.stlouisfed.org/')}</td></tr>
        <tr><td>일본 국채·해외증권 플로우</td><td>매일 · 매주</td><td>${src('일본 재무성', 'https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm')}</td></tr><tr><td>FOMC · 일본은행 일정</td><td>연 1회 공표</td><td>${src('연준', 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm')} ${src('일본은행', 'https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm')}</td></tr>
        <tr><td>MOVE · 채권 ETF · 금 · S&P</td><td>매일</td><td>${src('Yahoo Finance', 'https://finance.yahoo.com/quote/%5EMOVE/')}</td></tr><tr><td>QRA</td><td>분기</td><td>${src('재무부 리펀딩', 'https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding')}</td></tr></table>
        <div class="mk-foot">원본 대시보드에서 뺀 것: 2026년 4~6월 고정 일정, 관세 정책 옵션 트리, 특정 날짜의 고정 3줄 요약, 손으로 넣는 은행·사모신용 지표(PIK·Non-accrual 등) — 매일 바뀌는 공개 자료가 없거나 시점이 지나서예요.</div>`)}`;
  }

  window.UST = { page, stressHtml };
})();
