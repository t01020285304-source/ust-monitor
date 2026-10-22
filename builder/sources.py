"""국채 위기 모니터용 최소 수집 도구 — 원본(가격결정자_리서치/sources.py)에서 국채 모니터가 쓰는 부분만 옮김
   캐시: builder/data/cache (GitHub Actions에서는 data 브랜치에 함께 저장해 다음 실행 때 다시 씀)"""
import json
import math
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent


DATA_DIR = Path(os.environ.get("PR_DATA_DIR") or (BASE_DIR / "data"))


CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cached(name, max_age_sec, loader):
    path = CACHE_DIR / name
    if path.exists() and time.time() - path.stat().st_mtime < max_age_sec:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data = loader()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


PD_API = "https://markets.newyorkfed.org/api/pd/get/{sb}/timeseries/{ids}.json"


PD_PAGE = "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics"


PD_NET = {
    "us_tsy": ["PDPOSGST-TOT"],
    "tips": ["PDPOSTIPS-L2", "PDPOSTIPS-G2", "PDPOSTIPS-G6L11", "PDPOSTIPS-G11"],
    "frn": ["PDPOSGS-BFRN"],
    "agency": ["PDPOSFGS-TOT"],
    "mbs": ["PDPOSMBS-TOT"],
    "corp": ["PDPOSCS-TOT"],
    "muni": ["PDPOSSMGO-L13", "PDPOSSMGO-G13", "PDPOSSMGO-G5L10", "PDPOSSMGO-G10"],
    "abs": ["PDPOSABS-TOT"],
}


PD_REPO = ["PDSORA-UTSETTOT", "PDSORA-UTSTTOT", "PDSORA-FGMTOT", "PDSORA-FGEMTOT", "PDSORA-CDTOT", "PDSORA-ABSTOT", "PDSORA-ETOT"]


PD_RREPO = ["PDSIRRA-UTSETTOT", "PDSIRRA-UTSTTOT", "PDSIRRA-FGMTOT", "PDSIRRA-FGEMTOT", "PDSIRRA-ABSTOT", "PDSIRRA-ETOT"]


PD_LABEL = {"total": "전체 순포지션", "us_tsy": "미 국채 (TIPS 제외)", "tips": "TIPS (물가연동채)", "agency": "정부기관채 (MBS 제외)",
            "mbs": "MBS (모기지채)", "corp_muni": "회사채 + 지방채", "abs_frn": "ABS + 변동금리채", "repo": "Repo (딜러 차입)",
            "net_fin": "순차입 (Repo − 역Repo)"}


def _pd_assess(vals, lookback=8, rising_bad=False):
    """vals: 날짜순 값 목록 → 원본 assess_state 와 동일.
    rising_bad: Repo·순차입은 원본 해석 카드대로 '증가'가 위험 신호 (+5% 경계, +12% 방어)"""
    if len(vals) < 2:
        return {"state": "?", "pct": 0.0, "latest": vals[-1] if vals else 0.0}
    latest = vals[-1]
    if len(vals) < lookback * 2:
        return {"state": "정상", "pct": 0.0, "latest": latest}
    recent = sum(vals[-lookback:]) / lookback
    prev = sum(vals[-lookback * 2:-lookback]) / lookback
    pct = (recent - prev) / abs(prev) * 100 if prev else 0.0
    x = -pct if rising_bad else pct
    st = "방어" if x <= -12 else "경계" if x <= -5 else "정상"
    return {"state": st, "pct": round(pct, 1), "latest": latest}


def _pd_fetch(ids):
    rows = {}
    for sb in ("SBN2022", "SBN2024"):
        r = requests.get(PD_API.format(sb=sb, ids="_".join(ids)), timeout=40)
        r.raise_for_status()
        for x in r.json().get("pd", {}).get("timeseries", []):
            try:
                v = float(x["value"])
            except (TypeError, ValueError):
                continue
            rows.setdefault(x["keyid"], {})[x["asofdate"]] = v
    return rows


def _rates_vol():
    """금리 변동성 동반 여부: FRED 10년물 8주 변화 + MOVE 지수(Yahoo)"""
    out = {}
    try:
        import markets          # 같은 FRED 받기 함수 사용 (API 키가 있으면 공식 API)
        rows = [tuple(x) for x in markets.fred("DGS10")]
        last = rows[-1]
        cut = (datetime.fromisoformat(last[0]) - timedelta(weeks=8)).date().isoformat()
        base = [x for x in rows if x[0] <= cut][-1]
        out["dgs10"] = {"date": last[0], "v": last[1], "chg8w_bp": round((last[1] - base[1]) * 100), "url": "https://fred.stlouisfed.org/series/DGS10"}
    except Exception as e:
        out["dgs10_error"] = str(e)
    try:
        import yfinance as yf
        h = yf.Ticker("^MOVE").history(period="6mo")["Close"].dropna()
        if len(h) > 45:
            out["move"] = {"date": h.index[-1].strftime("%Y-%m-%d"), "v": round(float(h.iloc[-1]), 1),
                           "pct8w": round((float(h.iloc[-1]) / float(h.iloc[-41]) - 1) * 100, 1),
                           "url": "https://finance.yahoo.com/quote/%5EMOVE/"}
    except Exception as e:
        out["move_error"] = str(e)
    return out


def dealer_macro():
    def load():
        ids = [k for v in PD_NET.values() for k in v]
        raw = _pd_fetch(ids)
        raw.update(_pd_fetch(PD_REPO + PD_RREPO))
        dates = sorted({d for k in ids for d in raw.get(k, {})})[-105:]

        def ff(k):                                        # 어떤 주에 한 항목만 빠지면 0이 아니라 직전 값으로 채운다 (가짜 급감 방지)
            src, last, out = raw.get(k, {}), None, []
            if src:
                prev = [d for d in src if d < dates[0]]
                last = src[max(prev)] if prev else None
            for d in dates:
                last = src.get(d, last)
                out.append(last or 0.0)
            return out
        F_ = {k: ff(k) for k in set(ids) | set(PD_REPO) | set(PD_RREPO)}
        ser = {cat: [sum(F_[k][i] for k in ks) for i in range(len(dates))] for cat, ks in PD_NET.items()}
        repo = [sum(F_[k][i] for k in PD_REPO) for i in range(len(dates))]
        rrepo = [sum(F_[k][i] for k in PD_RREPO) for i in range(len(dates))]
        comb = {
            "total": [sum(ser[c][i] for c in PD_NET) for i in range(len(dates))],
            "us_tsy": ser["us_tsy"], "tips": ser["tips"], "agency": ser["agency"], "mbs": ser["mbs"],
            "corp_muni": [a + b for a, b in zip(ser["corp"], ser["muni"])],
            "abs_frn": [a + b for a, b in zip(ser["abs"], ser["frn"])],
            "repo": repo, "net_fin": [a - b for a, b in zip(repo, rrepo)],
        }
        states = {k: dict(_pd_assess(v, rising_bad=k in ("repo", "net_fin")), label=PD_LABEL[k]) for k, v in comb.items()}
        np_pct, rp_pct = states["total"]["pct"], states["repo"]["pct"]
        if np_pct <= -12 and rp_pct >= 5:
            mk = {"key": "defense", "label": "방어 패턴", "desc": "순포지션 급감 + Repo 의존도 증가. 시장 완충 장치 제거 중."}
        elif np_pct <= -5:
            mk = {"key": "caution", "label": "경계 구간", "desc": "순포지션 감소 시작. 위험 흡수 비중 축소 중."}
        else:
            mk = {"key": "normal", "label": "정상 범위", "desc": "순포지션 유지/증가. 시장을 떠받칠 의지 있음."}
        rates = _rates_vol()
        d10, mv = rates.get("dgs10") or {}, rates.get("move") or {}
        rates["vol_up"] = abs(d10.get("chg8w_bp") or 0) >= 30 or (mv.get("pct8w") or 0) >= 15
        return {"asof": dates[-1] if dates else None, "fetched_at": datetime.now().isoformat(timespec="minutes"),
                "market": mk, "states": states, "rates": rates,
                "spark": {"dates": dates[-52:], "total": [round(x / 1000, 1) for x in comb["total"][-52:]],
                          "net_fin": [round(x / 1000, 1) for x in comb["net_fin"][-52:]]},
                "src": {"page": PD_PAGE, "api": PD_API.format(sb="SBN2024", ids="PDPOSGST-TOT"),
                        "label": "NY 연준 Primary Dealer Statistics (매주 목요일 갱신, 단위 백만 달러)"}}
    return _cached("nyfed_pd.json", 6 * 3600, load)
