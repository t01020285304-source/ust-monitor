"""국채 위기 모니터 데이터 만들기 — 공식 원자료를 받아 판독한 결과를 JSON 한 파일로 저장

사용:  python builder/build.py [출력 경로]      (기본: site/data/ust.json)
GitHub Actions가 정해진 시간마다 이 파일을 실행해 data 브랜치에 올리고, 사이트는 그 파일을 읽어 그린다.
"""
import json
import math
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import treasury  # noqa: E402

KST = timezone(timedelta(hours=9))


def _clean(x):
    """JSON에 쓸 수 없는 NaN·무한대는 null로 (브라우저가 파일을 못 읽는 문제 방지)"""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "site" / "data" / "ust.json"
    t0 = time.time()
    s = _clean(dict(treasury.build_state()))
    s["built_at"] = datetime.now(KST).isoformat(timespec="minutes")
    s.pop("my", None)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out)
    # 내 PC에서 index.html 을 더블클릭(file://)으로 열 때는 브라우저가 JSON 읽기를 막는다 → 같은 내용을 스크립트로도 저장
    js = out.with_name("ust-data.js")
    js.write_text("window.UST_SNAPSHOT=" + json.dumps(s, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + ";", encoding="utf-8")
    errs = s.get("errors") or []
    print(f"완료: {out} ({out.stat().st_size / 1024:.0f} KB, {time.time() - t0:.0f}초) · 받지 못한 자료 {len(errs)}개")
    for e in errs:
        print("  -", e)
    # 핵심 자료(입찰 결과)가 없으면 실패로 끝내서, 이전에 올라간 정상 데이터가 그대로 유지되게 한다
    if not ((s.get("auctions") or {}).get("rows")):
        print("입찰 결과를 받지 못해 이번 갱신을 건너뜁니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
