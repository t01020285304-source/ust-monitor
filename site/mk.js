/* 공통 도우미 — 원본(가격결정자_리서치/web/markets.js)의 선 그래프·출처 링크·숫자 표기 함수만 옮김 */
(function () {
  'use strict';
  // 늦게 도착한 응답이 이미 사라진 칸에 쓰더라도 오류가 나지 않게, 없는 요소 대신 빈 객체를 돌려준다
  const $ = s => document.querySelector(s) || { style: {}, dataset: {}, classList: { toggle() { } } };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fN = (v, d = 2) => v == null || !isFinite(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sgn = (v, d = 2) => v == null || !isFinite(v) ? '—' : (v > 0 ? '+' : '') + fN(v, d);
  const ud = v => v > 0 ? 'up' : v < 0 ? 'dn' : '';
  const usdB = v => v == null ? '—' : v >= 1e12 ? `$${fN(v / 1e12, 2)}T` : v >= 1e9 ? `$${fN(v / 1e9, 1)}B` : `$${fN(v / 1e6, 0)}M`;
  const src = (label, url) => url ? `<a class="mk-src" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} ↗</a>` : `<span class="mk-src">${esc(label)}</span>`;
  // ── 선 그래프 (단일 축 · 2px 선 · 마우스 위치의 값 표시) ──────────────
  let CHN = 0; const CH = {};
  function lineSvg(rows, o = {}) {
    const pts = (rows || []).filter(r => r && r[1] != null && isFinite(r[1])).map(r => [typeof r[0] === 'number' ? r[0] * 1000 : Date.parse(r[0]), +r[1], r[0]]);
    if (pts.length < 2) return '<div class="mk-empty">그래프를 그릴 데이터가 부족해요</div>';
    const W = o.w || 600, H = o.h || 150, P = { l: o.axis === false ? 4 : 52, r: 8, t: 10, b: o.axis === false ? 4 : 22 };
    let lo = Math.min(...pts.map(p => p[1])), hi = Math.max(...pts.map(p => p[1]));
    if (o.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (o.ref != null) { lo = Math.min(lo, o.ref); hi = Math.max(hi, o.ref); }
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.01 || 1; lo -= pad; hi += pad;
    const x0 = pts[0][0], x1 = pts[pts.length - 1][0];
    const X = t => P.l + (t - x0) / ((x1 - x0) || 1) * (W - P.l - P.r);
    const Y = v => P.t + (hi - v) / (hi - lo) * (H - P.t - P.b);
    const color = o.color || 'var(--accent)';
    const id = 'c' + (++CHN);
    const xy = pts.map(p => [X(p[0]), Y(p[1])]);
    CH[id] = { pts: pts.map((p, i) => [xy[i][0], xy[i][1], p[2], p[1]]), W, H, fmt: o.fmt || (v => fN(v, 2)), intraday: typeof rows[0][0] === 'number' };
    const d = xy.map((q, i) => (i ? 'L' : 'M') + q[0].toFixed(1) + ',' + q[1].toFixed(1)).join('');
    const area = o.area ? `<path d="${d}L${xy[xy.length - 1][0].toFixed(1)},${H - P.b}L${xy[0][0].toFixed(1)},${H - P.b}Z" fill="url(#g${id})" opacity=".35"/>
      <defs><linearGradient id="g${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${color}"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>` : '';
    const gl = o.axis === false ? '' : [hi - pad, (hi + lo) / 2, lo + pad].map(v => `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}" class="mk-grid"/><text x="${P.l - 6}" y="${Y(v) + 4}" text-anchor="end" class="mk-ax">${esc((o.axfmt || o.fmt || (x => fN(x, 1)))(v))}</text>`).join('')
      + `<text x="${P.l}" y="${H - 5}" class="mk-ax">${esc(lbl(pts[0][2]))}</text><text x="${W - P.r}" y="${H - 5}" text-anchor="end" class="mk-ax">${esc(lbl(pts[pts.length - 1][2]))}</text>`;
    const zl = o.zero && lo < 0 && hi > 0 ? `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(0)}" y2="${Y(0)}" class="mk-zero"/>` : '';
    const rl = o.ref != null ? `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(o.ref)}" y2="${Y(o.ref)}" class="mk-ref"/>` : '';
    const mk = (o.marks || []).map(m => { const i = pts.findIndex(p => p[2] === m.x); return i < 0 ? '' : `<circle cx="${xy[i][0]}" cy="${xy[i][1]}" r="4" fill="${m.color}" stroke="var(--panel)" stroke-width="2"/>`; }).join('');
    return `<svg class="mkc" data-ch="${id}" viewBox="0 0 ${W} ${H}">${gl}${zl}${rl}${area}<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>${mk}
      <line class="xh" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" style="display:none"/><circle class="xd" r="4" fill="${color}" stroke="var(--panel)" stroke-width="2" style="display:none"/></svg>`;
  }
  function lbl(x) {
    if (typeof x === 'number') { const d = new Date(x * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; }
    return String(x).slice(2).replace(/-/g, '.');
  }
  document.addEventListener('mousemove', e => {
    const svg = e.target.closest && e.target.closest('svg.mkc'), tip = $('#mkTip');
    document.querySelectorAll('svg.mkc .xh, svg.mkc .xd').forEach(n => { if (!svg || !svg.contains(n)) n.style.display = 'none'; });
    if (!svg) { tip.style.display = 'none'; return; }
    const c = CH[svg.dataset.ch]; if (!c) return;
    const r = svg.getBoundingClientRect(), xv = (e.clientX - r.left) / r.width * c.W;
    let best = c.pts[0]; for (const p of c.pts) if (Math.abs(p[0] - xv) < Math.abs(best[0] - xv)) best = p;
    const xh = svg.querySelector('.xh'), xd = svg.querySelector('.xd');
    xh.setAttribute('x1', best[0]); xh.setAttribute('x2', best[0]); xh.style.display = '';
    xd.setAttribute('cx', best[0]); xd.setAttribute('cy', best[1]); xd.style.display = '';
    const dl = typeof best[2] === 'number' ? new Date(best[2] * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : best[2];
    tip.innerHTML = `<div class="tt-d">${esc(dl)}</div><div class="tt-v">${esc(c.fmt(best[3]))}</div>`;
    tip.style.display = 'block';
    tip.style.left = Math.min(window.innerWidth - 150, e.clientX + 14) + 'px'; tip.style.top = (e.clientY - 46) + 'px';
  });
  window.MK = { $, esc, fN, sgn, ud, src, lineSvg };
})();
