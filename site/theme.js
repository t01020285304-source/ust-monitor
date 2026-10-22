/* 화이트 / 블랙 화면 전환 — 선택은 이 브라우저에 저장 (기본: 블랙)
   <head>에서 가장 먼저 불러와 화면이 깜빡이지 않게 한다. 바꾸면 'themechange' 이벤트로 차트 등을 다시 그린다. */
(function () {
  'use strict';
  const KEY = 'siteTheme';
  let t = 'dark';
  try { t = localStorage.getItem(KEY) || 'dark'; } catch (e) { }
  const qp = new URLSearchParams(location.search).get('theme');      // 주소에 ?theme=light 로도 바꿀 수 있게
  if (qp === 'light' || qp === 'dark') { t = qp; try { localStorage.setItem(KEY, t); } catch (e) { } }
  document.documentElement.dataset.theme = t;
  function set(n) {
    document.documentElement.dataset.theme = n;
    try { localStorage.setItem(KEY, n); } catch (e) { }
    const b = document.getElementById('themeBtn');
    if (b) b.innerHTML = n === 'light' ? '🌙 블랙' : '☀️ 화이트';
    window.dispatchEvent(new CustomEvent('themechange', { detail: n }));
  }
  window.SiteTheme = { get: () => document.documentElement.dataset.theme, set, toggle: () => set(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light') };
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.createElement('button');
    b.id = 'themeBtn';
    b.type = 'button';
    b.title = '화면 색 바꾸기 (화이트 / 블랙)';
    b.innerHTML = document.documentElement.dataset.theme === 'light' ? '🌙 블랙' : '☀️ 화이트';
    b.onclick = () => window.SiteTheme.toggle();
    document.body.appendChild(b);
  });
})();
