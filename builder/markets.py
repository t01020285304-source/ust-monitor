"""국채 위기 모니터용 최소 시세 도구 — 원본(가격결정자_리서치/markets.py)에서 FRED·Yahoo 차트 함수만 옮김"""
import json
import os
import threading
import time
from datetime import date, datetime, timedelta

import requests

import sources

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


_MEM = {}


_MLOCK = threading.Lock()


def _mem(key, age, loader):
    """메모리 캐시 (짧은 주기 데이터용). 실패하면 직전 값을 돌려준다."""
    with _MLOCK:
        c = _MEM.get(key)
    if c and time.time() - c[0] < age:
        return c[1]
    try:
        v = loader()
    except Exception:
        if c:
            return c[1]
        raise
    with _MLOCK:
        _MEM[key] = (time.time(), v)
    return v


def yahoo_chart(symbol, rng="1d", interval="5m"):
    def load():
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}",
                         params={"range": rng, "interval": interval, "includePrePost": "false"}, headers=UA, timeout=15)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        m = res["meta"]
        ts = res.get("timestamp") or []
        q = (res.get("indicators", {}).get("quote") or [{}])[0]
        cl = q.get("close") or []
        pts = [[t, round(c, 4)] for t, c in zip(ts, cl) if c is not None]
        return {"symbol": symbol, "name": m.get("shortName") or m.get("longName"), "currency": m.get("currency"),
                "price": m.get("regularMarketPrice"), "prev": m.get("chartPreviousClose") if rng != "1d" else (m.get("previousClose") or m.get("chartPreviousClose")),
                "time": m.get("regularMarketTime"), "tz": m.get("exchangeTimezoneName"), "gmtoffset": m.get("gmtoffset"),
                "high52": m.get("fiftyTwoWeekHigh"), "low52": m.get("fiftyTwoWeekLow"), "points": pts,
                "url": f"https://finance.yahoo.com/quote/{requests.utils.quote(symbol)}/"}
    return _mem(f"y:{symbol}:{rng}:{interval}", 60 if rng == "1d" else 600, load)


def fred(series, start=None, age=6 * 3600):
    start = start or (date.today() - timedelta(days=800)).isoformat()

    def load():
        key = os.environ.get("FRED_API_KEY", "").strip()
        if key:     # GitHub 서버 등 클라우드에서는 fredgraph CSV가 막혀서 공식 API(무료 키)로 받는다
            r = requests.get("https://api.stlouisfed.org/fred/series/observations", timeout=40,
                             params={"series_id": series, "observation_start": start, "api_key": key, "file_type": "json"})
            r.raise_for_status()
            rows = []
            for o in r.json().get("observations", []):
                try:
                    rows.append([o["date"], float(o["value"])])
                except (ValueError, KeyError):
                    pass
            if not rows:
                raise ValueError(f"FRED {series} 데이터 없음")
            return rows
        # FRED 는 '브라우저 흉내' 헤더를 단 스크립트 요청을 지연·차단한다 → 솔직한 식별자로 요청
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series, "cosd": start},
                         headers={"User-Agent": "MangoResearch/1.0 (personal research)"}, timeout=40)
        r.raise_for_status()
        rows = []
        for ln in r.text.strip().splitlines()[1:]:
            p = ln.split(",")
            if len(p) == 2 and p[1] not in (".", ""):
                try:
                    rows.append([p[0], float(p[1])])
                except ValueError:
                    pass
        if not rows:
            raise ValueError(f"FRED {series} 데이터 없음 (FRED가 데이터 대신 다른 페이지를 돌려줌)")
        return rows
    try:
        return sources._cached(f"fred_{series}_{start[:7]}.json", age, load)
    except Exception:
        # FRED 일시 차단·장애 → 가장 최근에 저장해 둔 같은 시리즈를 대신 씀 (마지막 날짜가 곧 '언제 자료인지'를 보여줌)
        old = sorted(sources.CACHE_DIR.glob(f"fred_{series}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in old:
            try:
                rows = [r for r in json.loads(p.read_text(encoding="utf-8")) if r[0] >= start]
                if rows:
                    print(f"[fred] {series}: 새로 받기 실패 → 저장본 사용 ({p.name}, 마지막 {rows[-1][0]})")
                    return rows
            except Exception:
                continue
        raise


def fred_url(series):
    return f"https://fred.stlouisfed.org/series/{series}"
