# -*- coding: utf-8 -*-
"""
🏦 사모신용(BDC) 모니터 — 「돈을 기다리는 사람들」 보고서 12~15번 지표 (SEC 공시, 분기)
  12 PIK 이자 비중   : 이자를 현금 대신 원금에 얹어 받는 비율 (XBRL InterestIncomeOperatingPaidInKind 등 ÷ 총 투자수익, 연초 이후 누적)
  13 Non-accrual     : 이자 인식을 멈춘 대출 비율 — 원가 기준·공정가치 기준을 따로 (10-Q 표 원문)
  14 환매           : 비상장 BDC(BCRED 등)의 환매 요청 vs 지급 한도 — 공개 형식이 제각각이라 원문 링크로 확인
  15 신용한도        : 펀드가 은행에서 더 빌릴 수 있는 남은 한도 (XBRL LineOfCreditFacilityRemainingBorrowingCapacity)
  + 펀드 빚 ÷ 순자산(Debt/NAV) — 펀드가 빌린 돈은 펀드의 빚이지 대출받은 기업의 빚이 아님 (중복 합산 금지)
출처 등급: SEC XBRL·10-Q 원문(A+). 새 10-Q/10-K가 나오면 다시 계산, 그 전까지 접수번호별 캐시.
이 파일은 가격결정자_리서치와 국채위기모니터(builder) 양쪽에서 같은 내용으로 사용.
"""
import html as _html
import json
import os
import re
import time
from datetime import date
from pathlib import Path

import requests

UNIVERSE = [  # (표시 이름, 티커 또는 None, CIK, 설명)
    ("ARCC", "ARCC", "0001287750", "Ares Capital — 최대 상장 BDC"),
    ("OBDC", "OBDC", "0001655888", "Blue Owl Capital Corp"),
    ("BXSL", "BXSL", "0001736035", "Blackstone Secured Lending"),
    ("FSK", "FSK", "0001422183", "FS KKR Capital"),
    ("BCRED", None, "0001803498", "Blackstone Private Credit Fund — 비상장(환매 제한형)"),
]
PIK_TAGS = ["InterestAndDividendIncomeOperatingPaidInKind", "InterestIncomeOperatingPaidInKind", "PaidInKindInterest"]
INC_TAGS = ["GrossInvestmentIncomeOperating", "InvestmentIncomeInterestAndDividend", "Revenues", "InvestmentIncomeInterest"]
DEBT_TAGS = ["DebtLongtermAndShorttermCombinedAmount", "LongTermDebt", "DebtInstrumentCarryingAmount"]
try:
    import sources as _src                       # 가격결정자 사이트: 기존 SEC 헤더·간격·캐시 사용
    HDR, CACHE, _throttle = _src.SEC_HEADERS, _src.CACHE_DIR, _src.sec_throttle
except Exception:                               # 국채위기모니터(GitHub): 개인 이메일 없이 사이트 주소로 신분 표시 (SEC는 noreply 주소를 403으로 막음)
    HDR = {"User-Agent": os.environ.get("SEC_USER_AGENT") or "MangoUSTMonitor https://mango-ust.netlify.app"}
    CACHE = Path(os.environ.get("PR_DATA_DIR") or Path(__file__).parent / "data") / "cache"
    CACHE.mkdir(parents=True, exist_ok=True)
    _last = [0.0]

    def _throttle():
        w = 0.15 - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()


def _get(url, as_json=False):
    _throttle()
    r = requests.get(url, headers=HDR, timeout=90)
    r.raise_for_status()
    return r.json() if as_json else r.text


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _fact(g, tags, instant=False, pair=None):
    """가장 최근 값. pair=(start,end)면 같은 기간 값."""
    for tg in tags:
        u = [x for x in (g.get(tg) or {}).get("units", {}).get("USD", []) if x.get("form") in ("10-Q", "10-K")]
        if instant:
            u = [x for x in u if not x.get("start")]
        else:
            u = [x for x in u if x.get("start")]
        if pair:
            u = [x for x in u if (x.get("start"), x["end"]) == pair]
        if u:
            x = sorted(u, key=lambda x: (x["end"], -(date.fromisoformat(x["end"]) - date.fromisoformat(x.get("start") or x["end"])).days * 0, x.get("filed", "")))[-1]
            return dict(x, tag=tg)
    return None


def _nonaccrual(url):
    """10-Q 표에서 Non-accrual 비율 (원가·공정가치). 첫 숫자 = 이번 분기, 두 번째 = 비교 시점"""
    h = _get(url)
    cost = fv = None
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S | re.I):
        cells = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr.group(1), re.S | re.I)]
        cells = [c for c in cells if c and c not in ("$", "%", ")", "(")]
        if not cells or not re.search(r"non-?accrual", cells[0], re.I):
            continue
        nums = [_num(c) for c in cells[1:]]
        pct = [n for c, n in zip(cells[1:], nums) if n is not None and n <= 100 and ("." in c or "%" in c)]
        lab = cells[0].lower()
        if "amortized cost" in lab or "at cost" in lab:
            cost = cost or (pct[:2] if pct else None)
        elif "fair value" in lab:
            fv = fv or (pct[:2] if pct else None)
        elif len(nums) >= 4 and nums[1] is not None and nums[3] is not None and nums[1] <= 100 and nums[3] <= 100:
            cost, fv = cost or [nums[1]], fv or [nums[3]]          # [원가 금액, 원가 %, 공정가치 금액, 공정가치 %] 형식
        if cost and fv:
            break
    if not (cost or fv):                                            # 표가 없으면 문장 ("1% were on non-accrual status")
        t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h)))
        m = re.search(r"(\d+(?:\.\d+)?)\s?% (?:were|was) on non-?accrual status", t, re.I)
        if m:
            fv = [float(m.group(1))]
    return {"cost": cost, "fv": fv}


def one(name, cik, desc):
    subs = _get(f"https://data.sec.gov/submissions/CIK{cik}.json", True)
    r = subs["filings"]["recent"]
    k = next(i for i, f in enumerate(r["form"]) if f in ("10-Q", "10-K"))
    accn, doc = r["accessionNumber"][k], r["primaryDocument"][k]
    p = CACHE / f"bdc_{accn}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{doc}"
    g = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", True)["facts"].get("us-gaap", {})
    nav = _fact(g, ["AssetsNet", "StockholdersEquity"], instant=True)
    debt = _fact(g, DEBT_TAGS, instant=True)
    pik = _fact(g, PIK_TAGS)
    inc = _fact(g, INC_TAGS, pair=(pik["start"], pik["end"])) if pik else None
    fresh_pik = pik and pik["end"] >= r["reportDate"][k][:4] + "-01-01"              # 몇 년 전에 태그를 끊은 경우 제외
    room = _fact(g, ["LineOfCreditFacilityRemainingBorrowingCapacity"], instant=True)
    na = _nonaccrual(url)
    out = {"name": name, "cik": cik, "desc": desc, "form": r["form"][k], "period": r["reportDate"][k], "filed": r["filingDate"][k], "url": url,
           "nav": nav and nav["val"], "debt": debt and debt["val"], "debt_tag": debt and debt["tag"],
           "lev": (debt["val"] / nav["val"]) if nav and debt and nav["val"] else None,
           "pik": (pik["val"] / inc["val"]) if fresh_pik and inc and inc["val"] else None,
           "pik_period": f"{pik['start']}~{pik['end']}" if fresh_pik and inc else None,
           "room": room and room["val"], "room_date": room and room["end"],
           "na_cost": na["cost"], "na_fv": na["fv"],
           "tender": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=SC+TO&dateb=&owner=include&count=20" if not name.isupper() or name == "BCRED" else None}
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def monitor():
    rows, errs = [], []
    for name, tk, cik, desc in UNIVERSE:
        try:
            rows.append(one(name, cik, desc))
        except Exception as e:
            errs.append(f"{name}: {str(e)[:80]}")
    v = lambda k: [r[k] for r in rows if r.get(k) is not None]
    fvs = [r["na_fv"][0] for r in rows if r.get("na_fv")]
    rise = [r["name"] for r in rows if r.get("na_fv") and len(r["na_fv"]) > 1 and r["na_fv"][0] > r["na_fv"][1] + 0.3]
    med = lambda a: sorted(a)[len(a) // 2] if a else None
    s = {"lev": med(v("lev")), "pik": med(v("pik")), "na_fv": med(fvs), "rise": rise}
    lv = "bad" if (s["na_fv"] or 0) >= 3 or (s["pik"] or 0) >= 0.12 else "warn" if (s["na_fv"] or 0) >= 1.5 or (s["pik"] or 0) >= 0.08 or len(rise) >= 2 else "ok"
    asof = max((r["period"] for r in rows), default=None)
    return {"rows": rows, "summary": s, "lv": lv, "asof": asof, "errors": errs,
            "src": "SEC EDGAR — 각 BDC 최신 10-Q/10-K 원문 표 · XBRL (분기 공시, 새 공시가 나오면 자동 재계산)",
            "note": "BDC = 기업에 직접 대출하는 미국 상장·비상장 펀드. 펀드가 빌린 돈은 '펀드의 빚'이며 대출받은 기업의 빚과 더하지 않아요."}


if __name__ == "__main__":
    d = monitor()
    print(d["lv"], d["summary"], d["errors"])
    for r in d["rows"]:
        print(f"  {r['name']:6} {r['period']} 빚/순자산 {r['lev'] and round(r['lev'], 2)}  PIK {r['pik'] and round(r['pik'] * 100, 1)}%  Non-accrual 원가 {r['na_cost']} 공정가치 {r['na_fv']}  남은 한도 {r['room'] and round(r['room'] / 1e9, 1)}B")
