/* ==========================================================================
   🛢️ 원자재 레이더 — builder/radar.py 가 만든 radar.json(data 브랜치)을 읽어 그린다
   가격을 '예측'하지 않고, 가격을 움직이는 구조(투기자금 포지션 · 실물 재고)를 공식 자료로 보여 준다
   ========================================================================== */
(function () {
  'use strict';
  let $, esc, fN, sgn, src, lineSvg, main;
  const ST = { D: null, view: 'board', id: null, grp: 'all', showRef: {} };
  const BADGE = { ok: ['st-ok', '✅ 매핑 확정'], check: ['st-warn', '🟡 확인 필요'] };
  const GTIP = {
    pm: '원자재를 실제로 생산·가공·사용하는 회사 (정유사, 광산, 곡물회사 등) — 가격 위험을 줄이려고(헤지) 거래해요. 보통 생산자라 숏이 많아요.',
    sd: '은행 등 스와프 딜러 — 고객과 맺은 파생계약의 위험을 선물로 상쇄해요.',
    mm: '헤지펀드·CTA 등 수익을 노리는 투기자금 — 가격 흐름을 따라 빠르게 움직여 “돈의 쏠림”을 보여 줘요.',
    or: '위 세 그룹에 속하지 않는 대형 보고 대상 거래자.',
  };

  // ── 데이터 ─────────────────────────────────────────────────────
  async function api() {
    if (location.protocol === 'file:') throw new Error('원자재 레이더는 웹 주소로 열어 주세요');
    const bust = '?t=' + Math.floor(Date.now() / 6e5);
    const base = ((window.UST_CFG || {}).DATA_URL || '').replace(/ust\.json$/, 'radar.json');
    let last;
    for (const u of [base, 'data/radar.json'].filter(Boolean)) {
      try { const r = await fetch(u + bust, { cache: 'no-cache' }); if (!r.ok) throw new Error(`${r.status}`); return await r.json(); } catch (e) { last = e; }
    }
    throw last || new Error('자료 주소가 없어요');
  }

  // ── 표기 도우미 ────────────────────────────────────────────────
  const md = s => s ? `${+s.slice(5, 7)}/${+s.slice(8, 10)}` : '—';
  const wd = s => s ? '일월화수목금토'[new Date(s + 'T12:00:00Z').getUTCDay()] : '';
  const mdw = s => s ? `${md(s)}(${wd(s)})` : '—';
  const pd = p => /월평균/.test(p.freq) ? `${+p.obs.slice(5, 7)}월 평균` : mdw(p.obs);     // IMF 월평균은 특정 날짜가 아님
  const kst = z => { if (!z) return '—'; const d = new Date(z.replace('Z', ':00Z')); return isFinite(d) ? d.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'; };
  const pct = (v, d = 1) => v == null || !isFinite(v) ? '—' : sgn(v, d) + '%';
  const ct = v => v == null || !isFinite(v) ? '—' : fN(v, 0) + '계약';
  const sct = v => v == null || !isFinite(v) ? '—' : sgn(v, 0);
  const cls = v => v > 0 ? 'up' : v < 0 ? 'dn' : '';
  const big = v => { const a = Math.abs(v); return a >= 1e8 ? fN(v / 1e8, 2) + '억' : a >= 1e4 ? fN(v / 1e4, 0) + '만' : fN(v, 0); };
  const phys = (n, c) => n == null || !c ? '' : `≈ ${big(n * c.size)} ${c.unit}`;
  const tip = (t, d) => `<span class="ust-term" title="${esc(d)}">${esc(t)}</span>`;
  const card = (title, body, cls_ = '') => `<section class="mk-card ${cls_}"><h3>${title}</h3>${body}</section>`;
  const pctTxt = p => p == null ? '표본 부족' : p >= 90 ? '3년 중 매우 높음 (쏠림 극단)' : p >= 70 ? '3년 중 높은 편' : p <= 10 ? '3년 중 매우 낮음 (비관 극단)' : p <= 30 ? '3년 중 낮은 편' : '3년 중 중간';
  const pbar = p => p == null ? '' : `<div class="rd-pbar" title="3년 백분위 ${fN(p, 0)}% — 왼쪽(빨강)일수록 3년 중 순매수가 적은 쪽, 오른쪽(초록)일수록 많은 쪽"><i style="left:${p}%"></i></div>`;
  const showCot = it => it.cot && (it.status === 'ok' || ST.showRef[it.id]);
  const links = L => (L || []).map(x => src(x.label, x.url)).join(' ');
  const srcLine = (...L) => { const h = links([].concat(...L.filter(Boolean))); return h ? `<div class="rd-srcs">출처 ${h}</div>` : ''; };
  // 📘 이 탭 읽는 법 — 탭마다 맨 위에 (접어 두면 다음에도 접힌 채로)
  const HOW = {
    board: ['이 보드는 12개 원자재의 “지금 상태”를 한 장씩 보여 줘요. 위에서부터 이렇게 읽으세요.', [
      '<b>종합 해설</b>을 먼저 읽어요 — 이번 주 원자재 시장 전체가 어느 쪽으로 기울었는지 문장으로 정리돼 있어요.',
      '카드의 <b>가격</b>은 공식 자료 숫자예요. 날짜가 함께 붙어 있으니 “언제 값인지”부터 확인하세요 (월평균이면 지난달 평균).',
      '<b>등락률</b>은 1주·4주 동안 몇 % 움직였는지예요. <span class="up">빨강</span>은 오름, <span class="dn">파랑</span>은 내림. <span class="rd-ref">참고</span>가 붙은 건 공식 가격이 없어 선물 시세로 계산한 비율이에요.',
      '<b>투기자금 순매수</b>는 헤지펀드가 “오른다”에 건 계약이 “내린다”보다 얼마나 많은지예요. 아래 막대에서 흰 눈금이 오른쪽 끝(초록)에 가까울수록 3년 중 가장 많이 사 둔 상태, 왼쪽 끝(빨강)일수록 가장 적게 사 둔(비관) 상태예요.',
      '<b>재고</b>(원유·가스만)는 실물이 넉넉한지예요. 5년 평균보다 적으면 가격을 받치고, 많으면 누르는 쪽이에요.',
      '맨 아래 <b>한 줄 판단</b>은 가격 방향과 투기자금 방향을 짝지은 결과예요 (4가지 뜻은 “해석법·용어” 탭).',
      '주황 테두리 카드는 공식 발표가 예정보다 늦어진 자료가 있다는 뜻이에요. <b>확인 필요</b> 배지는 대표 계약이 CFTC에 없어 포지션을 숨긴 원자재예요.']],
    detail: ['한 원자재를 깊게 보는 화면이에요. 번호 순서대로 읽으면 “왜 움직였나 → 오래갈까”가 보여요.', [
      '<b>맨 위</b>: 공식 가격, 이번 주 방향, 어느 거래소의 어떤 계약을 보는지(1계약이 실물로 얼마인지)를 확인해요.',
      '<b>① 차트</b>: 위 선은 투기자금, 아래 선은 가격이에요. 두 선이 같이 오르내리면 돈이 가격을 밀고 있는 것, 엇갈리면 가격과 돈의 생각이 다른 거예요.',
      '<b>③ 4칸 그림</b>: 주황 점이 이번 주 위치예요. 오른쪽 위(① 추세 매수)·왼쪽 아래(④ 매도 추세)는 가격과 돈이 같은 방향, 나머지 두 칸은 엇갈린 상태예요. 회색 점선은 지난 13주 동안 어디를 지나왔는지예요.',
      '<b>④ 재고</b>: 주황 선(올해)이 파란 띠(지난 5년 범위) 아래에 있으면 공급이 빠듯, 위에 있으면 넉넉해요.',
      '<b>⑤ 사이클 위치</b>: 지금이 긴 흐름에서 바닥·회복·과열·하강 중 어디쯤인지, 층별 근거와 반대 근거를 함께 보여 줘요.',
      '<b>② 4그룹 표</b>: 투기자금(굵은 줄)뿐 아니라 실제 생산·사용 회사(Producer)가 어떻게 움직이는지도 보세요. 보통 생산자는 숏이 많고, 투기자금과 반대로 움직여요.',
      '각 칸 아래 <b>출처</b> 링크를 누르면 공식 원문으로 바로 가서 숫자를 대조할 수 있어요.']],
    cycle: ['원자재는 몇 년~십수 년에 걸쳐 “부족 → 가격 급등 → 증산 투자 → 공급 과잉 → 가격 하락 → 투자 감소 → 다시 부족”을 반복해요. 이 탭은 그 사이클의 위치를 공식 자료 4층으로 나눠 봐요.', [
      '<b>표의 한 줄</b> = 한 원자재. 왼쪽 <b>국면</b>은 20년 실질가격의 높이와 1년 방향으로 정한 “해석”이에요 (확정 사실이 아니에요).',
      '<b>층별 칸 색</b>: <span class="mk-badge st-warn">주황</span>은 주의(과열·빠듯함·쏠림 극단·역풍), <span class="mk-badge st-ok">초록</span>은 우호(저평가·넉넉함·순풍), 회색은 중립이에요.',
      '<b>층이 같은 말을 할수록</b> 신호가 단단해요. 예: 장기 가격이 바닥권인데 재고도 줄고 투기자금 비관도 극단이면, 사이클이 돌아설 조건이 모이는 중일 수 있어요.',
      '<b>층이 엇갈리면</b> “반대 근거”에 적어 둬요. 한쪽 신호만 보고 결론 내리지 않도록요.',
      '<b>공급 투자(CAPEX)</b> 층은 3차 개발에서 생산기업 공시로 채울 예정이에요. 사이클의 “다음 공급”을 알려 주는 가장 느리지만 중요한 층이에요.']],
    status: ['이 화면의 숫자가 “언제 것인지, 늦어진 건 없는지”를 확인하는 탭이에요.', [
      '<b>관측 → 발표</b>: 관측일은 자료가 가리키는 날, 발표일은 기관이 공개한 날이에요. CFTC는 화요일 기준을 금요일에 공개해서 3일 차이가 정상이에요.',
      '<b>정상 / 늦음</b>: 공식 발표 예정일보다 하루 넘게 지났는데 새 자료가 없으면 “늦음”이에요. 미국 공휴일·정부 셧다운 때는 기관이 공식적으로 미뤄요. 이때도 값을 추정해 채우지 않아요.',
      '<b>정정 이력</b>: 기관이 과거 숫자를 고치면, 이전 값을 지우지 않고 새 값과 함께 남겨요.',
      '<b>출처 · 이용 조건</b>: 각 자료를 어디서 받았고 어떤 조건으로 쓰는지 보여 줘요. 링크를 누르면 원문으로 가요.']],
    guide: ['처음이라면 이 탭부터 읽어 보세요. 용어와 판단 규칙, 원자재 사이클을 보는 법이 모여 있어요.', [
      '<b>읽는 순서</b> → <b>4가지 판단</b> → <b>사이클 보는 법</b> → <b>용어 사전</b> 순서로 읽으면 다른 탭이 훨씬 쉽게 보여요.']],
  };
  function howto(k) {
    const h = HOW[k]; if (!h) return '';
    let open = true; try { open = localStorage.getItem('rdHow_' + k) !== '0'; } catch (e) { }
    return `<details class="mk-card rd-how" data-how="${k}" ${open ? 'open' : ''}><summary>📘 이 탭 읽는 법 <span class="mk-sub">(눌러서 접기/펴기)</span></summary>
      <p>${h[0]}</p><ol>${h[1].map(x => `<li>${x}</li>`).join('')}</ol></details>`;
  }

  // ── 페이지 ─────────────────────────────────────────────────────
  async function page(mainEl, rest) {
    ({ $, esc, fN, sgn, src, lineSvg } = window.MK); main = mainEl;
    route(rest);
    main.innerHTML = `<h1 class="mk-h1">🛢️ 원자재 레이더 <span class="mk-sub">가격을 맞히려는 화면이 아니라, 가격을 움직이는 구조 — 투기자금의 쏠림(CFTC)과 실물 재고(EIA) — 를 공식 자료로 보는 화면이에요</span></h1>
      <div id="rBody"><div class="mk-loading">원자재 자료를 불러오는 중…</div></div>`;
    try { ST.D = await api(); } catch (e) { $('#rBody').innerHTML = `<div class="mk-err">원자재 자료를 불러오지 못했어요 — ${esc(e.message)}. 첫 자동 갱신이 끝나면 나타나요.</div>`; return; }
    draw();
  }
  function route(rest) {
    const p = String(rest || '').split('/').filter(Boolean);
    ST.view = ['status', 'guide', 'cycle'].includes(p[0]) ? p[0] : p[0] ? 'detail' : 'board';
    ST.id = ST.view === 'detail' ? p[0] : null;
  }
  function go(rest) { history.replaceState(null, '', '#radar' + (rest ? '/' + rest : '')); route(rest); draw(); window.scrollTo(0, 0); }

  function draw() {
    const D = ST.D;
    const it = ST.id && D.items.find(x => x.id === ST.id);
    if (ST.view === 'detail' && !it) ST.view = 'board';
    const tabs = [['', '📋 원자재 보드'], ...(it ? [[it.id, '🔎 ' + it.name]] : []), ['cycle', '🔄 사이클'], ['status', '🗂️ 자료 상태'], ['guide', '📖 해석법·용어']];
    const cur = ST.view === 'detail' ? it.id : ST.view === 'board' ? '' : ST.view;
    $('#rBody').innerHTML = `<div class="ust-top"><span class="mk-sub">${esc(String(D.built_at || '').replace('T', ' ').slice(0, 16))} (한국시간) 판독 · CFTC는 매주 금요일, EIA 재고는 매주 수·목요일 발표 · 이 화면은 공식 자료만 숫자로 싣고, 없으면 비워 둬요</span>
        ${D.errors && D.errors.length ? `<span class="mk-sub bad" title="${esc(D.errors.join('\n'))}">일부 자료 ${D.errors.length}개를 받지 못했어요</span>` : ''}</div>
      <div class="pf-tabs">${tabs.map(([k, l]) => `<button class="${cur === k ? 'on' : ''}" data-rg="${esc(k)}">${esc(l)}</button>`).join('')}</div><div id="rTab"></div>`;
    $('#rTab').innerHTML = howto(ST.view) + (ST.view === 'detail' ? detail(it, D) : ST.view === 'status' ? status(D) : ST.view === 'guide' ? guide(D) : ST.view === 'cycle' ? cycleTab(D) : board(D));
    document.querySelectorAll('[data-how]').forEach(d => d.ontoggle = () => { try { localStorage.setItem('rdHow_' + d.dataset.how, d.open ? '1' : '0'); } catch (e) { } });
    document.querySelectorAll('.rd-card a').forEach(a => a.addEventListener('click', e => e.stopPropagation()));
    document.querySelectorAll('[data-rg]').forEach(b => b.onclick = e => { e.preventDefault(); go(b.dataset.rg); });
    document.querySelectorAll('[data-rid]').forEach(b => b.onclick = e => { e.preventDefault(); go(b.dataset.rid); });
    document.querySelectorAll('[data-grp]').forEach(b => b.onclick = () => { ST.grp = b.dataset.grp; draw(); });
    document.querySelectorAll('[data-ref]').forEach(b => b.onclick = () => { ST.showRef[b.dataset.ref] = !ST.showRef[b.dataset.ref]; draw(); });
  }

  // ══ 화면 A. 원자재 보드 ═══════════════════════════════════════
  function summaryCard(D) {
    const S = D.summary; if (!S || !S.paras) return '';
    return card('📰 이번 주 원자재 종합 해설 <span class="mk-sub">공식 숫자로 자동 작성 · 문단마다 출처</span>', `<div class="rd-sum">${S.paras.map(p => `<div class="rd-sp"><h4>${esc(p.h)}</h4><p>${esc(p.t)}</p>${srcLine(p.src)}</div>`).join('')}</div>
      <div class="mk-foot">자동 생성 요약이에요 (${fN(S.chars, 0)}자). 매수·매도 추천이 아니며, 숫자 옆 출처 링크로 원문을 꼭 확인하세요.</div>`);
  }
  function board(D) {
    const items = D.items.filter(x => ST.grp === 'all' || x.group === ST.grp);
    return summaryCard(D) + `<div class="mk-card"><div class="rd-intro">
        <div><b>① 가격</b><br>숫자는 공식 자료(EIA·IMF)만 실어요. 금·은·백금처럼 공식 무료 가격이 없으면 <b>이번 주 등락률</b>만 <span class="rd-ref">참고</span>로 보여 줘요.</div>
        <div><b>② 투기자금 (${tip('Managed Money', GTIP.mm)})</b><br>헤지펀드가 이 원자재를 얼마나 사 두었는지(순매수)와, 그게 지난 3년 중 어느 높이인지(막대)를 봐요. 막대가 끝에 붙을수록 한쪽으로 쏠린 거예요.</div>
        <div><b>③ 한 줄 판단</b><br>가격 방향과 투기자금 방향을 짝지어 4가지 중 하나로 읽어요 (예: “④ 매도 추세 확인”). 자세한 근거는 카드를 눌러 보세요.</div>
      </div></div>
      <div class="rd-chips">${[['all', '전체'], ...Object.entries(D.groups)].map(([k, l]) => `<button class="${ST.grp === k ? 'on' : ''}" data-grp="${k}">${esc(l)}</button>`).join('')}</div>
      <div class="rd-grid">${items.map(boardCard).join('')}</div>
      <div class="mk-foot">⚠️ 공식 원자료(CFTC · EIA · FRED/IMF)를 자동으로 판독한 결과예요. 매수·매도 추천이 아니며, 등락률의 <span class="rd-ref">참고</span> 표시는 Yahoo 선물 시세에서 계산한 비율이에요(가격 숫자는 싣지 않아요).</div>`;
  }
  function boardCard(it) {
    const [bc, bl] = BADGE[it.status] || BADGE.check;
    const p = it.price, m = it.move, c = it.cot, mm = c && c.groups.mm, inv = it.inv;
    const late = (it.warn || []).length;
    return `<div class="rd-card ${late ? 'late' : ''}" data-rid="${it.id}" role="link" tabindex="0">
      <h4><span>${esc(it.name)} <span class="mk-sub">${esc(it.group_kr)}</span></span><span class="mk-badge ${bc}">${bl}</span></h4>
      <div class="rd-row"><span class="k">가격</span><span class="v">${p ? `<b>$${fN(p.v, p.v >= 100 ? 1 : 2)}</b> <span class="mk-sub">${esc(p.unit)} · ${pd(p)}</span>` : '<span class="mk-sub">공식 무료 가격 없음</span>'}</span></div>
      <div class="rd-row"><span class="k">등락률</span><span class="v">${m ? `1주 <b class="${cls(m.w1)}">${pct(m.w1)}</b> · 4주 <b class="${cls(m.w4)}">${pct(m.w4)}</b> <span class="mk-sub">${md(m.obs)}</span>${m.ref ? '<span class="rd-ref">참고</span>' : ''}` : '<span class="mk-sub">—</span>'}</span></div>
      ${showCot(it) ? `<div class="rd-row"><span class="k">투기자금 순매수</span><span class="v"><b>${sct(mm.net)}</b>계약 <span class="mk-sub">4주 ${sct(mm.c4)} · ${mdw(c.obs)}</span></span></div>
        ${pbar(mm.pctile)}<div class="mk-sub" style="font-size:12px">3년 백분위 ${mm.pctile == null ? '—' : fN(mm.pctile, 0) + '%'} — ${pctTxt(mm.pctile)}</div>`
        : `<div class="rd-why">${esc(it.why || '')}${it.status === 'check' && it.cot ? ' <span class="mk-sub">(카드를 누르면 참고로 볼 수 있어요)</span>' : ''}</div>`}
      ${inv ? `<div class="rd-row"><span class="k">재고</span><span class="v"><b>${fN(inv.v, 0)}</b> ${esc(inv.unit)} · 5년 평균보다 <b class="${cls(inv.vs5)}">${pct(inv.vs5)}</b> <span class="mk-sub">${md(inv.obs)}</span></span></div>` : ''}
      ${it.quad && showCot(it) ? `<div class="rd-line">${esc(it.quad.label)} <span class="mk-sub">(${mdw(c.obs)} 기준)</span></div>` : ''}
      ${late ? `<div class="rd-warn">⚠ ${esc(it.warn.join(' · '))}</div>` : ''}
      ${srcLine((it.src || {}).price, (it.src || {}).move, showCot(it) ? ((it.src || {}).cot || []).slice(0, 1) : null, ((it.src || {}).inv || []).slice(0, 1))}
    </div>`;
  }

  // ══ 화면 B. 원자재 상세 ═══════════════════════════════════════
  function detail(it, D) {
    const c = it.cot, p = it.price, m = it.move;
    const [bc, bl] = BADGE[it.status] || BADGE.check;
    const see = it.see && D.items.find(x => x.id === it.see);
    const head = `<div class="mk-card"><div class="rd-head">
        <div><div class="mk-sub">${esc(it.group_kr)}</div><div class="big">${esc(it.name)}</div><span class="mk-badge ${bc}">${bl}</span></div>
        <div><div class="mk-sub">가격 (공식)</div><div class="big">${p ? '$' + fN(p.v, p.v >= 100 ? 1 : 2) : '—'}</div><div class="mk-sub">${p ? `${esc(p.unit)} · ${esc(p.freq)} · ${pd(p)} ${src(p.series, p.url)}` : '공식 무료 가격 자료가 없어요'}</div></div>
        <div><div class="mk-sub">이번 주 방향</div><div class="big ${m ? cls(m.w1) : ''}">${m ? pct(m.w1) : '—'}</div><div class="mk-sub">${m ? `1주 · 4주 ${pct(m.w4)} · ${mdw(m.obs)} · ${esc(m.src)}` : '자료 없음'}</div></div>
        ${c ? `<div><div class="mk-sub">CFTC 계약</div><div><b>${esc(c.exch)} ${esc(c.contract)}</b> (${esc(c.code)})</div><div class="mk-sub">1계약 = ${fN(c.size, 0)} ${esc(c.unit)} · 미결제약정 ${ct(c.oi)}</div></div>` : ''}
      </div>
      ${it.why ? `<div class="rd-why" style="margin-top:10px">${esc(it.why)}${see ? ` <a href="#" data-rid="${see.id}">→ ${esc(see.name)} 보기</a>` : ''}</div>` : ''}
      ${it.alt ? `<div class="mk-foot">ℹ️ ${esc(it.alt)}</div>` : ''}
      ${(it.warn || []).length ? `<div class="rd-warn" style="margin-top:6px">⚠ ${esc(it.warn.join(' · '))}</div>` : ''}
      ${it.status === 'check' && c ? `<div style="margin-top:8px"><button class="btn sm" data-ref="${it.id}">${ST.showRef[it.id] ? '참고 포지션 숨기기' : '⚠ 대표 계약이 아님을 알고 참고로 보기'}</button></div>` : ''}</div>`;
    if (!showCot(it)) return head + (it.inv ? invCard(it) : '') + cycleCard(it, D) + explain(it) + srcBox(it);
    const g = c.groups, mm = g.mm;
    const ref = it.status === 'check' ? '<div class="rd-why">⚠ 아래 숫자는 이 원자재의 대표 계약이 아닌 대체 계약이에요. 흐름 참고용으로만 보세요.</div>' : '';
    const chart = it.chart && it.chart.obs.length ? card(`① 투기자금 순포지션과 ${it.chart.px_kind === 'price' ? '가격' : '가격 흐름(3년 전 = 100)'} — 주간, 최근 3년`, `
        <div class="rd-chart-l">투기자금(${tip('Managed Money', GTIP.mm)}) 순매수 (계약) — 0 위면 사 둔 쪽이 많고, 아래면 팔아 둔 쪽이 많아요</div>
        ${lineSvg(it.chart.obs.map((o, i) => [o, it.chart.mm[i]]), { h: 170, zero: true, area: true, fmt: v => fN(v, 0) + '계약', axfmt: v => big(v) })}
        ${it.chart.px.length ? `<div class="rd-chart-l">${it.chart.px_kind === 'price' ? `가격 ($ · ${esc(p ? p.unit : '')}) — 같은 주 화요일` : '가격 흐름 지수 (3년 전 = 100, Yahoo 선물 기준 <span class="rd-ref">참고</span>) — 같은 주 화요일'}</div>
          ${lineSvg(it.chart.obs.map((o, i) => [o, it.chart.px[i]]), { h: 130, color: 'var(--blue)', fmt: v => it.chart.px_kind === 'price' ? '$' + fN(v, 2) : fN(v, 1) })}` : ''}
        <div class="mk-foot">두 선이 같이 오르내리면 “돈이 가격을 밀고 있다”, 서로 반대로 가면 “가격과 돈의 방향이 엇갈린다”는 뜻이에요.</div>${srcLine(it.src.cot, it.chart.px_kind === 'price' ? it.src.price : it.src.move)}`) : '';
    const rows = ['pm', 'sd', 'mm', 'or'].map(k => [k, g[k]]);
    const table = card(`② 참가자 4그룹 포지션 — ${mdw(c.obs)} 기준`, `${ref}
      <table class="t rd-tbl"><tr><th>그룹</th><th class="num">롱(매수)</th><th class="num">숏(매도)</th><th class="num">순(롱−숏)</th><th class="num">1주</th><th class="num">4주</th><th class="num">13주</th><th class="num">미결제약정 대비</th><th class="num">3년 백분위</th></tr>
        ${rows.map(([k, x]) => `<tr${k === 'mm' ? ' style="font-weight:600"' : ''}><td>${tip(x.name, GTIP[k])}</td><td class="num">${fN(x.long, 0)}</td><td class="num">${fN(x.short, 0)}</td><td class="num ${cls(x.net)}">${sct(x.net)}</td>
          <td class="num ${cls(x.c1)}">${sct(x.c1)}</td><td class="num ${cls(x.c4)}">${sct(x.c4)}</td><td class="num ${cls(x.c13)}">${sct(x.c13)}</td><td class="num">${pct(x.pct_oi)}</td><td class="num">${x.pctile == null ? '—' : fN(x.pctile, 0) + '%'}</td></tr>`).join('')}</table>
      <div class="rd-gcards">${rows.map(([k, x]) => `<div><b>${esc(x.name)}</b><br>순 ${sct(x.net)}계약 · 1주 ${sct(x.c1)} · 4주 ${sct(x.c4)} · 13주 ${sct(x.c13)}<br>미결제약정 대비 ${pct(x.pct_oi)} · 3년 백분위 ${x.pctile == null ? '—' : fN(x.pctile, 0) + '%'}</div>`).join('')}</div>
      <div class="mk-foot">순포지션 = 롱 − 숏 (스프레드 포지션 제외, CFTC 정의). 투기자금 순매수 ${sct(mm.net)}계약은 실물로 ${phys(mm.net, c)}이에요. 변화는 정확히 1·4·13주 전 화요일 자료와 비교하고, 그 주 자료가 없으면 비워 둬요. 미결제약정 ${ct(c.oi)} (1주 ${sct(c.oi_c1)}).</div>${srcLine(it.src.cot)}`);
    return head + chart + `<div class="rd-2">${quadCard(it)}${it.inv ? invCard(it) : cycleCard(it, D)}</div>` + (it.inv ? cycleCard(it, D) : '') + table + explain(it) + srcBox(it);
  }

  function quadCard(it) {
    const q = it.quad, tr = it.traj || [];
    if (!q) return card('③ 가격 × 투기자금 — 이번 주 위치', '<div class="mk-sub">가격 방향 자료가 없어 판단하지 않았어요 (추정으로 채우지 않아요).</div>');
    const S = 260, P = 22, h = S / 2;
    const mx = Math.max(1, ...tr.map(t => Math.abs(t.pc))), my = Math.max(1, ...tr.map(t => Math.abs(t.nc)));
    const X = v => h + v / mx * (h - P), Y = v => h - v / my * (h - P);
    const fz = 0.5 / my * (h - P);
    const pts = tr.map(t => [X(t.pc), Y(t.nc)]);
    const last = pts[pts.length - 1];
    const svg = `<svg class="rd-quad" viewBox="0 0 ${S} ${S}" role="img" aria-label="가격 변화와 투기자금 변화 사분면">
      <rect x="${P}" y="${h - fz}" width="${S - 2 * P}" height="${2 * fz}" fill="var(--panel3)" opacity=".6"/>
      <line x1="${P}" x2="${S - P}" y1="${h}" y2="${h}" stroke="var(--line2)"/><line y1="${P}" y2="${S - P}" x1="${h}" x2="${h}" stroke="var(--line2)"/>
      <text x="${S - P}" y="${P - 6}" text-anchor="end">① 추세 매수</text><text x="${P}" y="${P - 6}">③ 하락 중 매수</text>
      <text x="${S - P}" y="${S - 6}" text-anchor="end">② 돈 없이 상승</text><text x="${P}" y="${S - 6}">④ 매도 추세</text>
      <text x="${S - 4}" y="${h - 4}" text-anchor="end">가격↑</text><text x="${h + 4}" y="${P + 10}">돈↑</text>
      ${pts.length > 1 ? `<polyline points="${pts.map(p => p.map(v => v.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3"/>` : ''}
      ${pts.slice(0, -1).map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="var(--dim)"/>`).join('')}
      ${last ? `<circle cx="${last[0]}" cy="${last[1]}" r="7" fill="var(--accent)" stroke="var(--panel)" stroke-width="2"/>` : ''}</svg>`;
    return card(`③ 가격 × 투기자금 — ${mdw(it.cot.obs)} 기준`, `${svg}
      <div class="rd-line" style="margin-top:8px"><b>${esc(q.label)}</b> — ${esc(q.text)} ${q.oi_note ? esc(q.oi_note) : ''}</div>
      ${q.extreme ? `<div class="rd-why" style="margin-top:6px">⚖️ 반대 근거: ${esc(q.extreme)}</div>` : ''}
      <div class="mk-foot">가로 = 그 주 가격 변화(%), 세로 = 투기자금 순매수 변화(미결제약정 대비 %). 회색 점선은 지난 13주 궤적, 주황 점이 이번 주. 가운데 회색 띠(±0.5%)는 “변화 거의 없음”.${it.move && it.move.ref ? ' 가격 변화는 Yahoo 선물 등락률(참고)이에요.' : ''}</div>${srcLine(it.src.cot, it.src.move)}`);
  }

  function invCard(it) {
    const v = it.inv;
    const b = (v.band || []).filter(r => r[1] != null);
    let svg = '';
    if (b.length > 2) {
      const W = 600, H = 170, P = { l: 52, r: 8, t: 10, b: 20 };
      const all = b.flatMap(r => [r[1], r[3], r[4]]).filter(x => x != null);
      let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
      const X = i => P.l + i / (b.length - 1) * (W - P.l - P.r), Y = x => P.t + (hi - x) / (hi - lo) * (H - P.t - P.b);
      const okb = b.map((r, i) => [i, r]).filter(([, r]) => r[3] != null && r[4] != null);
      const area = okb.length > 1 ? `<path d="${okb.map(([i, r], k) => (k ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(r[4]).toFixed(1)).join('')}${okb.slice().reverse().map(([i, r]) => 'L' + X(i).toFixed(1) + ',' + Y(r[3]).toFixed(1)).join('')}Z" fill="var(--blue)" opacity=".15"/>` : '';
      const avg = okb.length > 1 ? `<path d="${okb.map(([i, r], k) => (k ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(r[2]).toFixed(1)).join('')}" fill="none" stroke="var(--blue)" stroke-dasharray="4 3" stroke-width="1.5"/>` : '';
      const line = `<path d="${b.map((r, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(r[1]).toFixed(1)).join('')}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
      const ax = [hi - pad, (hi + lo) / 2, lo + pad].map(x => `<text x="${P.l - 6}" y="${Y(x) + 4}" text-anchor="end" class="mk-ax">${esc(big(x))}</text><line x1="${P.l}" x2="${W - P.r}" y1="${Y(x)}" y2="${Y(x)}" class="mk-grid"/>`).join('');
      svg = `<svg class="rd-band" viewBox="0 0 ${W} ${H}">${ax}${area}${avg}${line}<text x="${P.l}" y="${H - 4}" class="mk-ax">${md(b[0][0])}</text><text x="${W - P.r}" y="${H - 4}" text-anchor="end" class="mk-ax">${md(b[b.length - 1][0])}</text></svg>
        <div class="mk-foot"><span style="color:var(--accent)">━</span> 올해 재고 · <span style="color:var(--blue)">┅</span> 직전 5년 같은 주 평균 · 옅은 파란 띠 = 직전 5년 최저~최고 (올해는 평균에 넣지 않음, EIA 방식)</div>`;
    }
    return card(`④ ${esc(v.name)} — ${mdw(v.obs)} 기준`, `<div class="ust-kv"><div class="mk-sub">이번 주 재고</div><div class="mk-fv">${fN(v.v, 0)} <span class="mk-sub">${esc(v.unit)}</span></div>
        <div class="mk-sub">전주보다 <b class="${cls(v.w1)}">${sct(v.w1)}</b> · 5년 평균보다 <b class="${cls(v.vs5)}">${pct(v.vs5)}</b> ${v.vs5 == null ? '' : v.v > v.hi5 ? '— 5년 범위보다 많아요 (공급 넉넉)' : v.v < v.lo5 ? '— 5년 범위보다 적어요 (공급 빠듯)' : '— 5년 범위 안이에요'}</div></div>
      ${svg}
      <div class="mk-foot">재고가 평균보다 적으면 가격을 받치는 쪽, 많으면 누르는 쪽으로 작용해요. 발표: ${esc(v.pub_rule)} · 다음 예정 ${mdw(v.next)}</div>${srcLine(it.src.inv)}`);
  }

  const LSRC = (it, D, k) => k === 'usd' ? (D.macro.usd || {}).src : k === 'real' ? (D.macro.real || {}).src : k ? (it.src || {})[k] : null;
  function cycleCard(it, D) {
    const cy = it.cycle || {}, lg = cy.long, ph = lg && lg.phase;
    return card('⑤ 사이클 위치 — 긴 흐름에서 지금은 어디쯤?', `
      ${ph ? `<div class="rd-line"><b>${esc(ph.label)}</b> — ${esc(ph.text)} <span class="mk-sub">(규칙 기반 해석: ${lg.years}년 실질가격 ${fN(lg.pct, 0)}% 높이 · 1년 ${pct(lg.mom12, 0)} · ${+lg.obs.slice(5, 7)}월 기준)</span></div>` : `<div class="rd-why">${esc(cy.missing || '장기 사이클을 판단할 자료가 부족해요.')}</div>`}
      <div style="overflow-x:auto"><table class="t" style="margin-top:8px"><tr><th>층</th><th>지금</th><th>뜻</th><th>기준일</th><th>출처</th></tr>${(cy.layers || []).map(l => `<tr><td>${esc(l.k)}</td><td><span class="mk-badge st-${l.st}">${esc(l.v)}</span></td><td>${esc(l.note)}</td><td>${l.d ? md(l.d) : '—'}</td><td>${links(LSRC(it, D, l.src))}</td></tr>`).join('')}</table></div>
      ${(cy.counter || []).length ? `<div class="rd-why" style="margin-top:8px">⚖️ 반대 근거: ${cy.counter.map(esc).join(' ')}</div>` : ''}
      <div class="mk-foot">장기 가격 위치는 IMF 월평균 가격을 미국 CPI로 물가 보정해 지난 20년 중 몇 % 높이인지 본 거예요. 국면 이름은 이 사이트의 규칙으로 붙인 해석이에요 (사이클 탭에서 규칙 확인).</div>`);
  }

  // ══ 🔄 사이클 탭 ═════════════════════════════════════════════
  function cycleTab(D) {
    const order = ['장기 가격 위치', '재고', '투기자금 쏠림', '달러', '실질금리', '공급 투자(CAPEX)'];
    const mac = D.macro || {};
    const rows = D.items.map(it => {
      const cy = it.cycle || {}, by = Object.fromEntries((cy.layers || []).map(l => [l.k, l])), ph = cy.long && cy.long.phase;
      return `<tr><td><a href="#" data-rid="${it.id}">${esc(it.name)}</a></td><td>${ph ? `<b>${esc(ph.label)}</b>` : '<span class="mk-sub">자료 없음</span>'}</td>
        ${order.map(k => { const l = by[k]; return `<td>${l ? `<span class="mk-badge st-${l.st}" title="${esc(l.note)}">${esc(l.v)}</span>` : '<span class="mk-sub">—</span>'}</td>`; }).join('')}</tr>`;
    }).join('');
    const u = mac.usd, r = mac.real;
    return card('🧭 원자재 사이클, 이렇게 접근해요 — 4층으로 나눠 보기', `<div class="rd-ex">
        <div><b>1층 · 장기 가격 위치 (가장 느림, 수년 단위)</b> — 물가를 뺀 실질가격이 지난 20년 중 어느 높이인지 봐요. 아주 높으면 생산자들이 증산 투자에 나서 몇 년 뒤 공급이 늘고, 아주 낮으면 투자를 줄여 몇 년 뒤 부족해져요. <span class="mk-sub">자료: IMF 월평균 가격 + 미국 CPI (FRED)</span></div>
        <div><b>2층 · 재고 (수개월 단위)</b> — 지금 실물이 넉넉한지. 사이클이 돌아서는 첫 신호는 보통 재고에서 나와요(가격이 낮아도 재고가 줄기 시작하면 바닥 신호). <span class="mk-sub">자료: EIA 주간 재고 — 지금은 원유·가스만 공식 무료 자료가 있어요</span></div>
        <div><b>3층 · 투기자금 쏠림 (수주 단위)</b> — 돈이 한쪽으로 얼마나 몰렸는지. 사이클의 꼭대기·바닥 근처에서 극단(3년 중 상위·하위 10%)이 자주 나타나요. <span class="mk-sub">자료: CFTC COT</span></div>
        <div><b>4층 · 거시 바람 (수개월 단위)</b> — 달러가 강하면 원자재 전반에 역풍, 실질금리가 오르면 금·은에 역풍이에요. <span class="mk-sub">자료: 연준 달러지수 · 10년 TIPS 금리 (FRED)</span></div>
        <div><b>+ 공급 투자(CAPEX, 3차 예정)</b> — 생산기업이 설비투자를 늘리는지 줄이는지. 2~5년 뒤 공급을 미리 알려 주는 층이에요.</div>
        <div><b>읽는 법</b> — ① 1층으로 큰 국면을 정하고 → ② 2층(재고)이 그 국면을 확인해 주는지 보고 → ③ 3층(쏠림)이 극단이면 전환 가능성을 의심하고 → ④ 4층(거시)이 순풍인지 역풍인지 더해요. 층들이 같은 방향을 가리킬수록 신호가 강하고, 엇갈리면 결론을 미뤄요.</div></div>
      <div class="mk-foot">국면 규칙(해석): 20년 실질가격 70% 이상 & 1년 상승 = ③ 과열·고점권 · 40% 이상 & 1년 하락 = ④ 하강기 · 30% 이하 & 1년 하락 = ① 바닥권 · 1년 상승(70% 미만) = ② 회복기 · 그 밖 = 중간 지대. 선물 기간구조(콘탱고·백워데이션)는 EIA가 2024년 4월부터 선물 가격 공개를 멈춰 공식 무료 자료가 없어 넣지 않았어요.</div>`)
      + card('📊 원자재별 사이클 위치', `<div style="overflow-x:auto"><table class="t"><tr><th>원자재</th><th>국면 (해석)</th>${order.map(k => `<th>${esc(k)}</th>`).join('')}</tr>${rows}</table></div>
        <div class="mk-foot">칸에 마우스를 올리면 뜻이 나와요. 주황 = 주의 · 초록 = 우호 · 회색 = 중립. 이름을 누르면 그 원자재의 ⑤ 사이클 위치로 가요.</div>
        ${srcLine([{ label: 'FRED (IMF 월평균 가격)', url: 'https://fred.stlouisfed.org/' }, { label: 'FRED CPIAUCSL', url: 'https://fred.stlouisfed.org/series/CPIAUCSL' }, { label: 'EIA 주간 재고', url: 'https://www.eia.gov/petroleum/supply/weekly/' }, { label: 'CFTC COT', url: 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm' }])}`)
      + card('🌬️ 공통 거시 바람', `<div class="ust-g3">
        ${u ? `<div class="ust-kv"><div class="mk-sub">${esc(u.name)}</div><div class="mk-fv">${fN(u.v, 1)}</div><div class="mk-sub">3개월 ${pct(u.c3m)} · 5년 중 ${u.pct5 == null ? '—' : fN(u.pct5, 0) + '%'} 높이 · ${mdw(u.obs)}</div>${srcLine(u.src)}</div>` : ''}
        ${r ? `<div class="ust-kv"><div class="mk-sub">${esc(r.name)}</div><div class="mk-fv">${fN(r.v, 2)}%</div><div class="mk-sub">1년 ${r.c1y == null ? '—' : sgn(r.c1y, 0) + 'bp'} · ${mdw(r.obs)}</div>${srcLine(r.src)}</div>` : ''}</div>
        <div class="mk-foot">흔히 쓰는 DXY는 ICE 거래소의 상표 지수라, 공식 자료인 연준 달러지수(Nominal Broad)로 대신 봐요.</div>`);
  }

  function explain(it) {
    const c = it.cot, mm = c && c.groups.mm, q = it.quad;
    const now = !showCot(it) ? (it.why || '') :
      `${it.name}의 투기자금은 ${mdw(c.obs)} 기준 ${mm.net >= 0 ? `${fN(mm.net, 0)}계약 순매수` : `${fN(-mm.net, 0)}계약 순매도`} 상태이고, 이는 ${pctTxt(mm.pctile)} 수준이에요. 4주 동안 순매수가 ${mm.c4 == null ? '얼마나 바뀌었는지 비교할 자료가 없어요' : mm.c4 === 0 ? '그대로였어요' : fN(Math.abs(mm.c4), 0) + '계약 ' + (mm.c4 > 0 ? '늘었어요' : '줄었어요')}.` +
      (q ? ` 가격과 짝지어 보면 「${q.label}」이에요.` : '') + (it.inv && it.inv.vs5 != null ? (Math.abs(it.inv.vs5) < 0.5 ? ' 실물 재고는 5년 평균과 비슷해요.' : ` 실물 재고는 5년 평균보다 ${fN(Math.abs(it.inv.vs5), 1)}% ${it.inv.vs5 > 0 ? '많아요' : '적어요'}.`) : '');
    return card('🧭 초보자 해설', `<div class="rd-ex">
      <div>📖 <b>쉽게 말하면</b> — 선물 시장에는 실제로 원자재를 쓰는 회사(생산·실수요)와, 가격 흐름에 돈을 거는 투기자금이 함께 있어요. 미국 CFTC는 매주 “누가 얼마나 사고팔아 두었는지”를 공개해요. 투기자금이 한쪽으로 크게 몰리면 가격이 그 방향으로 밀리기도 하지만, 너무 몰리면 되돌아갈 때 크게 출렁여요.</div>
      <div>💡 <b>왜 중요한가</b> — 가격만 보면 “왜 움직였는지”를 알 수 없어요. 돈의 쏠림(포지션)과 실물 상황(재고)을 같이 보면 그 움직임이 오래갈지, 일시적인지 가늠할 수 있어요.</div>
      <div>🔍 <b>지금 이 원자재는</b> — ${esc(now)}</div></div>
      <div class="mk-foot">자동 생성 해설이에요. 투자 권유가 아니며, 결론보다 근거를 확인하는 용도로 쓰세요.</div>`);
  }

  function srcBox(it) {
    const c = it.cot, v = it.inv, p = it.price, m = it.move;
    const li = [];
    if (p) li.push(`가격: 관측 ${pd(p)} · ${esc(p.freq)} · ${links(it.src.price)}`);
    if (m) li.push(`등락률: 관측 ${mdw(m.obs)} · ${esc(m.src)} · ${links(it.src.move)}`);
    if (c) li.push(`CFTC 포지션: 관측 ${mdw(c.obs)} · 발표 ${mdw(c.pub)} · 처음 받은 시각 ${kst(c.seen)} (한국) · 다음 예정 ${mdw(c.next)} · ${links(it.src.cot)}`);
    if (v) li.push(`재고: 관측 ${mdw(v.obs)} · 발표 ${mdw(v.pub)} · 처음 받은 시각 ${kst(v.seen)} (한국) · 다음 예정 ${mdw(v.next)} · ${links(it.src.inv)}`);
    const lg = (it.cycle || {}).long;
    if (lg) li.push(`장기 사이클: ${+lg.obs.slice(5, 7)}월 월평균까지 · ${links(it.src.cyc)}`);
    return card('📅 자료 기준', `<div class="rd-src">${li.map(x => '· ' + x).join('<br>')}</div>
      <div class="mk-foot">관측일 = 자료가 가리키는 날 · 발표일 = 공식 공개일(과거 자료는 발표 일정 기준 추정) · 처음 받은 시각 = 이 사이트가 실제로 받은 시각</div>`);
  }

  // ══ 화면 D. 자료 상태 ═════════════════════════════════════════
  function status(D) {
    const st = x => x ? `<span class="mk-badge st-warn">⚠ ${x}일 늦음</span>` : '<span class="mk-badge st-ok">정상</span>';
    const rows = D.items.map(it => `<tr><td><a href="#" data-rid="${it.id}">${esc(it.name)}</a></td><td>${esc((BADGE[it.status] || BADGE.check)[1])}</td>
      <td>${it.price ? pd(it.price) : '—'}</td>
      <td>${it.move ? `${md(it.move.obs)}${it.move.ref ? ' <span class="rd-ref">참고</span>' : ''}` : '—'}</td>
      <td>${it.cot ? `${md(it.cot.obs)} → ${md(it.cot.pub)} ${st(it.cot.stale)}` : '—'}</td>
      <td>${it.inv ? `${md(it.inv.obs)} → ${md(it.inv.pub)} ${st(it.inv.stale)}` : '—'}</td></tr>`).join('');
    const revs = (D.revisions || []);
    return card('🗂️ 원자재별 최신 자료', `<div style="overflow-x:auto"><table class="t"><tr><th>원자재</th><th>매핑</th><th>가격(관측)</th><th>등락률(관측)</th><th>CFTC 관측 → 발표</th><th>EIA 재고 관측 → 발표</th></tr>${rows}</table></div>
        <div class="mk-foot">“늦음”은 공식 발표 예정일보다 하루 넘게 지났는데 새 자료가 없다는 뜻이에요 (미국 공휴일·정부 셧다운 때는 공식적으로 밀려요). 늦어도 값을 이어 붙이거나 추정하지 않아요.</div>`)
      + card('✏️ 최근 30일 정정 이력', revs.length ? `<table class="t"><tr><th>항목</th><th>관측일</th><th class="num">이전 값</th><th class="num">새 값</th><th>받은 시각</th></tr>${revs.map(r => `<tr><td>${esc(r.sid)}</td><td>${md(r.obs)}</td><td class="num">${fN(r.prev, 0)}</td><td class="num">${fN(r.v, 0)}</td><td>${kst(r.seen)}</td></tr>`).join('')}</table>` : '<div class="mk-sub">최근 30일 동안 CFTC·EIA·FRED가 과거 값을 고친 기록이 없어요. 고치면 이전 값을 지우지 않고 여기에 함께 남겨요.</div>')
      + (D.errors && D.errors.length ? card('⚠ 이번 갱신에서 받지 못한 자료', D.errors.map(e => `<div class="mk-sub">· ${esc(e)}</div>`).join('')) : '')
      + card('🔗 출처 · 이용 조건', `<table class="t"><tr><th>자료</th><th>발표</th><th>이용 조건</th></tr>${Object.values(D.sources || {}).map(s => `<tr><td>${src(s.label, s.url)}</td><td>${esc(s.pub || '')}</td><td>${esc(s.license || '')}</td></tr>`).join('')}</table>`);
  }

  // ══ 화면 E. 해석법·용어 ═══════════════════════════════════════
  function guide() {
    const gl = [['COT (Commitments of Traders)', '미국 CFTC가 매주 금요일 공개하는 선물 포지션 보고서. 그 주 화요일 기준이에요.'], ['Managed Money', GTIP.mm], ['Producer/Merchant', GTIP.pm], ['Swap Dealer', GTIP.sd], ['Other Reportables', GTIP.or],
      ['롱 / 숏', '롱 = 오를 것에 건 매수 포지션, 숏 = 내릴 것에 건 매도 포지션'], ['순포지션', '롱 − 숏. 플러스면 사 둔 쪽이 많아요.'], ['미결제약정 (Open Interest)', '아직 청산되지 않은 계약 총수 — 시장에 걸려 있는 돈의 크기'],
      ['3년 백분위', '이번 주 순포지션이 지난 3년(156주) 중 어느 높이인지. 95%면 3년 중 거의 최고로 많이 사 둔 상태'], ['5년 평균 재고', '직전 5년 같은 주의 평균 재고. 올해 재고가 이보다 적으면 공급이 빠듯하다는 신호'],
      ['계약 단위', '선물 1계약이 실물로 얼마인지. WTI 1계약 = 1,000배럴'], ['매핑 확인 필요', '그 원자재를 대표하는 계약이 CFTC에 없거나, 다른 상품(웃돈 계약 등)이라 숫자를 그대로 믿으면 오해할 수 있는 경우']];
    return card('🧭 이 화면을 읽는 순서', `<ol class="ust-3">
        <li><b>재고</b>부터 — 실물이 넉넉한지(5년 평균보다 많은지) 빠듯한지 봐요.</li>
        <li><b>투기자금 백분위</b> — 돈이 한쪽으로 얼마나 쏠렸는지. 90% 이상·10% 이하는 “쏠림 극단”이라 반대로 튈 위험도 커요.</li>
        <li><b>가격 × 투기자금</b> — 가격과 돈이 같은 방향이면 흐름이 단단하고, 엇갈리면 지속성을 의심해요.</li>
        <li>마지막으로 <b>자료 기준일</b> — CFTC는 화요일 기준을 금요일에 발표해서, 보고서가 나올 때 이미 3일이 지나 있어요.</li></ol>`)
      + card('🔀 가격 × 투기자금 4가지', `<table class="t"><tr><th></th><th>투기자금 순매수 ↑</th><th>투기자금 순매수 ↓</th></tr>
        <tr><th>가격 ↑</th><td><b>① 추세 매수</b><br>상승을 돈이 따라붙음</td><td><b>② 투기자금 없이 상승</b><br>숏 커버·실수요 상승 — 지속성 확인</td></tr>
        <tr><th>가격 ↓</th><td><b>③ 하락 중 저가 매수</b><br>바닥 탐색 또는 성급한 매수</td><td><b>④ 매도 추세 확인</b><br>돈이 하락을 확인</td></tr></table>
        <div class="mk-foot">미결제약정이 함께 늘면 “새 돈이 들어온 움직임”, 줄면 “기존 포지션 정리”로 덧붙여 읽어요. 변화가 미결제약정의 0.5%보다 작으면 “변화 거의 없음”으로 봐요.</div>`)
      + card('🔄 원자재 사이클 보는 법 (요약)', `<div class="rd-ex"><div>원자재는 <b>부족 → 가격 급등 → 증산 투자 → 공급 과잉 → 가격 하락 → 투자 감소 → 다시 부족</b>을 반복해요. 이 흐름은 몇 년~십수 년 걸려요.</div>
        <div>이 사이트는 그 위치를 <b>장기 가격 위치 · 재고 · 투기자금 쏠림 · 거시 바람</b> 4층으로 나눠 봐요. 자세한 방법과 원자재별 표는 <a href="#" data-rg="cycle">🔄 사이클 탭</a>에 있어요.</div></div>`)
      + card('📚 용어 사전', `<div class="ust-gl">${gl.map(([k, d]) => `<div><b>${esc(k)}</b> — ${esc(d)}</div>`).join('')}</div>`)
      + card('📏 이 화면의 원칙', `<ul class="ust-3"><li>가격 숫자는 공식 자료(EIA·IMF)만 실어요. 공식 무료 가격이 없는 금·은·백금·리튬은 가격 숫자를 싣지 않아요.</li>
        <li>빠진 주·늦은 발표는 빈칸으로 두고 이유를 적어요. 이웃 주 값이나 추정으로 채우지 않아요.</li>
        <li>대표 계약이 불확실한 브렌트·알루미늄·리튬은 포지션을 기본으로 숨겨요.</li>
        <li>매수·매도를 추천하지 않아요. 근거와 위험을 보여 주는 화면이에요.</li></ul>`);
  }

  window.RADAR = { page };
})();
