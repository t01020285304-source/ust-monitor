/* 🌐 언어 전환 (한국어 · English · 繁中) — 선택은 이 브라우저에 저장, 주소에 ?lang=en / ?lang=zh 로도 바꿀 수 있음
   화면 코드는 그대로 한국어로 그리고, 그려진 글자를 번역 사전(i18n/en.js · i18n/zh.js)으로 바꾼다.
   숫자는 {0}{1}… 자리표로 빼고 문장 틀만 찾으므로 값·판정은 바뀌지 않는다. 사전에 없는 글은 한국어 그대로 둔다.
   <head>에서 theme.js 다음에 불러온다. 한국어일 때는 아무것도 하지 않는다. */
(function () {
  'use strict';
  const KEY = 'siteLang', LANGS = { ko: '한국어', en: 'English', zh: '繁中' }, HTML_LANG = { ko: 'ko', en: 'en', zh: 'zh-Hant-TW' };
  let L = 'ko';
  try { L = localStorage.getItem(KEY) || 'ko'; } catch (e) { }
  const qp = new URLSearchParams(location.search).get('lang');
  if (LANGS[qp]) { L = qp; try { localStorage.setItem(KEY, L); } catch (e) { } }
  if (!LANGS[L]) L = 'ko';
  document.documentElement.lang = HTML_LANG[L];

  const HAN = /[가-힣]/;
  const NUM = /[+\-−]?\$?\d[\d,]*(?:\.\d+)?/g;
  const SEP = / · | — | – | \| | → /;
  const ATTRS = ['title', 'aria-label', 'placeholder', 'alt'];
  let D = null;
  const missing = new Set();

  // 숫자를 자리표로 뺀 문장 틀 (사전 키) — 사전 만들 때도 이 함수를 그대로 쓴다
  function norm(s) {
    const v = [];
    const k = s.replace(/\s+/g, ' ').trim().replace(NUM, m => { v.push(m); return '{' + (v.length - 1) + '}'; });
    return [k, v];
  }
  function one(s, rec) {
    const [k, v] = norm(s);
    const t = D[k];
    if (t == null) { if (rec) missing.add(k); return null; }
    return t.replace(/\{(\d+)\}/g, (_, i) => v[i] ?? '');
  }
  // 문장 하나를 번역. 통째로 없으면 ' · ' 같은 구분자로 나눠 조각마다 찾는다
  function tr(s) {
    if (!D || !HAN.test(s)) return s;
    const lead = s.match(/^\s*/)[0], trail = s.slice(lead.length).match(/\s*$/)[0];
    const sep = SEP.test(s);
    let t = one(s, !sep);                // 구분자로 이어 붙인 글은 조각 단위로만 사전에 둔다
    if (t == null && sep) {
      const parts = s.split(/( · | — | – | \| | → )/);
      t = parts.map((p, i) => i % 2 || !HAN.test(p) ? p : (one(p, true) ?? p)).join('').trim();
    }
    return t == null ? s : lead + t + trail;
  }
  const skip = n => { const e = n.nodeType === 1 ? n : n.parentElement; return !e || !!e.closest('script,style,textarea,[data-noi18n]'); };
  function node(n) {
    if (n.nodeType === 3) {
      if (HAN.test(n.nodeValue) && !skip(n)) { const t = tr(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
    } else if (n.nodeType === 1) {
      for (const a of ATTRS) { const v = n.getAttribute(a); if (v && HAN.test(v) && !skip(n)) { const t = tr(v); if (t !== v) n.setAttribute(a, t); } }
    }
  }
  function walk(root) {
    if (root.nodeType !== 1) return node(root);
    node(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    while (w.nextNode()) node(w.currentNode);
  }
  function start() {
    walk(document.documentElement);
    new MutationObserver(ms => {
      for (const m of ms) {
        if (m.type === 'childList') m.addedNodes.forEach(walk);
        else node(m.target);
      }
    }).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    document.documentElement.classList.remove('i18n-wait');
  }

  // 언어 버튼 — 화면 전환 막대 오른쪽 끝
  function bar() {
    const nav = document.querySelector('.sw-bar'); if (!nav) return;
    const box = document.createElement('span');
    box.className = 'lang-bar'; box.dataset.noi18n = '';
    box.innerHTML = Object.keys(LANGS).map(k => `<button type="button" data-lang="${k}" class="${k === L ? 'on' : ''}" lang="${HTML_LANG[k]}">${LANGS[k]}</button>`).join('');
    box.onclick = e => {
      const b = e.target.closest('[data-lang]'); if (!b || b.dataset.lang === L) return;
      try { localStorage.setItem(KEY, b.dataset.lang); } catch (x) { }
      const u = new URL(location.href); u.searchParams.delete('lang');
      location.replace(u.href);           // 처음부터 다시 그려야 원문 → 새 언어로 깔끔하게 바뀐다
      if (u.href === location.href) location.reload();
    };
    nav.appendChild(box);
  }
  document.addEventListener('DOMContentLoaded', bar);

  window.I18N = { lang: L, norm, tr: s => tr(s), missing, load(dict) { D = dict; if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start(); } };
  if (L === 'ko') return;
  // 사전을 받는 동안 한국어가 번쩍 보이지 않게 잠깐 숨김 (4초 넘으면 그냥 보여 줌)
  document.documentElement.classList.add('i18n-wait');
  const st = document.createElement('style'); st.textContent = 'html.i18n-wait body{visibility:hidden}'; document.head.appendChild(st);
  setTimeout(() => document.documentElement.classList.remove('i18n-wait'), 4000);
  const s = document.createElement('script'); s.src = 'i18n/' + L + '.js?v=8fe100b1'; s.onerror = () => document.documentElement.classList.remove('i18n-wait');
  document.head.appendChild(s);
})();
