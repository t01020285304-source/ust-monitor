/* 데이터 주소 — GitHub에 올린 뒤 아래 두 칸만 내 것으로 바꾸세요 (배포가이드.md 4단계)
   GitHub Actions가 하루 4번 data 브랜치에 ust.json 을 새로 올리고, 화면은 그 파일을 읽어요.
   비워 두면(또는 주소가 틀리면) 사이트에 함께 올린 data/ust.json 을 보여 줘요 (올릴 때 시점의 자료). */
window.UST_CFG = (function () {
  var GITHUB_USER = 't01020285304-source';
  var REPO = 'ust-monitor';
  var ok = GITHUB_USER.indexOf('내-') !== 0;
  return { DATA_URL: ok ? 'https://raw.githubusercontent.com/' + GITHUB_USER + '/' + REPO + '/data/ust.json' : '' };
})();
