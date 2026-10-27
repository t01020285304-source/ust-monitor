#!/usr/bin/env bash
# 데이터 만들기 → data 브랜치에 올리기를 LOOP_MIN분 동안 15분마다 반복
#   GitHub는 예약 실행을 자주 건너뛰어서(실측 하루 5번 남짓), 한 번 시작된 실행이 스스로 오래 돌며 갱신을 이어 간다.
#   공개 저장소라 Actions 사용 시간은 무료. 다음 예약 실행은 concurrency 로 이 실행이 끝날 때까지 기다린다.
set -u
END=$(( $(date +%s) + ${LOOP_MIN:-0} * 60 ))
export CACHE_CAP=${CACHE_CAP:-840}          # 반복 사이에 저장본을 14분까지만 재사용 → 매일 발표 자료를 다음 반복에서 바로 받음

publish() {
  if [ -f out/SKIP ]; then echo "건너뜀: $(cat out/SKIP)"; return 0; fi
  rm -rf pub && mkdir -p pub
  cp -r out/. pub/ 2>/dev/null || true
  rm -f pub/ust-data.js pub/SKIP          # 웹 화면은 ust.json 만 읽음
  rm -rf pub/cache pub/.git && mkdir -p pub/cache && cp -r builder/data/cache/. pub/cache/ || true
  (
    cd pub
    git init -q
    git config user.name "ust-monitor-bot"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git checkout -q -b data
    git add -A
    git commit -q -m "데이터 갱신 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M') KST"
    git push -q -f "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" data
  ) && echo "올림: $(TZ=Asia/Seoul date '+%H:%M') KST"
}

i=0
while true; do
  i=$((i + 1))
  rm -f out/SKIP
  echo "── ${i}번째 갱신 $(TZ=Asia/Seoul date '+%H:%M') KST"
  if python builder/build.py out/ust.json; then publish; else echo "만들기 실패 — 다음 반복에서 다시"; fi
  [ "$(date +%s)" -ge "$END" ] && break
  sleep 900
done
