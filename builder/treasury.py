"""
미국 재무부 국채 위기 모니터 — US_Treasury_Monitor_Dashboard.html 의 기능을 이 사이트 구조로 다시 구현
(브라우저 우회 프록시·FRED 키 없이 서버가 직접 수집하고, 모든 판정을 서버에서 한 번에 계산)

  국채 입찰 결과·예정      미 재무부 Fiscal Data  auctions_query · upcoming_auctions
  국채 구성(Bills 비중)    미 재무부 MSPD mspd_table_1
  TGA                      미 재무부 DTS operating_cash_balance
  ON RRP · SRF             NY 연준 Markets API
  금리 · 신용 · 레포 · SOMA · 대출 · 물가 · 고용 · 이자     FRED (공식 API — FRED_API_KEY, 없으면 fredgraph CSV)
  MOVE · ETF · 금 · S&P    Yahoo Finance
  일본 국채 금리           일본 재무성 jgbcme_all.csv / jgbcme.csv
  일본 해외채권 주간 플로우 일본 재무성 week.csv (Shift-JIS)
  FOMC · BOJ 회의 일정     연준·일본은행 공식 일정 페이지

원본 대비 바로잡은 것: 월간 C&I 대출(BUSLOANS)을 13개월 전과 비교 · Bills 가격 계산에서 주→일 변환 ·
금리 CSV 열 번호 대신 FRED · Yahoo '전일'은 실제 직전 종가 · 일본 CSV는 csv 모듈로 파싱 ·
고정 일정(2026년 4월)·고정 이자 수치 대신 실시간 자료 · 시장 긴장도에 MOVE·HY 실제 반영
"""
import csv
import io
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests

import absorb
import markets
import sources

UA = {"User-Agent": "MangoResearch/1.0 (personal research)"}
FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
FU = markets.fred_url
_LOCK = threading.Lock()
_MEM = {}


def _num(x):
    try:
        return None if x in (None, "", "null") else float(x)
    except (TypeError, ValueError):
        return None


def _fr(sid, days=400):
    return markets.fred(sid, (date.today() - timedelta(days=days)).isoformat())


def _last(rows):
    return rows[-1][1] if rows else None


def _ago_n(rows, n):
    """n 관측치 전 값"""
    return rows[-1 - n][1] if rows and len(rows) > n else None


def _ago_d(rows, days):
    if not rows:
        return None
    cut = (date.fromisoformat(rows[-1][0]) - timedelta(days=days)).isoformat()
    p = [r for r in rows if r[0] <= cut]
    return p[-1][1] if p else None


def _yahoo(sym, rng="3mo"):
    c = markets.yahoo_chart(sym, rng, "1d")
    off = c.get("gmtoffset") or 0
    rows = [[datetime.utcfromtimestamp(t + off).date().isoformat(), v] for t, v in c["points"] if v is not None]
    return rows


def _link(label, url):
    return {"label": label, "url": url}


# ══ 원자료 수집 ══════════════════════════════════════════════════
def _auctions_raw():
    def load():
        r = requests.get(FD + "/v1/accounting/od/auctions_query", headers=UA, timeout=40,
                         params={"sort": "-auction_date", "page[size]": "400",
                                 "filter": f"auction_date:gte:{(date.today() - timedelta(days=200)).isoformat()}"})
        r.raise_for_status()
        return r.json()["data"]
    return _merge_td(sources._cached("ust_auctions_full.json", 3 * 3600, load))


def _td_raw():
    """TreasuryDirect 입찰 결과 (발표 당일 반영) — Fiscal Data는 결과 칸을 며칠 늦게 채워서 최근 입찰이 빠지는 문제 보완"""
    def load():
        r = requests.get("https://www.treasurydirect.gov/TA_WS/securities/auctioned", params={"format": "json", "days": "45"}, headers=UA, timeout=40)
        r.raise_for_status()
        return r.json()
    return sources._cached("ust_td_auctioned.json", 3600, load)


def _td_to_fd(t):
    """TreasuryDirect 필드 → Fiscal Data(auctions_query) 필드 이름으로 바꿔 같은 판독 코드를 그대로 쓴다"""
    g = lambda k: t.get(k) if t.get(k) not in ("", None) else None
    d10 = lambda k: (g(k) or "")[:10] or None
    num = lambda k: _num(g(k)) or 0
    fima_a, sub_nc = num("fimaNoncompetitiveParAwarded"), num("subtotalNoncompetitiveParAwardedInsideOfOfferingAmount")
    comp_a = num("subtotalCompetitiveParAwardedInsideOfOfferingAmount") + num("subtotalCompetitiveParAwardedOutsideOfOfferingAmount")
    comp_t = num("subtotalCompetitiveParRecognizedInsideOfOfferingAmount") + num("subtotalCompetitiveParRecognizedOutsideOfOfferingAmount")
    typ = g("type") or g("securityType")
    return {"auction_date": d10("competitiveAuctionCloseDate") or d10("auctionDate"), "security_type": g("securityType"), "security_term": g("securityTerm"),
            "cusip": g("cusip"), "reopening": g("reopening"), "original_security_term": g("originalSecurityTerm"),
            "issue_date": d10("issueDate"), "maturity_date": d10("maturityDate"), "announcemt_date": d10("announcementDate"),
            "inflation_index_security": "Yes" if typ == "TIPS" else "No", "floating_rate": "Yes" if typ == "FRN" else (g("floatingRate") or "No"),
            "bid_to_cover_ratio": g("bidToCoverRatio"), "high_yield": g("highYield"), "high_discnt_rate": g("highRate"), "high_investment_rate": g("investmentRate"),
            "avg_med_yield": g("medianYield"), "avg_med_discnt_rate": g("medianRate"), "low_yield": g("lowYield"), "low_discnt_rate": g("lowRate"),
            "allocation_pctage": g("allottedAtHighYieldPercentage") or g("allottedAtHighRatePercentage") or g("allottedAtHighDiscountMarginPercentage"),
            "price_per100": g("highPrice"), "int_rate": g("interestRate"), "offering_amt": g("offeringAmount"),
            "total_accepted": g("grandTotalParAwarded"), "total_tendered": g("grandTotalParRecognized"),
            "comp_accepted": comp_a or None, "comp_tendered": comp_t or None, "noncomp_accepted": (sub_nc - fima_a) if sub_nc else None,
            "fima_noncomp_accepted": g("fimaNoncompetitiveParAwarded"), "fima_noncomp_tendered": g("fimaNoncompetitiveParRecognized"),
            "soma_accepted": g("somaNoncompetitiveParAwarded"), "soma_tendered": g("somaNoncompetitiveParRecognized"),
            "primary_dealer_accepted": g("primaryDealersCompetitiveParAwarded"), "primary_dealer_tendered": g("primaryDealersCompetitiveParRecognized"),
            "direct_bidder_accepted": g("directBiddersCompetitiveParAwarded"), "direct_bidder_tendered": g("directBiddersCompetitiveParRecognized"),
            "indirect_bidder_accepted": g("indirectBiddersCompetitiveParAwarded"), "indirect_bidder_tendered": g("indirectBiddersCompetitiveParRecognized"),
            "treas_retail_accepted": g("retailNoncompetitiveParAwarded"), "pdf_filenm_comp_results": g("treasuryAuctionResultsPressReleaseFileName"),
            "cash_management_bill_cmb": g("cashManagementBill"), "src_td": True}


def _merge_td(fd_rows):
    """Fiscal Data 행 중 결과(응찰배율)가 비어 있거나 아예 없는 최근 입찰을 TreasuryDirect 결과로 채움"""
    try:
        td = [_td_to_fd(t) for t in (_td_raw() or [])]
    except Exception as e:
        print(f"[td] TreasuryDirect 실패: {str(e)[:80]}")
        return fd_rows
    td = {(x["cusip"], x["auction_date"]): x for x in td if x.get("cusip") and x.get("auction_date") and _num(x.get("bid_to_cover_ratio"))}
    out, seen = [], set()
    for x in fd_rows or []:
        k = (x.get("cusip"), x.get("auction_date"))
        seen.add(k)
        out.append(td[k] if not _num(x.get("bid_to_cover_ratio")) and k in td else x)
    out += [x for k, x in td.items() if k not in seen]
    return sorted(out, key=lambda x: x.get("auction_date") or "", reverse=True)


def _upcoming_raw():
    def load():
        r = requests.get(FD + "/v1/accounting/od/upcoming_auctions", headers=UA, timeout=40, params={"sort": "-record_date", "page[size]": "60"})
        r.raise_for_status()
        return r.json()["data"]
    return sources._cached("ust_upcoming.json", 3 * 3600, load)


def _mspd_latest():
    def load():
        r = requests.get(FD + "/v1/debt/mspd/mspd_table_1", headers=UA, timeout=40,
                         params={"sort": "-record_date", "page[size]": "40", "fields": "record_date,security_type_desc,security_class_desc,total_mil_amt"})
        r.raise_for_status()
        return r.json()["data"]
    return sources._cached("ust_mspd.json", 12 * 3600, load)


def _tga_raw():
    def load():
        r = requests.get(FD + "/v1/accounting/dts/operating_cash_balance", headers=UA, timeout=40,
                         params={"sort": "-record_date", "page[size]": "1500", "fields": "record_date,account_type,open_today_bal,close_today_bal",
                                 "filter": f"record_date:gte:{(date.today() - timedelta(days=400)).isoformat()}"})
        r.raise_for_status()
        out = {}
        for x in r.json()["data"]:
            at = x.get("account_type") or ""
            if "Closing Balance" in at and "TGA" in at:
                v = _num(x.get("open_today_bal")) or _num(x.get("close_today_bal"))   # 2021년 이후 '마감 잔액'이 open_today_bal 칸에 들어 있음
                if v:
                    out[x["record_date"]] = v / 1000
        return sorted([d, v] for d, v in out.items())
    return sources._cached("ust_tga.json", 3 * 3600, load)


def _rrp_raw():
    def load():
        s = (date.today() - timedelta(days=400)).isoformat()
        r = requests.get(f"https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate={s}&endDate={date.today().isoformat()}", headers=UA, timeout=40)
        r.raise_for_status()
        ops = r.json()["repo"]["operations"]
        by = {}
        for o in ops:
            by[o["operationDate"]] = by.get(o["operationDate"], 0) + (o.get("totalAmtAccepted") or 0) / 1e9
        return sorted([d, round(v, 3)] for d, v in by.items())
    try:
        return sources._cached("ust_rrp.json", 3 * 3600, load), "NY 연준"
    except Exception:
        return _fr("RRPONTSYD", 400), "FRED RRPONTSYD"


def _srf_raw():
    def load():
        r = requests.get("https://markets.newyorkfed.org/api/rp/repo/all/results/last/30.json", headers=UA, timeout=40)
        r.raise_for_status()
        by = {}
        for o in r.json()["repo"]["operations"]:
            by[o["operationDate"]] = by.get(o["operationDate"], 0) + (o.get("totalAmtAccepted") or 0) / 1e9
        return sorted([d, round(v, 3)] for d, v in by.items())
    return sources._cached("ust_srf.json", 3 * 3600, load)


def _jgb_curve():
    """일본 국채 2·5·10·30년 (전체 기록 + 이번 달)"""
    def parse(txt):
        rows = list(csv.reader(io.StringIO(txt)))
        hdr = next(i for i, x in enumerate(rows) if x and x[0] == "Date")
        H = rows[hdr]
        idx = {k: H.index(k) for k in ("2Y", "5Y", "10Y", "30Y") if k in H}
        out = []
        for x in rows[hdr + 1:]:
            try:
                d = datetime.strptime(x[0], "%Y/%m/%d").date().isoformat()
            except (ValueError, IndexError):
                continue
            out.append([d] + [_num(x[idx[k]]) if idx.get(k) is not None and idx[k] < len(x) and x[idx[k]] not in ("-", "") else None for k in ("2Y", "5Y", "10Y", "30Y")])
        return out

    def load_all():
        r = requests.get("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv", headers=UA, timeout=40)
        r.raise_for_status()
        cut = (date.today() - timedelta(days=500)).isoformat()
        return [x for x in parse(r.content.decode("utf-8", "replace")) if x[0] >= cut]
    hist = sources._cached("ust_jgb_all.json", 24 * 3600, load_all)
    try:
        def load_cur():
            r = requests.get("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv", headers=UA, timeout=40)
            r.raise_for_status()
            return parse(r.content.decode("utf-8", "replace"))
        cur = sources._cached("ust_jgb_cur.json", 3 * 3600, load_cur)
        seen = {x[0] for x in hist}
        hist = hist + [x for x in cur if x[0] not in seen]
    except Exception:
        pass
    return sorted(hist)


def _japan_flow():
    """일본 거주자의 해외 중장기채 순매수 (억엔, 주간) — 미국 국채의 '숨은 지원군'"""
    def load():
        r = requests.get("https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv", headers=UA, timeout=40)
        r.raise_for_status()
        out = []
        for x in csv.reader(io.StringIO(r.content.decode("shift_jis", "replace"))):
            if not x or not re.match(r"\s*\d{4}", x[0] or ""):
                continue
            p = x[0].replace("．", ".").replace(" ", "").replace("　", "")
            def n(s):
                s = (s or "").replace(",", "").replace(" ", "").replace("△", "-")
                try:
                    return float(s)
                except ValueError:
                    return None
            if len(x) >= 12:
                out.append({"period": p, "long": n(x[6]), "total": n(x[11])})
        return out[-60:]
    return sources._cached("ust_japan_flow.json", 12 * 3600, load)


def _fomc_dates():
    def load():
        t = requests.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", headers=UA, timeout=40).text
        out = []
        for m in re.finditer(r"(\d{4}) FOMC Meetings", t):
            y = int(m.group(1))
            end = t.find("FOMC Meetings", m.end())
            blk = t[m.end(): end if end > 0 else m.end() + 30000]
            for mon, dd in re.findall(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<', blk, re.S):
                mon = mon.split("/")[-1].strip()
                try:
                    mi = datetime.strptime(mon[:3], "%b").month
                except ValueError:
                    continue
                days = re.findall(r"\d+", dd)
                if not days:
                    continue
                d1 = int(days[-1])
                mi2 = mi if len(days) < 2 or int(days[-1]) >= int(days[0]) else mi % 12 + 1
                try:
                    out.append({"date": date(y, mi2, d1).isoformat(), "sep": "*" in dd})
                except ValueError:
                    pass
        return sorted({x["date"]: x for x in out}.values(), key=lambda x: x["date"])
    return sources._cached("ust_fomc.json", 7 * 24 * 3600, load)


def _boj_dates():
    def load():
        t = requests.get("https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm", headers=UA, timeout=40).text
        out = []
        for tb in re.findall(r"<table.*?</table>", t, re.S):
            cap = re.search(r"(\d{4})", re.sub(r"<[^>]+>", " ", tb[:600]))
            ym = re.search(r"Table\s*:\s*(\d{4})", re.sub(r"<[^>]+>", " ", tb))
            y = int((ym or cap).group(1)) if (ym or cap) else None
            for tr in re.findall(r"<tr.*?</tr>", tb, re.S):
                cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
                if not cells or not y:
                    continue
                m = re.match(r"([A-Z][a-z]+)\.?\s+(\d+)\s*\([^)]*\)(?:,\s*(\d+))?", cells[0])
                if not m:
                    continue
                try:
                    mi = datetime.strptime(m.group(1)[:3], "%b").month
                    out.append({"date": date(y, mi, int(m.group(3) or m.group(2))).isoformat(), "outlook": len(cells) > 1 and cells[1] not in ("-", "")})
                except ValueError:
                    pass
        return sorted({x["date"]: x for x in out}.values(), key=lambda x: x["date"])
    return sources._cached("ust_boj.json", 7 * 24 * 3600, load)


FRED_SET = {**absorb.FRED_NEED, 
    "DGS10": 500, "DGS30": 120, "DGS2": 120, "DFII10": 120, "T10YIE": 120, "SOFR": 120, "IORB": 120, "SOFR25": 120, "SOFR75": 120,
    "VIXCLS": 400, "BAMLH0A0HYM2": 400, "BAMLC0A0CM": 200, "BAMLH0A3HYC": 200, "WSHOBL": 120, "TREAST": 120, "WRESBAL": 400, "WALCL": 120,
    "DEXUSEU": 60, "DEXJPUS": 120, "DFEDTARU": 400, "DFEDTARL": 400, "PCEPILFE": 500, "A191RL1Q225SBEA": 800,
    "CPIAUCSL": 500, "CPILFESL": 500, "CPIENGSL": 500, "CUSR0000SAH1": 500, "CUSR0000SAS": 500,
    "PAYEMS": 500, "UNRATE": 500, "CES0500000003": 500, "CIVPART": 500,
    "DRTSCILM": 1200, "SUBLPDMOSXWBNQ": 1200, "BUSLOANS": 900,
    "A091RC1Q027SBEA": 1200, "W018RC1Q027SBEA": 1200, "GFDEBTN": 1200, "GDP": 800,
}
YH_SET = ["^MOVE", "HYG", "JNK", "LQD", "TLT", "GC=F", "^GSPC"]


def _collect():
    F, Y, X, errs = {}, {}, {}, []
    jobs = {("F", k): (lambda k=k, d=d: _fr(k, d)) for k, d in FRED_SET.items()}
    jobs.update({("Y", s): (lambda s=s: _yahoo(s)) for s in YH_SET})
    jobs.update({("X", k): f for k, f in {"auctions": _auctions_raw, "upcoming": _upcoming_raw, "mspd": _mspd_latest, "tga": _tga_raw, "rrp": _rrp_raw,
                                         "srf": _srf_raw, "jgb": _jgb_curve, "jflow": _japan_flow, "fomc": _fomc_dates, "boj": _boj_dates}.items()})

    def run(item):
        k, f = item
        try:
            return k, f(), None
        except Exception as e:
            return k, None, f"{k[1]}: {str(e)[:80]}"
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (kind, key), val, err in ex.map(run, jobs.items()):
            if err:
                errs.append(err)
            {"F": F, "Y": Y, "X": X}[kind][key] = val if val is not None else ([] if kind != "X" else None)
    return F, Y, X, errs


# ══ 판정 ══════════════════════════════════════════════════════════
TERM_KR = {"Bill": "단기채(Bill)", "Note": "중기채(Note)", "Bond": "장기채(Bond)", "TIPS": "물가연동(TIPS)", "FRN": "변동금리(FRN)"}


def _term_days(term):
    m = re.match(r"(\d+)-(Week|Day|Month|Year)", term or "")
    if not m:
        return None
    n = int(m.group(1))
    return n * {"Week": 7, "Day": 1, "Month": 30, "Year": 365}[m.group(2)]


def _grade(btc, dealer):
    if not btc:
        return None
    return "A" if btc >= 2.5 and dealer < 18 else "B" if btc >= 2.2 and dealer < 22 else "C" if btc >= 2.0 and dealer < 28 else "D"


def _days_between(a, b):
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


def _official_term(x, typ):
    """재무부 보도자료 표기: 단기채는 '56-Day Bill', 나머지는 '9-Year 10-Month Note' (재개행은 원래 만기 병기)"""
    if typ == "Bill":
        d = re.match(r"(\d+)-Day", x.get("security_term_day_month") or "")
        n = int(d.group(1)) if d else _days_between(x.get("issue_date"), x.get("maturity_date"))
        return f"{n}-Day Bill" + (" (CMB)" if x.get("cash_management_bill_cmb") == "Yes" else "")
    kind = {"TIPS": "TIPS", "FRN": "FRN"}.get(typ, typ)
    return f"{x.get('security_term')} {kind}"


def auctions_view(raw):
    out = []
    for x in raw or []:
        btc = _num(x.get("bid_to_cover_ratio"))
        hy = _num(x.get("high_yield")) or _num(x.get("high_investment_rate"))
        if not btc or hy is None:
            continue
        ta = _num(x.get("total_accepted")) or 0
        st = x.get("security_type") or ""
        typ = "TIPS" if x.get("inflation_index_security") == "Yes" else "FRN" if x.get("floating_rate") == "Yes" else st
        pct = lambda k: (_num(x.get(k)) or 0) / ta * 100 if ta else None
        d, ind, di = pct("primary_dealer_accepted"), pct("indirect_bidder_accepted"), pct("direct_bidder_accepted")
        td = _term_days(x.get("security_term"))
        ir = _num(x.get("high_investment_rate"))
        price = _num(x.get("price_per100")) or (round(100 - _num(x.get("high_discnt_rate")) * td / 360, 6) if st == "Bill" and _num(x.get("high_discnt_rate")) and td else None)
        out.append({
            "date": x["auction_date"], "type": typ, "type_kr": TERM_KR.get(typ, typ), "term": x.get("security_term"), "cusip": x.get("cusip"),
            "reopening": x.get("reopening") == "Yes", "orig_term": x.get("original_security_term"),
            "btc": btc, "high": hy, "coupon": _num(x.get("int_rate")), "inv_rate": ir, "median": _num(x.get("avg_med_yield")) or _num(x.get("avg_med_investment_rate")) or _num(x.get("avg_med_discnt_rate")),
            "low": _num(x.get("low_yield")) or _num(x.get("low_investment_rate")) or _num(x.get("low_discnt_rate")), "discount": _num(x.get("high_discnt_rate")),
            "alloc_high": _num(x.get("allocation_pctage")), "price": price,
            "dealer": d, "indirect": ind, "direct": di, "grade": _grade(btc, d or 0),
            "offering": _num(x.get("offering_amt")), "accepted": ta, "tendered": _num(x.get("total_tendered")),
            "comp_t": _num(x.get("comp_tendered")), "comp_a": _num(x.get("comp_accepted")), "nc_t": _num(x.get("noncomp_tendered")) or _num(x.get("noncomp_accepted")), "nc_a": _num(x.get("noncomp_accepted")),
            "fima_t": _num(x.get("fima_noncomp_tendered")), "fima_a": _num(x.get("fima_noncomp_accepted")), "soma_t": _num(x.get("soma_tendered")), "soma_a": _num(x.get("soma_accepted")),
            "pd_t": _num(x.get("primary_dealer_tendered")), "pd_a": _num(x.get("primary_dealer_accepted")), "dir_t": _num(x.get("direct_bidder_tendered")), "dir_a": _num(x.get("direct_bidder_accepted")),
            "ind_t": _num(x.get("indirect_bidder_tendered")), "ind_a": _num(x.get("indirect_bidder_accepted")),
            "issue": x.get("issue_date"), "maturity": x.get("maturity_date"), "term_days": td,
            "pdf": f"https://www.treasurydirect.gov/instit/annceresult/press/preanre/{x['auction_date'][:4]}/{x['pdf_filenm_comp_results']}" if x.get("pdf_filenm_comp_results") else None,
            # ── 재무부 보도자료(Treasury News) 원문 양식용 ──
            "label": _official_term(x, typ), "days": _days_between(x.get("issue_date"), x.get("maturity_date")),
            "disc_high": _num(x.get("high_discnt_rate")), "disc_med": _num(x.get("avg_med_discnt_rate")), "disc_low": _num(x.get("low_discnt_rate")),
            "y_high": _num(x.get("high_yield")), "y_med": _num(x.get("avg_med_yield")), "y_low": _num(x.get("low_yield")),
            "retail": _num(x.get("treas_retail_accepted")), "announce": x.get("announcemt_date"),
            "sub_t": sum(_num(x.get(k)) or 0 for k in ("comp_tendered", "noncomp_accepted", "fima_noncomp_tendered")),
            "sub_a": sum(_num(x.get(k)) or 0 for k in ("comp_accepted", "noncomp_accepted", "fima_noncomp_accepted")),
        })
    # 직전 같은 종류·같은 만기와 비교 (재개행은 원래 만기 기준)
    for i, a in enumerate(out):
        key = lambda b: (b["type"], b["term"] if b["type"] == "Bill" else (b["orig_term"] or b["term"]))
        p = next((b for b in out[i + 1:] if key(b) == key(a)), None)
        a["prev"] = {kk: p.get(kk) for kk in ("date", "term", "label", "days", "btc", "high", "inv_rate", "disc_high", "y_high", "indirect", "direct", "dealer", "ind_a", "comp_a", "pd_a", "dir_a")} if p else None
    return out


def _news_comment(a):
    """경매 결과 자동 해설 (원본 generateNewsCommentary 규칙)"""
    s, p = [], a.get("prev")
    s.append(f"{a['date']} 실시된 {a['type_kr']} {a['term']} 입찰은 {a['accepted'] / 1e9:,.1f}B 달러 규모로 {'투자수익률' if a['type'] == 'Bill' else '낙찰금리'} {a['high']:.3f}%, 응찰배율 {a['btc']:.2f}배를 기록했어요.")
    if p:
        hc, bc = a["high"] - p["high"], a["btc"] - p["btc"]
        s.append(f"직전 같은 만기 입찰({p['date']})보다 {'투자수익률' if a['type'] == 'Bill' else '낙찰금리'}는 {hc * 100:+.1f}bp" + (" 올라 정부의 차입 부담이 커졌고" if hc > 0.1 else " 내려 차입 부담이 줄었고" if hc < -0.1 else " 비슷했고")
                 + f", 응찰배율은 {bc:+.2f}" + (" 낮아져 수요 경쟁이 약해졌어요." if bc < -0.3 else " 높아져 수요 경쟁이 강해졌어요." if bc > 0.3 else "로 큰 차이가 없어요."))
    ind = a.get("indirect") or 0
    s.append(f"Primary Dealer를 통한 국내외 고객 주문인 Indirect Bidder 비중은 {ind:.1f}%로 " + ("매우 높아 최종 투자자 수요가 탄탄해요." if ind >= 65 else "양호한 편이에요." if ind >= 55 else "평균 수준이에요." if ind >= 45 else "낮아 최종 투자자 수요가 약해 보여요."))
    dl = a.get("dealer") or 0
    if a["type"] == "Bill":
        s.append(f"Primary Dealer가 받아 간 비중은 {dl:.1f}%예요 — 단기채는 원래 Primary Dealer 비중이 30~45%로 높은 시장이라 " + ("평소보다 많이 떠안았어요." if dl > 50 else "평소 범위예요."))
    else:
        s.append(f"Primary Dealer가 떠안은 비중은 {dl:.1f}%로 " + ("높아 '강제 매수(Forced Buying)'에 가까워요 — 시장 수요가 부족했다는 뜻이에요." if dl > 28 else "다소 높은 편이에요." if dl > 22 else "보통 수준이에요." if dl > 15 else "매우 낮아 시장 수요가 건강해요."))
    if a["type"] == "Bill":
        s.append("단기채는 MMF 자금이 받쳐 주는 시장이라 보통 안정적이에요 — 응찰배율이 2.5배를 밑돌거나 Primary Dealer 비중이 25%를 넘기 시작하면 단기 자금시장 긴장을 의심해요.")
    elif (a.get("term_days") or 0) >= 3600 * 2 or "30" in (a["orig_term"] or a["term"] or ""):
        s.append("장기채는 '가장 먼 미래'를 사는 입찰이라 재정 불안을 가장 먼저 반영해요 — 응찰배율 2.3배 미만이나 Indirect Bidder 비중 55% 미만이 이어지면 장기금리 상승 압력이 커져요.")
    else:
        s.append("중기채는 기간 프리미엄(오래 빌려주는 대가)의 온도계예요 — 결과가 약하면 10년물 금리가 따라 오를 수 있어요.")
    s.append("종합하면 " + ("수요가 매우 강한 입찰이었어요." if a["btc"] >= 2.5 and dl < 18 else "무난한 입찰이었어요." if a["btc"] >= 2.2 else "다소 아쉬운 입찰이었어요." if a["btc"] >= 2.0 else "수요가 부족한 입찰이었어요 — 다음 입찰을 꼭 확인하세요."))
    return " ".join(s)


def build_state():
    F, Y, X, errs = _collect()
    today = date.today().isoformat()
    S = {"errors": errs, "fetched_at": datetime.now().isoformat(timespec="minutes")}
    L = lambda k: _last(F.get(k))

    # ── 1. 입찰 ───────────────────────────────────────────
    AU = auctions_view(X.get("auctions"))
    for a in AU[:30]:
        a["comment"] = _news_comment(a)
    recent = AU[:20]
    avg = lambda k: (sum(a[k] for a in recent if a.get(k) is not None) / max(1, len([a for a in recent if a.get(k) is not None]))) if recent else None
    coup = [a for a in AU if a["type"] in ("Note", "Bond")][:12]
    S["auctions"] = {"rows": AU[:30], "avg_btc": avg("btc"), "avg_dealer": avg("dealer"), "avg_indirect": avg("indirect"), "avg_direct": avg("direct"),
                     "coupon_avg_btc": sum(a["btc"] for a in coup) / len(coup) if coup else None,
                     "coupon_avg_dealer": sum(a["dealer"] or 0 for a in coup) / len(coup) if coup else None,
                     "n_d": len([a for a in recent if a["grade"] == "D" and a["type"] in ("Note", "Bond")]),
                     "src": [_link("미 재무부 Fiscal Data — 입찰 결과", "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/"),
                             _link("TreasuryDirect 입찰 결과", "https://www.treasurydirect.gov/auctions/auction-query/")]}
    upc = {}
    for x in [r for r in (X.get("auctions") or []) if _num(r.get("bid_to_cover_ratio")) is None] + (X.get("upcoming") or []):
        if (x.get("auction_date") or "") >= today:
            ty = "TIPS" if x.get("inflation_index_security") == "Yes" else "FRN" if x.get("floating_rate") == "Yes" else x["security_type"]
            k = x.get("cusip") or (x["auction_date"], x["security_type"], x["security_term"])
            if k not in upc:
                upc[k] = {"date": x["auction_date"], "type": ty, "term": x["security_term"], "offering": _num(x.get("offering_amt"))}
    S["upcoming"] = sorted(upc.values(), key=lambda r: r["date"])

    # ── 2. 국채 구성 · Bills 비중 ─────────────────────────────
    ms = X.get("mspd") or []
    if ms:
        d0 = max(r["record_date"] for r in ms)
        cur = [r for r in ms if r["record_date"] == d0]
        tot = next((_num(r["total_mil_amt"]) for r in cur if r["security_type_desc"] == "Total Marketable"), None)
        comp = {}
        for r in cur:
            if r["security_type_desc"] != "Marketable":
                continue
            c = r["security_class_desc"].lower()
            k = "bills" if c == "bills" else "notes" if c == "notes" else "bonds" if c == "bonds" else "tips" if "inflation" in c else "frn" if "floating" in c else None
            if k:
                comp[k] = _num(r["total_mil_amt"])
        tot = tot or sum(comp.values())
        pub = next((_num(r["total_mil_amt"]) for r in cur if r["security_type_desc"] == "Total Public Debt Outstanding"), None)
        share = comp.get("bills", 0) / tot * 100 if tot else None
        try:
            import plumbing
            bh = plumbing.bills().get("rows") or []
        except Exception:
            bh = []
        S["debt"] = {"date": d0, "total_marketable": tot * 1e6 if tot else None, "public_total": pub * 1e6 if pub else None,
                     "comp": {k: v / tot * 100 for k, v in comp.items()} if tot else {}, "amt": {k: v * 1e6 for k, v in comp.items()},
                     "bills_share": share, "bills_hist": bh,
                     "tbac": "범위 초과 (위험)" if share and share > 22 else "약간 초과 (경계)" if share and share > 20 else "정상 범위" if share and share >= 15 else "범위 미달",
                     "tbac_st": "bad" if share and share > 22 else "warn" if share and share > 20 else "ok",
                     "src": [_link("미 재무부 MSPD (월간 국채 잔액)", "https://fiscaldata.treasury.gov/datasets/monthly-statement-public-debt/")]}
    else:
        S["debt"] = None

    # ── 3. 유동성: ON RRP · TGA · 지준 · SRF ───────────────────
    rrp, rrp_src = X.get("rrp") or ([], "")
    rv = _last(rrp)
    tga = X.get("tga") or []
    S["liq"] = {"rrp": rrp[-260:], "rrp_now": rv, "rrp_src": rrp_src,
                "rrp_badge": None if rv is None else "거의 소진" if rv < 10 else "위험 수위" if rv < 100 else "저수위" if rv < 300 else "정상",
                "rrp_st": None if rv is None else "bad" if rv < 100 else "warn" if rv < 300 else "ok",
                "tga": tga[-260:], "tga_now": _last(tga), "tga_30": (_last(tga) - (_ago_d(tga, 30) or _last(tga))) if tga else None,
                "res": [[d, v / 1e6] for d, v in (F.get("WRESBAL") or [])], "res_now": (L("WRESBAL") or 0) / 1e6 or None,
                "res_13w": ((L("WRESBAL") or 0) - (_ago_n(F.get("WRESBAL"), 13) or 0)) / 1e3 if F.get("WRESBAL") else None,
                "srf": X.get("srf") or [], "srf_now": _last(X.get("srf") or []),
                "src": [_link("NY 연준 역레포(ON RRP)", "https://www.newyorkfed.org/markets/desk-operations/reverse-repo"), _link("미 재무부 일일 재정 보고서(DTS)", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/"),
                        _link("FRED WRESBAL (은행 지준)", FU("WRESBAL")), _link("NY 연준 상설 레포(SRF)", "https://www.newyorkfed.org/markets/desk-operations/repo")]}
    # 역레포가 이미 바닥(구조적)이면 '완충 장치' 판정은 은행 지준 변화와 SOFR−IORB로 한다
    si0 = (L("SOFR") - L("IORB")) * 100 if L("SOFR") is not None and L("IORB") is not None else None
    r13 = S["liq"]["res_13w"]
    buf = "bad" if (r13 is not None and r13 < -150) or (si0 is not None and si0 >= 5) else "warn" if (r13 is not None and r13 < -50) or (si0 is not None and si0 >= 2) else "ok"
    S["liq"]["buffer_st"] = buf
    if rv is not None and rv < 10:
        S["liq"]["rrp_badge"] = "소진 (구조적) — 지준으로 판단"
        S["liq"]["rrp_st"] = buf
    srf = S["liq"]["srf_now"]
    S["liq"]["srf_st"] = None if srf is None else "bad" if srf >= 10 else "warn" if srf >= 1 else "ok"

    # ── 4. 금리 상승 원인 분해 ─────────────────────────────────
    def chg30(k):
        r = F.get(k) or []
        return ((r[-1][1] - r[-22][1]) * 100) if len(r) > 22 else None
    dn, dr, db = chg30("DGS10"), chg30("DFII10"), chg30("T10YIE")
    # T10YIE = DGS10 − DFII10 이라 '나머지'로 구한 기간프리미엄은 항상 0 → 연준 공식 추정치(Kim-Wright) 30일 변화를 쓴다
    tpr = F.get("THREEFYTP10") or []
    tp30a = _ago_d(tpr, 30) if tpr else None
    tp = (tpr[-1][1] - tp30a) * 100 if tpr and tp30a is not None else None
    sofr_r = F.get("SOFR") or []
    si_now = (L("SOFR") - L("IORB")) * 100 if L("SOFR") is not None and L("IORB") is not None else None
    liq_stress = (len(sofr_r) > 22 and (sofr_r[-1][1] - sofr_r[-22][1]) * 100 > 10) or (si_now is not None and si_now >= 5) or (S["liq"].get("buffer_st") == "bad")
    rc = {"y10": L("DGS10"), "y30": L("DGS30"), "y2": L("DGS2"), "real": L("DFII10"), "bei": L("T10YIE"), "d_nom": dn, "d_real": dr, "d_bei": db, "d_tp": tp, "liq_stress": liq_stress,
          "hist10": (F.get("DGS10") or [])[-260:]}
    if dn is None:
        rc.update(key="na", title="데이터 부족", badge="판정 불가", desc="")
    elif abs(dn) < 10:
        rc.update(key="stable", title="🔵 10Y 금리 안정", badge="안정", desc=f"30일 변화 {dn:+.0f}bp — 의미 있는 움직임이 없어요.")
    else:
        comps = [("real", dr), ("bei", db), ("tp", tp)]
        dom = max(comps, key=lambda c: abs(c[1] or 0))[0]
        if dn > 0:
            if liq_stress and (dom == "tp" or (tp or 0) > 15):
                rc.update(key="crisis", title="🚨 구조적 위기 신호: 기간프리미엄 상승 + 유동성 악화 동시", badge="🚨 위기", desc="금리가 '돈을 오래 빌려주기 무서워서' 오르는데 단기 자금시장까지 빡빡해요 — 2019년 레포 위기와 비슷한 조합이에요.")
            elif dom == "real" and dr > 10:
                rc.update(key="healthy", title="🟢 건강한 상승: 실질금리(성장 기대) 주도", badge="건강", desc="경제가 좋아질 거라는 기대로 오르는 금리예요 — 주식에 꼭 나쁘지 않아요.")
            elif dom == "bei" and db > 10:
                rc.update(key="inflation", title="🟡 인플레 보상 상승", badge="물가 압력", desc="물가가 다시 오를 거라는 걱정이 금리를 올려요 — 연준이 매파적으로 돌아설 수 있어요.")
            elif dom == "tp" and (tp or 0) > 10:
                rc.update(key="supply", title="🟠 재정/수급 압력: 기간프리미엄 상승 주도", badge="수급 압력", desc="국채가 너무 많이 나와서, 오래 빌려주는 대가(기간프리미엄)가 올라요 — 재정 걱정 신호예요.")
            else:
                rc.update(key="mixed", title="⚪ 혼합 상승", badge="혼합", desc="여러 요인이 섞여서 올랐어요.")
        else:
            if dom == "real" and dr < -10:
                rc.update(key="fear", title="🟣 안전자산 선호 (경기 둔화 걱정)", badge="피난", desc="성장 기대가 꺾여 국채로 돈이 피난 오는 중이에요.")
            elif dom == "bei" and db < -10:
                rc.update(key="disinfl", title="🟢 디스인플레 (물가 걱정 완화)", badge="디스인플레", desc="물가 걱정이 줄어서 금리가 내려요 — 위험자산에 우호적이에요.")
            else:
                rc.update(key="drop_mixed", title="⚪ 혼합 하락", badge="하락 혼합", desc="여러 요인이 섞여서 내렸어요.")
    rc["liq_note"] = "유동성 교차확인: " + ("⚠ SOFR 30일 +10bp 이상 또는 역레포 $100B 미만 — 유동성도 빡빡해요" if liq_stress else "단기 자금시장은 안정적이에요")
    rc["src"] = [_link("FRED DGS10", FU("DGS10")), _link("FRED DFII10 (실질금리)", FU("DFII10")), _link("FRED T10YIE (기대인플레)", FU("T10YIE"))]
    S["rates"] = rc

    # ── 5. 레포 심층 ───────────────────────────────────────
    si = (L("SOFR") - L("IORB")) * 100 if L("SOFR") is not None and L("IORB") is not None else None
    s75 = (L("SOFR75") - L("SOFR25")) * 100 if L("SOFR75") is not None and L("SOFR25") is not None else None
    dang = (1 if si is not None and si >= 10 else 0) + (1 if s75 is not None and s75 >= 10 else 0) + (1 if srf is not None and srf >= 10 else 0)
    warn = (1 if si is not None and 5 <= si < 10 else 0) + (1 if s75 is not None and 5 <= s75 < 10 else 0) + (1 if srf is not None and 1 <= srf < 10 else 0)
    S["repo"] = {"sofr": L("SOFR"), "iorb": L("IORB"), "sofr_iorb": si, "spread75": s75, "srf": srf, "danger": dang, "warn": warn,
                 "verdict": "⚠️ 데이터 부족" if si is None and s75 is None else "🚨 Repo 시장 이중 압박 (2019년 9월 패턴)" if dang >= 2 else "🔴 Repo 압박 신호 (분기말 효과인지 추세인지 확인)" if dang == 1 else "🟠 경계 수위" if warn >= 1 else "🟢 Repo 정상",
                 "st": "bad" if dang >= 1 else "warn" if warn else "ok",
                 "pathA": "🔴 활성화" if dang >= 2 else "🟠 조짐" if dang >= 1 or warn >= 2 else "🟢 비활성",
                 "hist": [[d, round((v - dict(F.get("IORB") or []).get(d, v)) * 100, 1)] for d, v in (F.get("SOFR") or [])][-120:],
                 "src": [_link("FRED SOFR", FU("SOFR")), _link("FRED IORB", FU("IORB")), _link("FRED SOFR 25·75 분위", FU("SOFR75")), _link("NY 연준 SRF 결과", "https://www.newyorkfed.org/markets/desk-operations/repo")]}

    # ── 6. 신용 (HY·IG·CCC·ETF) ─────────────────────────────
    bp = lambda k: [[d, v * 100] for d, v in (F.get(k) or [])]
    hy, ig, ccc = bp("BAMLH0A0HYM2"), bp("BAMLC0A0CM"), bp("BAMLH0A3HYC")
    hyv, igv, cccv = _last(hy), _last(ig), _last(ccc)
    wk = lambda r: (r[-1][1] - r[-6][1]) if len(r) > 6 else None
    ratio = hyv / igv if hyv and igv else None
    def ychg(sym):
        r = Y.get(sym) or []
        return (r[-1][1], (r[-1][1] / r[-2][1] - 1) * 100 if len(r) > 1 else None, (r[-1][1] / r[0][1] - 1) * 100 if r else None)
    etf = {s: ychg(s) for s in ("HYG", "JNK", "LQD", "TLT")}
    hg, tl = etf["HYG"][1], etf["TLT"][1]
    flow = "⚠️ 자본 탈출 진행 중 (정크본드 팔고 국채로)" if hg is not None and tl is not None and hg < -0.3 and tl > 0.3 else "✅ 위험자산 선호" if hg is not None and tl is not None and hg > 0 and tl < 0 else "중립"
    stage = None if hyv is None or igv is None else 0 if hyv < 400 and igv < 100 else 1 if hyv < 600 and igv < 130 and (ratio or 0) < 5 else 2 if hyv < 800 and igv < 180 else 3 if hyv < 1000 else 4
    soma_b, soma_t = F.get("WSHOBL") or [], F.get("TREAST") or []
    tot_chg = ((soma_t[-1][1] - soma_t[-6][1]) / 1000) if len(soma_t) > 6 else None
    end1 = len(hy) >= 30 and sum(v for _, v in hy[-10:]) / 10 < sum(v for _, v in hy[-30:-20]) / 10
    end = [end1, (tot_chg or 0) > 0, igv is not None and igv < 200]
    lvl = lambda v, ts: next((n for t, n in ts if v is not None and v >= t), ts[-1][1])
    S["credit"] = {"hy": hyv, "ig": igv, "ccc": cccv, "hy_w": wk(hy), "ig_w": wk(ig), "ccc_w": wk(ccc), "ratio": ratio,
                   "hy_badge": lvl(hyv, [(1000, "위기"), (800, "공포"), (600, "경계"), (400, "중립"), (-1e9, "낙관")]),
                   "ig_badge": lvl(igv, [(300, "위기"), (200, "위험"), (150, "경계"), (100, "중립"), (-1e9, "낙관")]),
                   "ccc_badge": lvl(cccv, [(1500, "부도 임박"), (1000, "경계"), (700, "주시"), (-1e9, "안정")]),
                   "ratio_badge": lvl(ratio, [(7, "위험"), (5, "경계"), (3, "중립"), (-1e9, "안정")]),
                   "etf": {k: {"px": v[0], "d1": v[1], "m1": v[2]} for k, v in etf.items()}, "hyg_tlt": (etf["HYG"][0] / etf["TLT"][0]) if etf["HYG"][0] and etf["TLT"][0] else None,
                   "flow": flow, "stage": stage, "end": end, "end_n": sum(end),
                   "hist_hy": hy[-260:], "hist_ig": ig[-260:],
                   "src": [_link("FRED 하이일드 스프레드", FU("BAMLH0A0HYM2")), _link("FRED 투자등급 스프레드", FU("BAMLC0A0CM")), _link("FRED CCC 스프레드", FU("BAMLH0A3HYC")), _link("Yahoo HYG·TLT", "https://finance.yahoo.com/quote/HYG/")]}

    # ── 7. SOMA (연준 국채 보유) · Bills 집중 매입 ─────────────────
    if len(soma_b) > 6 and len(soma_t) > 6:
        bc = (soma_b[-1][1] - soma_b[-6][1]) / 1000
        tc = (soma_t[-1][1] - soma_t[-6][1]) / 1000
        sh = bc / tc * 100 if tc > 0 else 0
        hist = []
        tdict = dict(soma_t)
        for i in range(max(1, len(soma_b) - 8), len(soma_b)):
            d, v = soma_b[i]
            t = tdict.get(d)
            hist.append({"date": d, "bills": v / 1000, "wchg": (v - soma_b[i - 1][1]) / 1000, "total": t / 1e6 if t else None, "share": v / t * 100 if t else None})
        S["soma"] = {"bills_chg": bc, "total_chg": tc, "share_of_chg": sh, "share_now": soma_b[-1][1] / soma_t[-1][1] * 100,
                     "share_pp": (soma_b[-1][1] / soma_t[-1][1] - soma_b[-6][1] / soma_t[-6][1]) * 100, "hist": hist[::-1],
                     "badge": "🚨 극단적 단기 편중" if sh > 80 else "⚠️ 단기 편중" if sh > 50 else "🟡 일부 단기" if sh > 0 else "✅ 정상 (QT 또는 균형)",
                     "st": "bad" if sh > 80 else "warn" if sh > 50 else "ok",
                     "src": [_link("FRED WSHOBL (연준 보유 T-Bill)", FU("WSHOBL")), _link("FRED TREAST (연준 보유 국채)", FU("TREAST"))]}
    else:
        S["soma"] = None

    # ── 8. 일본: JGB 곡선 · 캐리 압력 · 해외채권 플로우 ────────────
    J = X.get("jgb") or []
    jv = [x for x in J if x[3] is not None]
    j10 = jv[-1][3] if jv else None
    j1m = (jv[-1][3] - jv[-22][3]) * 100 if len(jv) > 22 else None
    spread = (L("DGS10") - j10) * 100 if j10 is not None and L("DGS10") else None
    carry = 0
    if j10 is not None:
        carry += 50 if j10 >= 2.5 else 35 if j10 >= 2.0 else 20 if j10 >= 1.5 else 10 if j10 >= 1.0 else 0
    if j1m is not None:
        carry += 30 if j1m >= 30 else 20 if j1m >= 15 else 10 if j1m >= 5 else 0
    if spread is not None:
        carry += 20 if spread < 100 else 10 if spread < 150 else 0
    carry = min(100, carry)
    jf = X.get("jflow") or []
    jl = [x for x in jf if x.get("long") is not None]
    lastf, prevf = (jl[-1]["long"] if jl else None), (jl[-2]["long"] if len(jl) > 1 else None)
    ftrend = None if lastf is None or prevf is None else "🚨 매도→매수 전환! (숨은 지원군 등장 가능성)" if prevf < 0 <= lastf else "⚠️ 매수→매도 전환 (지원군 이탈 신호)" if prevf >= 0 > lastf else "✅ 순매수 지속 중" if lastf >= 0 else "🔻 순매도 지속 중"
    boj = X.get("boj") or []
    nboj = next((b for b in boj if b["date"] >= (date.today() - timedelta(days=2)).isoformat()), None)
    dboj = (date.fromisoformat(nboj["date"]) - date.today()).days if nboj else None
    vix, hyb = L("VIXCLS"), hyv
    st2 = j1m is not None and (j1m >= 15 or ((j10 or 0) >= 1.5 and j1m >= 10))      # 수준이 아니라 1개월 상승폭
    seq = [
        {"n": 1, "name": "BOJ 회의", "active": dboj is not None and -2 <= dboj <= 7, "text": "날짜 정보 없음" if dboj is None else f"🚨 회의 {dboj}일 전" if 0 < dboj <= 7 else "회의 진행 중/직후" if -2 <= dboj <= 0 else f"⏳ {nboj['date']} ({dboj}일 후)"},
        {"n": 2, "name": "일본 10년물 급등", "active": st2, "text": "—" if j10 is None else f"{j10:.3f}% · 1개월 {j1m:+.0f}bp" if j1m is not None else f"{j10:.3f}%"},
        {"n": 3, "name": "일본 자금 본국 회수", "active": lastf is not None and lastf < -10000 and (j10 or 0) >= 1.5, "text": "—" if lastf is None else f"해외 중장기채 {lastf:+,.0f}억엔"},
        {"n": 4, "name": "공포 지수 상승 (VIX)", "active": vix is not None and vix >= 25 and st2, "text": "—" if vix is None else f"VIX {vix:.1f}"},
        {"n": 5, "name": "신용시장 전이 (HY)", "active": hyb is not None and hyb >= 600 and (vix or 0) >= 25, "text": "—" if hyb is None else f"HY {hyb:.0f}bp"},
    ]
    top = max([s["n"] for s in seq if s["active"]], default=0)
    S["japan"] = {"curve": [{"date": x[0], "y2": x[1], "y5": x[2], "y10": x[3], "y30": x[4]} for x in jv[-8:]][::-1], "j10": j10, "j1m": j1m, "spread": spread,
                  "spread_badge": None if spread is None else "⚠️ 캐리 청산 압박" if spread < 100 else "경계" if spread < 150 else "정상",
                  "carry": carry, "carry_badge": "🚨 위험 / 청산 임박" if carry >= 70 else "⚠️ 경계 / 압박 증가" if carry >= 40 else "🟢 정상",
                  "carry_st": "bad" if carry >= 70 else "warn" if carry >= 40 else "ok",
                  "hist10": [[x[0], x[3]] for x in jv][-260:],
                  "flow": jf[-12:][::-1], "flow_last": lastf, "flow_trend": ftrend, "flow_usd": lastf * 1e8 / (L("DEXJPUS") or 150) / 1e9 if lastf is not None else None,
                  "boj_next": nboj, "boj_days": dboj, "boj_list": [b for b in boj if b["date"] >= today][:6], "seq": seq, "seq_top": top,
                  "src": [_link("일본 재무성 국채 금리", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm"),
                          _link("일본 재무성 대외증권투자 주간", "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/index.htm"),
                          _link("일본은행 금융정책회의 일정", "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm")]}

    # ── 9. 역발상 지표 ───────────────────────────────────────
    move_r = Y.get("^MOVE") or []
    mv = _last(move_r)
    eu = F.get("DEXUSEU") or []
    eu30 = (eu[-1][1] / (_ago_d(eu, 30) or eu[-1][1]) - 1) * 100 if eu else None
    gold, spx = _last(Y.get("GC=F") or []), _last(Y.get("^GSPC") or [])
    S["contra"] = {"move": mv, "move_badge": lvl(mv, [(150, "위기"), (120, "긴장"), (100, "보통"), (80, "평온"), (-1e9, "매우 평온")]), "move_hist": move_r,
                   "eurusd": _last(eu), "eurusd_30": eu30, "sofr": L("SOFR"), "vix": vix, "vix_badge": lvl(vix, [(30, "공포"), (20, "경계"), (-1e9, "평온")]),
                   "hy": hyv, "hy_badge": lvl(hyv, [(800, "공포"), (600, "경계"), (400, "중립"), (-1e9, "낙관")]),
                   "gold_spx": gold / spx if gold and spx else None, "gold": gold, "spx": spx,
                   "src": [_link("Yahoo ^MOVE", "https://finance.yahoo.com/quote/%5EMOVE/"), _link("FRED VIXCLS", FU("VIXCLS")), _link("FRED DEXUSEU", FU("DEXUSEU"))]}

    # ── 10. 경기침체 선행 (SLOOS · C&I 대출 · HY) ──────────────────
    sl_ci, sl_all = F.get("DRTSCILM") or [], F.get("SUBLPDMOSXWBNQ") or []
    ci = F.get("BUSLOANS") or []
    ci_yoy = (ci[-1][1] / ci[-13][1] - 1) * 100 if len(ci) > 13 else None            # 월간 → 13개월 전과 비교 (원본 버그 수정)
    ci_yoy_prev = (ci[-13][1] / ci[-25][1] - 1) * 100 if len(ci) > 25 else None
    s1v = _last(sl_ci)
    sig = lambda v, rules: next((r for t, r in rules if v is not None and t(v)), ("na", "자료 없음"))
    s1 = sig(s1v, [(lambda v: v >= 40, ("crisis", "🚨 신용경색")), (lambda v: v >= 20, ("danger", "🔴 뚜렷한 긴축")), (lambda v: v >= 10, ("warning", "🟠 조짐")), (lambda v: v >= 0, ("neutral", "🔵 보통")), (lambda v: True, ("ok", "🟢 완화"))])
    s2 = sig(ci_yoy, [(lambda v: v < -3, ("crisis", "🚨 급감")), (lambda v: v < 0, ("danger", "🔴 감소")), (lambda v: v < 2, ("warning", "🟠 둔화")), (lambda v: v < 5, ("neutral", "🔵 보통")), (lambda v: True, ("ok", "🟢 양호"))])
    s3 = sig(hyv, [(lambda v: v >= 800, ("crisis", "🚨 공포")), (lambda v: v >= 600, ("danger", "🔴 경계")), (lambda v: v >= 500, ("warning", "🟠 상승")), (lambda v: v >= 400, ("neutral", "🔵 보통")), (lambda v: True, ("ok", "🟢 낙관"))])
    sigs = [s1, s2, s3]
    trig = sum(1 for s in sigs if s[0] in ("crisis", "danger"))
    wct = sum(1 for s in sigs if s[0] == "warning")
    rec_title, rec_badge = (("🚨 신용위기 단계 진입 — 3가지 신호 모두 악화", "🚨 3/3 트리거") if trig >= 3 else ("🔴 심각한 경계 — 2가지 신호 동시 악화", "🔴 2/3 트리거") if trig == 2 else
                            ("🟠 조짐 감지 — 1가지 신호 악화 (나머지 추세 주시)", "🟠 1/3 트리거") if trig == 1 else ("🟡 다중 경계 수위", f"🟡 {wct}/3 경계") if wct >= 2 else
                            ("🔵 일부 경계 — 큰 그림은 안정", f"🔵 {wct}/3 경계") if wct == 1 else ("🟢 신용 환경 안정 — 3가지 모두 정상", "🟢 정상"))
    sl_q = (sl_all[-1][1] - sl_all[-2][1]) if len(sl_all) > 1 else None
    hy90 = (hy[-1][1] - _ago_d(hy, 90)) if hy and _ago_d(hy, 90) is not None else None
    S["recession"] = {"sloos_ci": s1v, "sloos_all": _last(sl_all), "sloos_date": sl_ci[-1][0] if sl_ci else None, "sloos_q": sl_q,
                      "sloos_trend": None if sl_q is None else "🔴 긴축 가속" if sl_q >= 5 else "🟠 긴축 지속" if sl_q >= 0 else "🔵 완화 조짐" if sl_q >= -5 else "🟢 뚜렷한 완화",
                      "ci_yoy": ci_yoy, "hy": hyv, "sig": [{"name": "은행 대출 기준 (SLOOS 대기업·중견 C&I)", "v": s1v, "unit": "%p", "lv": s1[0], "label": s1[1], "hint": "+20%p 이상 = 긴축 뚜렷"},
                                                           {"name": "기업 대출 잔액 1년 증가율 (C&I)", "v": ci_yoy, "unit": "%", "lv": s2[0], "label": s2[1], "hint": "0% 아래 = 대출이 줄어드는 중"},
                                                           {"name": "하이일드 스프레드", "v": hyv, "unit": "bp", "lv": s3[0], "label": s3[1], "hint": "600bp 이상 = 경계"}],
                      "trig": trig, "warn": wct, "title": rec_title, "badge": rec_badge,
                      "end": [{"name": "대출 기준 분기 변화", "v": sl_q, "label": None if sl_q is None else "✅ 둔화 전환 — 바닥 조짐" if sl_q < -5 else "🟡 소폭 둔화" if sl_q < 0 else "⏳ 아직 긴축 지속"},
                              {"name": "C&I 대출 증가율 1년 전 대비", "v": (ci_yoy - ci_yoy_prev) if ci_yoy is not None and ci_yoy_prev is not None else None,
                               "label": None if ci_yoy is None or ci_yoy_prev is None else "✅ 반등 중" if ci_yoy - ci_yoy_prev > 1 else "🟡 안정화 조짐" if ci_yoy - ci_yoy_prev > 0 else "⏳ 아직 둔화"},
                              {"name": "HY 스프레드 90일 변화", "v": hy90, "label": None if hy90 is None else "✅ 뚜렷한 하락" if hy90 < -50 else "🟡 하락 조짐" if hy90 < 0 else "⏳ 아직 확대 중"}],
                      "src": [_link("FRED SLOOS 대기업·중견 C&I 대출 기준 (DRTSCILM)", FU("DRTSCILM")), _link("FRED SLOOS 전체", FU("SUBLPDMOSXWBNQ")), _link("FRED BUSLOANS", FU("BUSLOANS"))]}

    # ── 11. 이자 부담 (실시간) ─────────────────────────────────
    ip, rec_, debt_, gdp = F.get("A091RC1Q027SBEA") or [], F.get("W018RC1Q027SBEA") or [], F.get("GFDEBTN") or [], F.get("GDP") or []
    yoy4 = lambda r: (r[-1][1] / r[-5][1] - 1) * 100 if len(r) > 4 else None
    ig_, dg_ = yoy4(ip), yoy4(debt_)
    S["interest"] = {"interest": _last(ip), "receipts": _last(rec_), "debt": (_last(debt_) or 0) * 1e6 or None, "gdp": _last(gdp), "date": ip[-1][0] if ip else None,
                     "to_rev": _last(ip) / _last(rec_) * 100 if ip and rec_ else None, "to_gdp": _last(ip) / _last(gdp) * 100 if ip and gdp else None,
                     "int_g": ig_, "debt_g": dg_, "speed": ig_ / dg_ if ig_ is not None and dg_ else None,
                     "hist": [[d, v / dict(rec_).get(d, 0) * 100] for d, v in ip if dict(rec_).get(d)],
                     "src": [_link("FRED 연방정부 이자 지출 (연율)", FU("A091RC1Q027SBEA")), _link("FRED 연방정부 경상수입 (연율)", FU("W018RC1Q027SBEA")), _link("FRED 연방부채 총액", FU("GFDEBTN"))]}
    ii = S["interest"]
    ii["st"] = None if ii["to_rev"] is None else "bad" if ii["to_rev"] >= 25 else "warn" if ii["to_rev"] >= 18 or (ii["speed"] or 0) > 1 else "ok"
    b_amt = (S["debt"] or {}).get("amt", {}).get("bills")
    S["shock"] = [{"dp": dp, "bills_only": b_amt * dp / 100 if b_amt else None} for dp in (0.5, 1.0, 2.0)]

    # ── 12. 이벤트 캘린더 (자동) ────────────────────────────────
    lo, hi = (date.today() - timedelta(days=14)).isoformat(), (date.today() + timedelta(days=28)).isoformat()
    ev = []
    for a in AU:
        if lo <= a["date"] <= hi and a["type"] != "Bill":
            ev.append({"date": a["date"], "type": "auction", "title": f"{a['type_kr']} {a['term']} 입찰 (결과: {a['grade']}등급, 응찰 {a['btc']:.2f}배)", "imp": "high" if a["type"] == "Bond" or "10-Year" in (a["orig_term"] or a["term"] or "") else "med", "src": "Fiscal Data"})
    for u in S["upcoming"]:
        if u["date"] <= hi and u["type"] != "Bill":
            ev.append({"date": u["date"], "type": "auction", "title": f"{TERM_KR.get(u['type'], u['type'])} {u['term']} 입찰" + (f" ${u['offering'] / 1e9:,.0f}B" if u["offering"] else ""), "imp": "high" if u["type"] == "Bond" or "10-Year" in u["term"] else "med", "src": "Fiscal Data 예정"})
    nb = len([u for u in S["upcoming"] if u["type"] == "Bill" and u["date"] <= (date.today() + timedelta(days=7)).isoformat()])
    for f in X.get("fomc") or []:
        if lo <= f["date"] <= hi:
            ev.append({"date": f["date"], "type": "fed", "title": "FOMC 금리 결정" + (" + 경제전망(SEP·점도표)" if f["sep"] else ""), "imp": "high", "src": "연준"})
    for b in boj:
        if lo <= b["date"] <= hi:
            ev.append({"date": b["date"], "type": "policy", "title": "일본은행 금융정책 결정" + (" + 전망보고서" if b.get("outlook") else ""), "imp": "high", "src": "일본은행"})
    # 분기 국채 발행 계획(QRA): 재무부 공표 일정이 있으면 그것, 없으면 2·5·8·11월 첫째 주 월·수 (관행 추정)
    try:
        qn = absorb.qra().get("next") or []
    except Exception:
        qn = []
    for i_, nd_s in enumerate(qn[:2]):
        try:
            dd = datetime.strptime(nd_s, "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
        if lo <= dd <= hi:
            ev.append({"date": dd, "type": "policy", "title": ["재무부 분기 차입 추정치 발표 (QRA 1부)", "분기 국채 발행 계획 발표 (QRA 정책 발표)"][i_], "imp": "high", "src": "재무부 공표 일정"})
    for y in ((date.today().year, date.today().year + 1) if not qn else ()):
        for m in (2, 5, 8, 11):
            d0 = date(y, m, 1)
            wed = d0 + timedelta(days=(2 - d0.weekday()) % 7)
            mon = wed - timedelta(days=2)
            for dd, t in ((mon, "재무부 분기 차입 추정치 발표 (QRA 1부, 추정일)"), (wed, "분기 국채 발행 계획 발표 (QRA, 추정일)")):
                if lo <= dd.isoformat() <= hi:
                    ev.append({"date": dd.isoformat(), "type": "policy", "title": t, "imp": "high", "src": "재무부 관행"})
    S["events_auto"] = sorted(ev, key=lambda e: e["date"])
    S["bills_week"] = nb
    S["fomc_next"] = next((f for f in X.get("fomc") or [] if f["date"] >= today), None)

    # ── 13. 5대 지표 자동 판정 (QRA · FOMC · BOJ · CPI · NFP) ───────
    V = {}
    # QRA: 직전 리펀딩 달(2·5·8·11월)의 3·10·30년물 규모를 3개월 전과 비교
    cp = [a for a in AU if a["type"] in ("Note", "Bond")]
    def ref_sum(ym):
        out = {}
        for a in cp:
            if a["date"][:7] == ym:
                k = (a["orig_term"] or a["term"])
                for t in ("3-Year", "10-Year", "30-Year"):
                    if k.startswith(t) and t not in out:
                        out[t] = a["offering"] or 0
        return out
    ms_ = [m for m in sorted({a["date"][:7] for a in cp}, reverse=True) if int(m[5:]) in (2, 5, 8, 11)]
    q = None
    for m in ms_:
        cur_ = ref_sum(m)
        y_, mo = int(m[:4]), int(m[5:]) - 3
        if mo <= 0:
            y_, mo = y_ - 1, mo + 12
        prv_ = ref_sum(f"{y_}-{mo:02d}")
        if len(cur_) == 3 and len(prv_) == 3:
            tc_, tp_ = sum(cur_.values()), sum(prv_.values())
            pct = (tc_ - tp_) / tp_ * 100
            lab = "유지" if abs(pct) < 1 else "대폭 증액" if pct >= 5 else "소폭 증액" if pct > 0 else "감액"
            q = {"month": m, "total": tc_ / 1e9, "prev": tp_ / 1e9, "pct": pct, "label": lab, "sizes": {k: v / 1e9 for k, v in cur_.items()}}
            break
    if q:
        sc = {"유지": 1, "감액": 1, "소폭 증액": -0.5, "대폭 증액": -1}[q["label"]]
        V["qra"] = {"score": sc, "title": {"유지": "🟢 장기물 발행 유지", "감액": "🟢 장기물 발행 감액", "소폭 증액": "🟡 장기물 소폭 증액", "대폭 증액": "🔴 장기물 대폭 증액"}[q["label"]],
                    "summary": f"{q['month']} 리펀딩 3·10·30년물 ${q['total']:,.0f}B (3개월 전 ${q['prev']:,.0f}B, {q['pct']:+.1f}%) — 장기물 공급이 늘면 장기금리 부담", "data": q}
    # FOMC
    tu = F.get("DFEDTARU") or []
    if tu:
        cur_r = tu[-1][1]
        chg_d = next((tu[i][0] for i in range(len(tu) - 1, 0, -1) if tu[i][1] != tu[i - 1][1]), None)
        chg_v = next((tu[i][1] - tu[i - 1][1] for i in range(len(tu) - 1, 0, -1) if tu[i][1] != tu[i - 1][1]), 0)
        recent = chg_d and (date.today() - date.fromisoformat(chg_d)).days <= 50
        pce = F.get("PCEPILFE") or []
        core = (pce[-1][1] / pce[-13][1] - 1) * 100 if len(pce) > 13 else None
        mid = (cur_r + (L("DFEDTARL") if L("DFEDTARL") is not None else cur_r - 0.25)) / 2
        impl = ((L("DGS2") or mid) - mid) * 100
        wl = F.get("WALCL") or []
        r4 = (wl[-1][1] - wl[-5][1]) / 1000 if len(wl) > 8 else None
        o4 = (wl[-5][1] - wl[-9][1]) / 1000 if len(wl) > 8 else None
        qt = None if r4 is None else "중단" if r4 > 0 and o4 < 0 else "가속" if r4 < o4 - 20 else "감속" if r4 > o4 + 20 and r4 < 0 else "유지" if r4 < 0 else "확대(매입)"
        tone = "매파" if recent and chg_v > 0 else "비둘기" if recent and chg_v < 0 else ("매파" if core is not None and core >= 3.0 else "비둘기" if core is not None and core <= 2.2 else "중립")
        V["fomc"] = {"score": {"비둘기": 1, "중립": 0, "매파": -1}[tone], "title": {"비둘기": "🟢 비둘기 (완화적)", "중립": "⚖️ 중립", "매파": "🔴 매파 (긴축적)"}[tone],
                     "summary": f"기준금리 상단 {cur_r:.2f}%" + (f" · {chg_d} {chg_v * 100:+.0f}bp 변경" if chg_d and recent else " · 최근 50일 동결") + (f" · 근원 PCE {core:.1f}%" if core is not None else "")
                     + f" · 2년물이 말하는 앞으로의 금리 {impl:+.0f}bp" + (f" · 대차대조표 {qt} (4주 {r4:+,.0f}B)" if qt else ""),
                     "data": {"rate": cur_r, "core_pce": core, "implied": impl, "qt": qt, "next": S["fomc_next"]}}
    # BOJ
    if j10 is not None:
        sc = -1 if (j1m or 0) >= 15 or carry >= 70 else -0.5 if j10 >= 2.0 or carry >= 40 else 0
        jp = F.get("DEXJPUS") or []
        j30 = (jp[-1][1] / jp[-22][1] - 1) * 100 if len(jp) > 22 else None
        V["boj"] = {"score": sc, "title": "🔴 긴축 압력 큼 (캐리 위험)" if sc == -1 else "🟡 긴축 조짐" if sc < 0 else "🟢 안정",
                    "summary": f"일본 10년물 {j10:.2f}% · 캐리 압력 {carry}/100" + (f" · 엔/달러 1개월 {j30:+.1f}% ({'엔 약세' if j30 > 0 else '엔 강세'})" if j30 is not None else "") + (f" · 다음 회의 {nboj['date']}" if nboj else ""),
                    "data": {"j10": j10, "carry": carry, "usdjpy_1m": j30}}
    # CPI
    def yoy(k, n=12):
        r = F.get(k) or []
        return (r[-1][1] / r[-1 - n][1] - 1) * 100 if len(r) > n else None
    def mom(k, n=1):
        r = F.get(k) or []
        return ((r[-1][1] / r[-1 - n][1]) ** (1 / n) - 1) * 100 if len(r) > n else None
    cy = yoy("CPILFESL")
    if cy is not None:
        sc = -1 if cy >= 3.5 else -0.5 if cy >= 3.0 else 0.5 if cy >= 2.5 else 1
        V["cpi"] = {"score": sc, "title": "🔴 인플레 끈적" if cy >= 3.5 else "🟠 다소 끈적" if cy >= 3.0 else "🔵 보통" if cy >= 2.5 else "🟢 물가 안정",
                    "summary": f"근원 CPI 1년 {cy:.1f}% · 전체 {yoy('CPIAUCSL'):.1f}% · 서비스 한 달 {mom('CUSR0000SAS'):.2f}% · 주거비 3개월 평균 {mom('CUSR0000SAH1', 3):.2f}% · 에너지 한 달 {mom('CPIENGSL'):+.1f}%"
                    + f" ({(F.get('CPILFESL') or [['']])[-1][0][:7]})",
                    "data": {"core": cy, "headline": yoy("CPIAUCSL"), "services_mom": mom("CUSR0000SAS"), "shelter_3m": mom("CUSR0000SAH1", 3), "energy_mom": mom("CPIENGSL")}}
    pay = F.get("PAYEMS") or []
    if len(pay) > 4:
        nj = pay[-1][1] - pay[-2][1]
        a3 = (pay[-1][1] - pay[-4][1]) / 3
        sc = -1 if nj >= 250 else 0 if nj >= 150 else 0.5 if nj >= 75 else 1
        V["nfp"] = {"score": sc, "title": "🔴 고용 과열 (금리 인하 지연)" if nj >= 250 else "⚖️ 고용 보통" if nj >= 150 else "🔵 고용 둔화" if nj >= 75 else "🟢 고용 약함 (금리 인하 기대)",
                    "summary": f"신규 일자리 {nj:+,.0f}천 명 (3개월 평균 {a3:+,.0f}천) · 실업률 {L('UNRATE'):.1f}% · 시급 1년 {yoy('CES0500000003'):.1f}% · 경제활동참가율 {L('CIVPART'):.1f}% ({pay[-1][0][:7]})",
                    "data": {"jobs": nj, "avg3": a3, "unrate": L("UNRATE"), "wage": yoy("CES0500000003"), "part": L("CIVPART")}}
    sc_ = [v["score"] for v in V.values()]
    avg_s = sum(sc_) / len(sc_) if sc_ else None
    master = None if avg_s is None else (("🟢 Risk-On", "위험자산 유지") if avg_s >= 0.6 else ("🔵 약한 우호", "현금 10~15%") if avg_s >= 0.2 else ("⚖️ 중립", "현금 15~20%")
                                          if avg_s >= -0.2 else ("🟡 약한 부정", "위험자산 일부 축소") if avg_s >= -0.6 else ("🔴 Risk-Off", "장기 듀레이션·고밸류 축소, 현금·달러·금 점검"))
    S["verdicts"] = {"items": V, "avg": avg_s, "title": master[0] if master else None, "action": master[1] if master else None, "n": len(V)}

    # ── 13-b. 국채 흡수력 (윌리엄 시리즈 320~324) ──────────────────
    def _sf(fn):
        try:
            return fn()
        except Exception as e:
            errs.append(f"흡수력 {fn.__name__ if hasattr(fn, '__name__') else ''}: {str(e)[:80]}")
            return None
    QU = absorb.auction_quality(AU, F)
    DLR = _sf(sources.dealer_macro)
    TF = absorb.three_factors(F, QU, DLR)
    S["absorb"] = {"quality": QU, "three": TF, "investor": _sf(absorb.investor_view), "net": _sf(absorb.net_issuance),
                   "buyback": _sf(absorb.buybacks), "qra": _sf(absorb.qra),
                   "src": [_link("미 재무부 Investor Class Auction Allotments", "https://home.treasury.gov/data/investor-class-auction-allotments"),
                           _link("FRED THREEFYTP10 (연준 Kim-Wright 10년 기간프리미엄)", FU("THREEFYTP10")), _link("NY 연준 ACM 기간프리미엄", "https://www.newyorkfed.org/research/data_indicators/term-premia-tabs"),
                           _link("NY 연준 Primary Dealer 통계", "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics"),
                           _link("NY 연준 Primary Dealer 목록", "https://www.newyorkfed.org/markets/primarydealers")],
                   "basis": "윌리엄 「지금 놓치면 평생 후회로 남을 시리즈」 320 국채와 미국의 진정한 힘 · 321 거대자본이 3개월마다 보는 이면의 진실 · 322 재무부가 자기 국채를 다시 사들이는 이유 · 323 Fed가 가만히 있어도 장기금리는 · 324 국채 입찰은 누가 받아갔는지"}
    S["rates"]["tp_official"] = TF["tp"]

    # ── 14. 입찰 붕괴 경보 · 종합 등급 ──────────────────────────
    # 판정은 중장기물(Note·Bond) 최근 12건 기준 — 단기채는 원래 딜러 비중이 40% 안팎이라 섞으면 늘 '부진'으로 나옴
    ab, ad = S["auctions"]["coupon_avg_btc"], S["auctions"]["coupon_avg_dealer"]
    risk = 0
    if ab:
        risk += 0 if ab >= 2.5 else 15 if ab >= 2.2 else 30 if ab >= 2.0 else 40
    if ad is not None:
        risk += 0 if ad < 15 else 15 if ad < 20 else 30 if ad < 25 else 40
    risk += {"bad": 20, "warn": 10}.get(S["liq"].get("buffer_st"), 0)
    grade = "A" if risk <= 15 else "B" if risk <= 35 else "C" if risk <= 55 else "D" if risk <= 75 else "F"
    cba = [a for a in AU if a["type"] in ("Note", "Bond")]
    two_weak = len(cba) >= 2 and cba[0]["btc"] < 2.0 and cba[1]["btc"] < 2.0
    d10w = (F["DGS10"][-1][1] - F["DGS10"][-6][1]) * 100 if len(F.get("DGS10") or []) > 6 else None
    S["chain"] = {"risk": risk, "grade": grade, "grade_kr": {"A": "양호", "B": "보통", "C": "경계", "D": "위험", "F": "심각"}[grade],
                  "grade_desc": {"A": "경매 수요가 충분하고 유동성 완충도 넉넉해요.", "B": "대체로 괜찮지만 일부 지표가 평소보다 약해요.", "C": "수요가 약해지는 조짐 — 다음 입찰들을 이어서 보세요.",
                                 "D": "입찰 부진이 뚜렷해요 — 연쇄반응 1~2단계(장기 성장주·베이시스 트레이드)에 주의하세요.", "F": "입찰과 유동성이 동시에 나빠졌어요 — 가장 위험한 조합이에요."}[grade],
                  "watch": [{"t": "중장기물 응찰배율 2.0배 미만 2회 연속", "on": two_weak},
                            {"t": "Primary Dealer 25% 초과 + Indirect Bidder 비중 하락", "on": bool(cba) and (cba[0]["dealer"] or 0) > 25 and cba[0].get("prev") and (cba[0]["indirect"] or 0) < (cba[0]["prev"]["indirect"] or 0)},
                            {"t": "10년물 1주일 +20bp 이상", "on": d10w is not None and d10w >= 20, "v": d10w},
                            {"t": "유동성 완충 약화(지준 감소·SOFR−IORB 상승) + 약한 중장기물 입찰(C등급 이하)", "on": S["liq"].get("buffer_st") in ("warn", "bad") and any(a["grade"] in ("C", "D") for a in cba[:5])},
                            {"t": "같은 주 중장기물 D등급 2건 이상", "on": len([a for a in AU if a["type"] in ("Note", "Bond") and a["grade"] == "D" and a["date"] >= (date.today() - timedelta(days=7)).isoformat()]) >= 2}]}

    # ── 15. Bills Pivot 감지기 ─────────────────────────────────
    sh = (S["debt"] or {}).get("bills_share")
    so = S["soma"] or {}
    c1 = None if not q else ("fail" if q["label"] in ("유지", "감액") and (sh or 0) > 20 else "pass")
    c2 = None if sh is None else "fail" if sh > 22 else "warn" if sh > 20 else "pass"
    c3 = None if not so else "fail" if so["bills_chg"] > 0 and so["share_of_chg"] > 70 else "warn" if so["share_of_chg"] > 40 else "pass"
    cab, cad = S["auctions"]["coupon_avg_btc"], S["auctions"]["coupon_avg_dealer"]
    c4 = None if not cab else "fail" if cab < 2.3 and cad > 18 else "warn" if cab < 2.5 or cad > 15 else "pass"
    checks = [{"n": 1, "name": "쿠폰(중장기물) 증액 없이 단기물만 늘리는가", "st": c1, "v": f"리펀딩 장기물 {q['label']} · Bills 비중 {sh:.1f}%" if q and sh else "—"},
              {"n": 2, "name": "국채 중 단기물(Bills) 비중 구조적 상승", "st": c2, "v": f"{sh:.1f}% (TBAC 권고 15~20%)" if sh else "—"},
              {"n": 3, "name": "연준이 단기 구간(T-Bill)을 사들이는가", "st": c3, "v": f"5주 보유 증가분 중 Bills {so.get('share_of_chg', 0):.0f}%" if so else "—"},
              {"n": 4, "name": "중장기물 입찰 수요 약화", "st": c4, "v": f"최근 중장기물 12건 평균 응찰 {cab:.2f}배 · Primary Dealer {cad:.1f}%" if cab else "—"}]
    nf = len([c for c in checks if c["st"] == "fail"])
    S["pivot"] = {"checks": checks, "fails": nf,
                  "verdict": ["✅ 정상", "🔵 낮은 경보", "🟡 중간 경보: 부분적 Bills 편중", "⚠️ 높은 경보: Bills Pivot 레짐 진입", "🚨 최고 경보: 구조적 Bills Pivot 진행 중 (장기금리 통제 + 재정 스트레스 동시)"][nf],
                  "action": ["", "추세만 관찰", "장기 듀레이션 비중 점검", "장기 듀레이션 축소 · 달러자산 분산 검토", "장기 듀레이션 축소 · 달러자산 분산 · 금·현금 비중 점검"][nf]}

    # ── 16. 배관도 (9개 지점) ──────────────────────────────────
    def pipe(key, name, st, text, tab):
        return {"key": key, "name": name, "st": st, "text": text, "tab": tab}
    mv_ = mv or 0
    pipes = [
        pipe("treasury", "🏛️ 미 재무부 (발행)", "warn" if (sh or 0) > 22 else "ok", f"Bills 비중 {sh:.1f}%" if sh else "자료 없음", "issue"),
        pipe("fed", "⚙️ 연준", (so.get("st") if so else "ok"), f"기준금리 {(V.get('fomc') or {}).get('data', {}).get('rate', 0):.2f}% · " + ("T-Bill 집중 매입" if so and so["share_of_chg"] > 80 else "일부 단기 매입" if so and so["share_of_chg"] > 0 else "QT/중립"), "liq"),
        pipe("dealer", "🏦 Primary Dealer · 입찰", "bad" if (ab or 9) < 2.0 or (ad or 0) > 25 else "warn" if (ab or 9) < 2.3 or (ad or 0) > 18 else "ok",
             f"중장기물 평균 응찰 {ab:.2f}배 · Primary Dealer {ad:.1f}%" if ab else "자료 없음", "auc"),
        pipe("reservoir", "💧 유동성 저수조", S["liq"].get("buffer_st") or "ok",
             f"지준 13주 {(S['liq']['res_13w'] or 0):+,.0f}B · 역레포 ${rv:,.1f}B · TGA ${(S['liq']['tga_now'] or 0):,.0f}B · 지준 ${(S['liq']['res_now'] or 0):.2f}T" if rv is not None else "자료 없음", "liq"),
        pipe("repo", "🔄 레포 시장", "bad" if mv_ >= 120 or S["repo"]["danger"] >= 1 else "warn" if mv_ >= 100 or S["repo"]["warn"] else "ok",
             f"SOFR−IORB {si:+.0f}bp · MOVE {mv_:.0f}" if si is not None else f"MOVE {mv_:.0f}", "repo"),
        pipe("foreign", "🌍 해외 수요 (일본)", "bad" if (j1m or 0) >= 15 or (lastf or 0) < -20000 else "warn" if (j10 or 0) >= 2.0 or (lastf or 0) < -10000 else "ok",
             f"일본 10년물 {j10:.2f}% · 주간 해외채 {lastf:+,.0f}억엔" if j10 is not None and lastf is not None else "자료 없음", "japan"),
        pipe("credit", "⚠️ 신용 시장", "bad" if (hyv or 0) >= 800 else "warn" if (hyv or 0) >= 600 else "ok", f"HY {hyv:.0f}bp · IG {igv:.0f}bp" if hyv and igv else "자료 없음", "credit"),
        pipe("gauge", "📊 10년물 금리 압력계", "bad" if rc["key"] == "crisis" else "warn" if rc["key"] in ("supply", "inflation") else "ok",
             f"{rc['y10']:.2f}% · {rc['title'][:24]}" if rc.get("y10") else "자료 없음", "rates"),
        pipe("pivot", "🎯 Bills Pivot 감지기", "bad" if nf >= 3 else "warn" if nf >= 2 else "ok", f"{nf}/4 경보", "issue"),
    ]
    for p_ in pipes:
        if p_["key"] == "dealer":
            lastq = QU[0] if QU else None
            if TF["n"] >= 3 or (lastq and lastq["n"] >= 2):
                p_["st"] = "bad"
            elif TF["n"] == 2 and p_["st"] == "ok":
                p_["st"] = "warn"
            if lastq:
                p_["text"] += f" · 최근 {lastq['key']}년물 {lastq['verdict']}"
            p_["tab"] = "absorb"
    nd_, nw_ = len([p for p in pipes if p["st"] == "bad"]), len([p for p in pipes if p["st"] == "warn"])
    S["plumb"] = {"pipes": pipes, "bad": nd_, "warn": nw_,
                  "title": "🚨 다중 배관 이상: 시스템 스트레스 확인" if nd_ >= 3 else f"⚠️ {nd_}개 지점 이상 감지 — 집중 모니터링 필요" if nd_ >= 1 else f"🟠 {nw_}개 지점 경계 — 추이 관찰" if nw_ >= 2 else "🔵 대체로 정상 (일부 경계 지점)" if nw_ == 1 else "🟢 전 배관 정상 (압력 안정)",
                  "st": "bad" if nd_ >= 1 else "warn" if nw_ >= 2 else "ok"}

    # ── 17. 종합 의견 (분위기 · 점수 4종 · 오늘의 시황) ─────────────
    mood = ("bad" if (hyv or 0) >= 600 or mv_ >= 120 or (ab and ab < 2.0) or carry >= 70 else
            "warn" if (hyv or 0) >= 500 or mv_ >= 100 or (ab and ab < 2.3) or carry >= 40 or (ad or 0) >= 20 or S["liq"].get("buffer_st") == "bad" else
            "good" if hyv and hyv < 400 and vix and vix < 18 and ab and ab >= 2.5 else "neutral")
    tension = 50 + (20 if ab and ab < 2.0 else 10 if ab and ab < 2.3 else -10 if ab and ab > 2.7 else 0) + (20 if (ad or 0) > 25 else 10 if (ad or 0) > 20 else -5 if ad is not None and ad < 15 else 0) \
        + (15 if mv_ >= 120 else 8 if mv_ >= 100 else -5 if mv and mv < 80 else 0) + (15 if (hyv or 0) >= 600 else 8 if (hyv or 0) >= 500 else -5 if hyv and hyv < 350 else 0)
    tension = max(0, min(100, tension))
    liqs = {"ok": 65, "warn": 40, "bad": 20}.get(S["liq"].get("buffer_st"), 50) if rv is None or rv < 10 else 75 if rv > 500 else 60 if rv > 200 else 40 if rv > 100 else 20
    if liqs is not None and S["liq"]["res_13w"] is not None:
        liqs = max(0, min(100, liqs + (10 if S["liq"]["res_13w"] > 50 else -10 if S["liq"]["res_13w"] < -50 else 0)))
    narr = 75 if (liqs or 50) < 40 and (vix or 18) < 20 else 65 if (liqs or 50) < 50 and (vix or 18) < 18 else 30 if (liqs or 50) > 60 and (vix or 18) > 25 else 50
    S["scores"] = [
        {"k": "시장 긴장도", "v": tension, "badge": "높음" if tension >= 70 else "중간" if tension >= 40 else "낮음", "st": "bad" if tension >= 70 else "warn" if tension >= 40 else "ok", "why": "입찰 응찰배율·Primary Dealer 비중 + MOVE + 하이일드 스프레드"},
        {"k": "유동성 상태", "v": liqs, "badge": None if liqs is None else "양호" if liqs >= 60 else "보통" if liqs >= 30 else "부족", "st": None if liqs is None else "ok" if liqs >= 60 else "warn" if liqs >= 30 else "bad", "why": "역레포 잔고(바닥이면 지준·SOFR−IORB 완충 판정) + 은행 지준 3개월 변화"},
        {"k": "경매 수요", "v": grade, "badge": "양호" if grade in ("A", "B") else "보통" if grade == "C" else "부진", "st": "ok" if grade in ("A", "B") else "warn" if grade == "C" else "bad", "why": "입찰 건전성 종합 등급 (응찰배율·Primary Dealer 비중·유동성 완충)"},
        {"k": "내러티브 괴리", "v": narr, "badge": "괴리 큼" if narr >= 65 else "중립" if narr >= 40 else "일치", "st": "warn" if narr >= 65 else "ok", "why": "유동성은 마르는데 공포 지수는 낮은가 (안심이 지나친가)"},
    ]
    S["mood"] = {"key": mood, "label": {"bad": "🔴 긴장", "warn": "🟠 경계", "good": "🟢 평온", "neutral": "🔵 중립"}[mood]}
    S["narrative"] = _narrative(S, mood, ab, ad, rv, si, s75, hyv, vix, mv, j10, carry, lastf, sh)
    S["three"] = _three_lines(S)
    S["three"].append(f"국채 흡수력: {TF['verdict']} — 기간프리미엄 1년 {TF['tp']['d1y']:+.0f}bp · 최근 45일 꼬리 입찰 {TF['tail']['n1']}/{TF['tail']['n']}건 · Primary Dealer 국채 보유 8주 {TF['dealer']['ust_pct'] if TF['dealer']['ust_pct'] is not None else 0:+.1f}%" if TF['tp']['d1y'] is not None else f"국채 흡수력: {TF['verdict']}")
    S["narrative"].insert(-2, "국채를 '누가 받아 갔는지'를 보면, " + (f"최근 중장기물 입찰 {len(QU[:6])}건 중 흡수 실패 의심 {len([q for q in QU[:6] if q['n'] >= 2])}건, 일부 약함 {len([q for q in QU[:6] if q['n'] == 1])}건이에요. " if QU else "")
                       + (f"장기채를 오래 들고 있는 대가인 기간프리미엄은 {TF['tp']['v']:.2f}%" + (f"로 1년 동안 {TF['tp']['d1y']:+.0f}bp 움직였어요. " if TF['tp']['d1y'] is not None else ". ") if TF['tp']['v'] is not None else "기간프리미엄 자료(FRED)를 지금 받지 못했어요. ")
                       + {3: "기간프리미엄·꼬리 입찰·Primary Dealer 부담이 동시에 나빠져 Fed가 가만히 있어도 장기금리가 스스로 오를 수 있는 상태예요.", 2: "흡수력 3요소 중 두 가지가 약해져 장기금리 상승 압력이 쌓이고 있어요.", 1: "흡수력 3요소 중 한 가지만 약해 아직은 지켜볼 단계예요.", 0: "국채 흡수력은 양호해요."}[TF["n"]])
    return S


def _narrative(S, mood, ab, ad, rv, si, s75, hyv, vix, mv, j10, carry, lastf, sh):
    wd = "월화수목금토일"[date.today().weekday()]
    rc = S["rates"]
    P = []
    p1 = f"{date.today().month}월 {date.today().day}일({wd}) 미국 국채 시장의 분위기는 「{S['mood']['label']}」이에요. "
    if rc.get("y10") is not None:
        k = rc.get("key")
        dn = rc.get("d_nom")
        p1 += f"10년물 금리는 {rc['y10']:.2f}%" + (f"로 한 달 동안 {dn:+.0f}bp 움직였는데, " if dn is not None else "이고, ")
        p1 += {"healthy": "주로 실질금리(성장 기대)가 끌어올린 건강한 상승이에요.", "inflation": "물가 걱정(기대인플레)이 끌어올렸어요 — 연준이 매파적으로 돌아설 수 있어요.",
               "supply": "국채 공급 부담(기간프리미엄)이 끌어올렸어요 — 재정 걱정 신호예요.", "crisis": "기간프리미엄 상승과 유동성 악화가 함께 나타났어요 — 2019년 레포 위기와 비슷한 조합이라 가장 주의할 상황이에요.",
               "fear": "경기 둔화 걱정으로 안전자산에 돈이 몰리며 내렸어요.", "disinfl": "물가 걱정이 줄면서 내렸어요 — 위험자산엔 우호적이에요."}.get(k, "큰 방향성 없이 움직였어요.")
    P.append(p1)
    p2 = "국채라는 수도관을 보면, "
    if ab:
        p2 += f"최근 중장기물 입찰 응찰배율 평균은 {ab:.2f}배로 " + ("국채가 잘 흡수되고 있어요. " if ab >= 2.5 else "보통 수준이에요. " if ab >= 2.3 else "수요가 약해지는 조짐이 있어요. " if ab >= 2.0 else "수요가 부진해요. ")
    if ad is not None:
        p2 += f"Primary Dealer가 떠안은 비중은 {ad:.1f}%로 " + ("부담이 꽤 커요. " if ad >= 25 else "조금 높은 편이에요. " if ad >= 18 else "정상이에요. ")
    tg = S["liq"]["tga_now"]
    if tg:
        p2 += f"정부 통장(TGA)에는 ${tg:,.0f}B가 있고, "
    if rv is not None:
        p2 += f"비상용 물탱크인 역레포에는 ${rv:,.1f}B가 남았어요" + ((" — 2025년 말 이후 구조적으로 바닥이라, 지금 완충 여부는 은행 지준과 SOFR−IORB로 봐요(현재 " + {"ok": "안정", "warn": "주의", "bad": "위험"}.get(S["liq"].get("buffer_st"), "판단 불가") + "). ") if rv < 10 else " — 완충장치가 얇아진 상태예요. " if rv < 100 else " — 낮은 수준이에요. " if rv < 300 else ". ")
    if si is not None:
        p2 += f"단기 자금 금리(SOFR)는 연준 기준선(IORB)보다 {si:+.0f}bp" + (" 높아 레포 시장이 빡빡해요." if si >= 5 else " 수준이라 레포 시장은 안정적이에요.")
    P.append(p2)
    if j10 is not None:
        p3 = f"바다 건너 일본에서는 10년물 국채 금리가 {j10:.2f}%예요" + (" — 엔 캐리 트레이드 청산 압력이 매우 높은 수준이에요. " if j10 >= 2.0 else " — 일본에서 돈을 빌리는 비용이 오르고 있어요. " if j10 >= 1.5 else " — 안정적이에요. ")
        if lastf is not None:
            p3 += f"지난주 일본 투자자는 해외 중장기채를 {abs(lastf):,.0f}억엔 " + ("순매수했어요 — 미국 국채의 '숨은 지원군'이 아직 있어요." if lastf >= 0 else "순매도했어요 — 해외 수요가 빠져나가는 신호예요.")
        p3 += f" 캐리 압력 점수는 {carry}/100이에요."
        P.append(p3)
    p4 = ""
    if hyv:
        p4 += f"신용시장에서 하이일드 스프레드는 {hyv:.0f}bp로 " + ("공포에 가까워요. " if hyv >= 800 else "경계 수준이에요. " if hyv >= 600 else "보통이에요. " if hyv >= 400 else "투자자들이 낙관적이에요. ")
    if vix:
        p4 += f"주식 공포지수(VIX)는 {vix:.1f}, "
    if mv:
        p4 += f"채권 변동성(MOVE)은 {mv:.0f}로 " + ("매우 높아 재무부가 국채 바이백(되사기)에 적극 나설 가능성이 있어요." if mv >= 120 else "다소 높아요." if mv >= 100 else "안정적이에요.")
    if p4:
        P.append(p4)
    R = S["recession"]
    P.append(f"은행 대출 창구를 보면 「{R['title']}」 상태예요 — 경기침체는 뉴스보다 은행 대출 창구에서 먼저 시작돼요. '돈의 가격(금리)은 내려도 돈의 문(대출 심사)이 닫혀 있으면' 경기는 살아나지 않아요.")
    P.append("종합하면, " + {"bad": "긴장 신호가 여러 곳에서 켜졌어요. 장기 듀레이션 자산(고밸류 성장주·장기채) 비중을 점검하되, 하루 숫자보다 며칠 이어지는지를 확인하세요.",
                             "warn": "경계할 지점이 보여요. 현금 비중을 10~20% 확보하고 다음 입찰·물가 지표를 지켜보세요.",
                             "good": "전반적으로 평온해요. 하지만 '평온할 때가 가장 위험하다'는 말처럼 지나친 낙관은 경계하세요.",
                             "neutral": "뚜렷한 방향이 없는 상태예요. 다가오는 물가(CPI)·고용·입찰 결과가 다음 방향을 정할 거예요."}[mood]
             + " 위 배관도에서 빨간색·주황색 지점을 먼저 확인하세요. (자동 생성 요약 — 투자 조언이 아니에요)")
    return P


def _three_lines(S):
    out = []
    d = S.get("debt") or {}
    if d.get("bills_share"):
        out.append(f"국채 중 단기물(Bills) 비중 {d['bills_share']:.1f}% — TBAC 권고 15~20% " + ("초과: 재무부가 장기금리를 자극하지 않으려 단기물로 버티는 중" if d["bills_share"] > 20 else "범위 안"))
    L_ = S["liq"]
    if L_.get("rrp_now") is not None:
        out.append(f"유동성 완충: 역레포 ${L_['rrp_now']:,.1f}B ({L_['rrp_badge']}) · TGA ${(L_['tga_now'] or 0):,.0f}B (30일 {(L_['tga_30'] or 0):+,.0f}B) · 은행 지준 ${(L_['res_now'] or 0):.2f}T")
    a = S["auctions"]
    if a.get("avg_btc"):
        out.append(f"입찰 수요: 최근 중장기물 12건 평균 응찰 {a['coupon_avg_btc']:.2f}배 · Primary Dealer {a['coupon_avg_dealer']:.1f}% → 종합 {S['chain']['grade']}등급 ({S['chain']['grade_kr']}) · 배관 {S['plumb']['title']}")
    return out


def state(force=False):
    with _LOCK:
        c = _MEM.get("s")
        if c and not force and time.time() - c[0] < 20 * 60:
            return c[1]
    s = build_state()
    with _LOCK:
        _MEM["s"] = (time.time(), s)
    return s
