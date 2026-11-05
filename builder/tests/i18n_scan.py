"""번역 사전 점검 — 모든 화면을 실제 브라우저로 열어 사전에 없는 한국어 문장 틀을 모은다 (수동 실행용, Actions 에서는 안 돌림)
준비: pip install playwright && playwright install chromium
실행: python builder/tests/i18n_scan.py [en|zh] [결과.json]   → 빠진 문장 틀 목록(어느 화면에서 봤는지 포함)을 출력
사이트 폴더를 임시 웹서버로 띄우고, 자료는 실제 사이트처럼 GitHub data 브랜치(실패하면 site/data)에서 읽는다."""
import http.server
import json
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[2] / "site"
LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
OUT = sys.argv[2] if len(sys.argv) > 2 else None
UST_TABS = ["op", "force", "pipes", "auc", "chain", "cal", "liq", "repo", "absorb", "rates", "issue", "int", "credit", "japan", "contra", "guide"]


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = partial(Quiet, directory=str(SITE))
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def main():
    port = serve()
    base = f"http://127.0.0.1:{port}/index.html?lang={LANG}"
    seen = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        def grab(view):
            pg.wait_for_timeout(400)
            pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            pg.wait_for_timeout(150)
            for k in pg.evaluate("[...I18N.missing]"):
                seen.setdefault(k, view)
            pg.evaluate("I18N.missing.clear()")

        def goto(h):
            pg.evaluate(f"location.hash = {json.dumps(h)}")
            pg.wait_for_function("!document.querySelector('.mk-loading')", timeout=30000)

        pg.goto(base + "#op")
        pg.wait_for_function("window.I18N && !document.querySelector('.mk-loading')", timeout=60000)
        grab("load")
        for t in UST_TABS:
            goto(t)
            grab(t)
        n = pg.evaluate("document.querySelectorAll('.ust-row').length")
        goto("auc")
        for i in range(n):
            pg.evaluate(f"document.querySelectorAll('.ust-row')[{i}].dispatchEvent(new CustomEvent('pick',{{bubbles:true}}))")
            grab(f"auc/{i}")
        goto("radar")
        grab("radar")
        for g in pg.evaluate("[...document.querySelectorAll('[data-grp]')].map(b => b.dataset.grp)"):
            pg.click(f"[data-grp='{g}']")
            grab("radar grp " + g)
        ids = [x["id"] for x in json.loads((SITE / "data" / "radar.json").read_text(encoding="utf-8"))["items"]]
        for v in ["cycle", "status", "guide"] + ids:
            goto("radar/" + v)
            grab("radar/" + v)
            for r in pg.evaluate("[...document.querySelectorAll('[data-ref]')].map(b => b.dataset.ref)"):
                pg.click(f"[data-ref='{r}']")
                grab(f"radar/{v} ref")
        # 차트 위 말풍선
        goto("rates")
        box = pg.query_selector("svg.mkc")
        if box:
            bb = box.bounding_box()
            pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
            grab("tooltip")
        b.close()
    print(f"[{LANG}] 사전에 없는 문장 틀 {len(seen)}개, 화면 오류 {len(errs)}개")
    for e in errs:
        print("  오류:", e)
    if OUT:
        Path(OUT).write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")
    else:
        for k, v in seen.items():
            print(f"  [{v}] {k}")


if __name__ == "__main__":
    main()
