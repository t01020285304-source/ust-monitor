"""
국채 흡수력 — 윌리엄 「지금 놓치면 평생 후회로 남을 시리즈」 320~324 (사용자 제공, 2026-10-07~19)
  320 「국채와 미국의 진정한 힘」          Bill vs Coupon 순발행 → 레포 압력 (Fed 추정: $1,000억당 Bill 1.3bp · Coupon 3.9bp)
  321 「거대자본이 3개월마다 보는 진실」    QRA = 국채 공급 지도 (총 조달액 · 만기별 발행량 · 예상과 바뀐 부분)
  322 「재무부가 자기 국채를 다시 사는 이유」 Buyback (규모 · 만기 · 딜러가 팔려는 물량 · 목적)
  323 「Fed가 가만히 있어도 장기금리는」     Term Premium · Auction Tail · Dealer Capacity 3요소
  324 「국채 입찰은 누가 받아갔는지」        흡수의 질 = Tail · Indirect · Dealer 를 평소와 함께 비교 + 투자자 유형별 실제 배정
자료: 미 재무부 Fiscal Data(입찰·바이백·MSPD) · 재무부 Investor Class Auction Allotments · 재무부 QRA 보도자료 · FRED(CMT 금리·Kim-Wright 기간프리미엄) · NY 연준 프라이머리 딜러 통계
"""
import html as _html
import io
import re
from datetime import date, datetime, timedelta

import requests

import sources

UA = {"User-Agent": "MangoResearch/1.0 (personal research)"}
FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
TSY = "https://home.treasury.gov"
CMT = {2: "DGS2", 3: "DGS3", 5: "DGS5", 7: "DGS7", 10: "DGS10", 20: "DGS20", 30: "DGS30"}
FRED_NEED = {"DGS3": 400, "DGS5": 400, "DGS7": 400, "DGS20": 400, "THREEFYTP10": 800}


def _num(x):
    try:
        return None if x in (None, "", "null") else float(x)
    except (TypeError, ValueError):
        return None


def _txt(url):
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text))))


def _years(term):
    m = re.match(r"(\d+)-Year", term or "")
    if not m:
        return None
    y = int(m.group(1)) + (1 if re.search(r"\d+-Month", term or "") else 0)
    return min(CMT, key=lambda k: abs(k - y))


def _at(rows, d):
    """d 이전(포함) 가장 가까운 값"""
    p = [v for k, v in rows if k <= d]
    return p[-1] if p else None


# ── 324 · 323: 입찰마다 테일(근사) + 흡수의 질 ───────────────────────
def auction_quality(AU, F):
    cp = [a for a in AU if a["type"] in ("Note", "Bond")]
    for a in cp:
        k = _years(a["orig_term"] or a["term"])
        a["cmt_key"] = k
        cm = _at(F.get(CMT.get(k), []) or [], a["date"]) if k else None
        a["cmt"] = cm
        a["tail"] = round((a["high"] - cm) * 100, 1) if cm is not None and a.get("high") is not None else None
    out = []
    for i, a in enumerate(cp):
        prev = [b for b in cp[i + 1:] if b.get("cmt_key") == a.get("cmt_key")][:6]
        if len(prev) < 3:
            continue
        mi = sum(b["indirect"] or 0 for b in prev) / len(prev)
        md = sum(b["dealer"] or 0 for b in prev) / len(prev)
        tails = [b["tail"] for b in prev if b.get("tail") is not None]
        mt = sum(tails) / len(tails) if tails else None
        # 테일 근사치(낙찰금리 − 당일 종가 기준 시장금리)는 시각 차이로 만기마다 고질적 치우침이 있어 '같은 만기의 평소 테일'보다 2bp 이상 클 때만 꼬리로 본다
        f_tail = a.get("tail") is not None and mt is not None and a["tail"] - mt >= 2
        f_ind = (a["indirect"] or 0) < mi - 5
        f_dl = (a["dealer"] or 0) > md + 5
        n = f_tail + f_ind + f_dl
        out.append({"date": a["date"], "term": a["term"], "label": a.get("label"), "key": a.get("cmt_key"), "btc": a["btc"], "high": a["high"], "cmt": a.get("cmt"),
                    "tail": a.get("tail"), "tail_avg": mt, "tail_ex": (a["tail"] - mt) if a.get("tail") is not None and mt is not None else None, "indirect": a["indirect"], "ind_avg": mi, "dealer": a["dealer"], "dl_avg": md,
                    "flags": {"tail": f_tail, "ind": f_ind, "dl": f_dl}, "n": n,
                    "verdict": ["흡수 양호", "일부 약함", "흡수 실패 의심", "흡수 실패 의심"][n], "st": ["ok", "warn", "bad", "bad"][n]})
    return out[:14]


# ── 324: 투자자 유형별 실제 배정 (재무부 Investor Class Auction Allotments) ───
IC_COLS = ["soma", "depository", "individuals", "dealers", "pension_ins", "inv_funds", "foreign", "other"]
IC_KR = {"soma": "연준(SOMA)", "depository": "은행", "individuals": "개인", "dealers": "Dealers and Brokers", "pension_ins": "연기금·보험", "inv_funds": "투자펀드", "foreign": "해외·국제기구", "other": "기타"}


def investor_class():
    def load():
        h = requests.get(TSY + "/data/investor-class-auction-allotments", headers=UA, timeout=40).text
        m = re.search(r"href=\"?/system/+(files/276/[^\"\s>]*IC-Coupons\.xls)", h)     # 재무부가 '/system//files/'처럼 슬래시를 겹쳐 쓰기도 함
        if not m:
            raise ValueError("배정 파일 링크를 찾지 못했어요")
        import xlrd
        url = TSY + "/system/" + m.group(1)
        wb = xlrd.open_workbook(file_contents=requests.get(url, headers=UA, timeout=60).content)
        sh = wb.sheet_by_index(0)
        rows = []
        for i in range(sh.nrows):
            v = sh.row_values(i)
            if isinstance(v[0], float) and isinstance(v[5], float) and v[5] > 0:
                d = xlrd.xldate_as_datetime(v[0], wb.datemode).date().isoformat()
                rows.append({"issue": d, "sec": str(v[1]).strip(), "cusip": v[3], "total": v[5], **{k: (v[6 + j] or 0) for j, k in enumerate(IC_COLS)}})
            if len(rows) >= 200:
                break
        return {"url": url, "rows": rows}
    return sources._cached("ust_investor_class.json", 24 * 3600, load)


def investor_view():
    D = investor_class()
    rows = D["rows"]
    out = []
    for i, r in enumerate(rows[:40]):
        if r["sec"].startswith(("TIPS", "FRN", "2-Year FRN")) or "TIPS" in r["sec"] or "FRN" in r["sec"]:
            continue
        priv = r["total"] - r["soma"]                  # 시장 물량 = 전체 − 연준 몫
        if priv <= 0:
            continue
        sh = {k: r[k] / priv * 100 for k in IC_COLS if k != "soma"}
        prev = [p for p in rows[i + 1:] if p["sec"] == r["sec"]][:6]
        base = {}
        if prev:
            for k in sh:
                base[k] = sum(p[k] / max(p["total"] - p["soma"], 1e-9) * 100 for p in prev) / len(prev)
        out.append({"issue": r["issue"], "sec": r["sec"], "total": r["total"], "soma": r["soma"], "share": sh, "base": base})
        if len(out) >= 10:
            break
    return {"rows": out, "kr": IC_KR, "url": D["url"], "page": TSY + "/data/investor-class-auction-allotments"}


# ── 323: 딜러 여력 · 기간프리미엄 · 3요소 종합 ─────────────────────
def three_factors(F, quality, dealer):
    tp = F.get("THREEFYTP10") or []
    tpv = tp[-1][1] if tp else None
    tp30 = (tpv - _at(tp, (date.fromisoformat(tp[-1][0]) - timedelta(days=30)).isoformat())) * 100 if tp and _at(tp, (date.fromisoformat(tp[-1][0]) - timedelta(days=30)).isoformat()) is not None else None
    tp1y = (tpv - _at(tp, (date.fromisoformat(tp[-1][0]) - timedelta(days=365)).isoformat())) * 100 if tp and _at(tp, (date.fromisoformat(tp[-1][0]) - timedelta(days=365)).isoformat()) is not None else None
    f_tp = tp30 is not None and (tp30 >= 15 or (tp1y is not None and tp1y >= 50 and tp30 > 0))
    rec = [q for q in quality if q["date"] >= (date.today() - timedelta(days=45)).isoformat()]
    tails = [q for q in rec if q.get("tail_ex") is not None]
    f_tail = len([q for q in tails if q["flags"]["tail"]]) >= 2
    st = (dealer or {}).get("states", {})
    ust, repo = st.get("us_tsy", {}), st.get("repo", {})
    f_dl = (ust.get("pct") or 0) >= 10 and (repo.get("pct") or 0) >= 5
    n = f_tp + f_tail + f_dl
    return {"tp": {"v": tpv, "d30": tp30, "d1y": tp1y, "hist": tp[-520:], "flag": f_tp, "date": tp[-1][0] if tp else None},
            "tail": {"n": len(tails), "n1": len([q for q in tails if q["flags"]["tail"]]), "max": max((q["tail_ex"] for q in tails), default=None), "flag": f_tail},
            "dealer": {"ust": ust.get("latest"), "ust_pct": ust.get("pct"), "repo": repo.get("latest"), "repo_pct": repo.get("pct"), "asof": (dealer or {}).get("asof"), "flag": f_dl,
                       "net_fin": (st.get("net_fin") or {}).get("latest")},
            "n": n, "st": "bad" if n >= 3 else "warn" if n == 2 else "na" if n == 1 else "ok",
            "verdict": ["🟢 국채 흡수력 양호", "🔵 한 가지 약함 — 지켜보기", "🟠 두 가지 동시 약화 — 장기금리 상승 압력", "🔴 세 가지 동시 악화 — Fed가 가만히 있어도 장기금리가 스스로 오를 수 있는 상태"][n]}


# ── 320: Bill vs Coupon 순발행 → 레포 압력 ──────────────────────
def net_issuance():
    def load():
        r = requests.get(FD + "/v1/debt/mspd/mspd_table_1", headers=UA, timeout=40,
                         params={"sort": "-record_date", "page[size]": "400", "fields": "record_date,security_type_desc,security_class_desc,total_mil_amt",
                                 "filter": f"record_date:gte:{(date.today() - timedelta(days=500)).isoformat()}"})
        r.raise_for_status()
        by = {}
        for x in r.json()["data"]:
            if x["security_type_desc"] != "Marketable":
                continue
            c = x["security_class_desc"].lower()
            k = "bills" if c == "bills" else "coupons" if c in ("notes", "bonds") or "inflation" in c or "floating" in c else None
            if k:
                d = by.setdefault(x["record_date"], {"bills": 0, "coupons": 0})
                d[k] += _num(x["total_mil_amt"]) or 0
        return sorted([d, v["bills"] / 1000, v["coupons"] / 1000] for d, v in by.items())
    s = sources._cached("ust_mspd_hist.json", 12 * 3600, load)
    if len(s) < 4:
        return None
    a, b = s[-1], s[-4]
    y = s[-13] if len(s) >= 13 else s[0]
    db, dc = a[1] - b[1], a[2] - b[2]
    return {"asof": a[0], "from": b[0], "d_bills": db, "d_coupons": dc, "share_bills": db / (db + dc) * 100 if db + dc else None,
            "repo_bp": 1.3 * db / 100 + 3.9 * dc / 100, "repo_bills": 1.3 * db / 100, "repo_coupons": 3.9 * dc / 100,
            "y_bills": a[1] - y[1], "y_coupons": a[2] - y[2], "hist": [[d, b_, c_] for d, b_, c_ in s][-15:],
            "basis": "Fed 이사회 「Repo Markets and the Fed’s Balance Sheet」 추정(2014~2026): 순발행 $1,000억당 레포 금리 Bill +1.3bp · Coupon +3.9bp (윌리엄 칼럼 320 인용)"}


# ── 322: 재무부 Buyback ─────────────────────────────────────────
def buybacks():
    def load():
        r = requests.get(FD + "/v1/accounting/od/buybacks_operations", headers=UA, timeout=40,
                         params={"sort": "-operation_date", "page[size]": "200", "filter": f"operation_date:gte:{(date.today() - timedelta(days=400)).isoformat()}"})
        r.raise_for_status()
        return r.json()["data"]
    ops = sources._cached("ust_buybacks.json", 6 * 3600, load)
    rows = []
    for o in ops:
        acc, off, mx = _num(o.get("total_par_amt_accepted")), _num(o.get("total_par_amt_offered")), _num(o.get("max_par_amt_redeemed"))
        rows.append({"date": o["operation_date"], "type": o.get("operation_type"), "sec": o.get("security_type"), "bucket": o.get("maturity_bucket"),
                     "accepted": acc / 1e9 if acc else None, "offered": off / 1e9 if off else None, "max": mx / 1e9 if mx else None,
                     "ratio": off / acc if off and acc else None, "pdf": f"https://www.treasurydirect.gov/instit/annceresult/press/preanre/{o['operation_date'][:4]}/{o['results_pdf']}" if o.get("results_pdf") not in (None, "null") else None})
    done = [r for r in rows if r["accepted"]]
    cut90 = (date.today() - timedelta(days=90)).isoformat()
    by_b = {}
    for r in done:
        if r["date"] < cut90:
            continue
        b = by_b.setdefault(f"{r['type']} · {r['bucket']}", {"n": 0, "acc": 0, "off": 0, "max": 0})
        b["n"] += 1
        b["acc"] += r["accepted"]
        b["off"] += r["offered"] or 0
        b["max"] = max(b["max"], r["max"] or 0)
    months = {}
    for r in done:
        months.setdefault(r["date"][:7], 0)
        months[r["date"][:7]] += r["accepted"]
    long_ = [r for r in done if r["bucket"] and re.search(r"10Y to 20Y|20Y to 30Y", r["bucket"]) and r["type"] == "Liquidity Support"]
    ratio_recent = [r["ratio"] for r in done[:10] if r["ratio"]]
    return {"recent": rows[:15], "by_bucket": sorted(([k, v] for k, v in by_b.items()), key=lambda kv: -kv[1]["acc"]),
            "months": sorted(months.items())[-8:], "total_90d": sum(v["acc"] for v in by_b.values()),
            "long_max_now": long_[0]["max"] if long_ else None, "long_max_prev": next((r["max"] for r in long_ if r["max"] and long_ and r["max"] < long_[0]["max"]), None),
            "ratio_avg": sum(ratio_recent) / len(ratio_recent) if ratio_recent else None,
            "src": [{"label": "미 재무부 Fiscal Data — 바이백 실적", "url": "https://fiscaldata.treasury.gov/datasets/treasury-securities-buybacks/"},
                    {"label": "재무부 바이백 안내", "url": "https://home.treasury.gov/policy-issues/financing-the-government/treasury-buybacks"}]}


# ── 321: QRA = 국채 공급 지도 ────────────────────────────────────
def qra():
    def load():
        page = TSY + "/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents"
        h = requests.get(page, headers=UA, timeout=40).text
        link = lambda kw: (re.search(r"href=[\"']?(/news/press-releases/[a-z0-9]+)[\"']?[^>]*>\s*(?:<[^>]+>\s*)*" + kw, h) or [None, None])[1]
        t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h)))
        nxt = re.findall(r"next release is scheduled for ([A-Z][a-z]+ \d{1,2}\s*,\s*\d{4})", t)
        out = {"page": page, "next": [re.sub(r"\s+,", ",", x) for x in nxt]}
        fe, ps = link("Financing Estimates"), link("Policy Statement")
        if fe:
            x = _txt(TSY + fe)
            q = re.findall(r"During the ([A-Z][a-z]+[–-][A-Z][a-z]+ \d{4}) quarter, Treasury expects to borrow \$([\d,]+) billion[^.]*?cash balance of \$([\d,]+) billion", x)
            ch = re.search(r"borrowing estimate is \$([\d,]+) billion (higher|lower) than announced in ([A-Z][a-z]+ \d{4})", x)
            act = re.search(r"During the ([A-Z][a-z]+[–-][A-Z][a-z]+ \d{4}) quarter, Treasury borrowed \$([\d,]+) billion", x)
            out["estimates"] = {"url": TSY + fe, "quarters": [{"q": a, "borrow": float(b.replace(",", "")), "cash": float(c.replace(",", ""))} for a, b, c in q],
                                "change": {"amt": float(ch.group(1).replace(",", "")) * (1 if ch.group(2) == "higher" else -1), "vs": ch.group(3)} if ch else None,
                                "actual": {"q": act.group(1), "borrow": float(act.group(2).replace(",", ""))} if act else None}
        if ps:
            x = _txt(TSY + ps)
            g = lambda pat: (lambda mm: float(mm.group(1).replace(",", "")) if mm else None)(re.search(pat, x))
            offering, refund, new_cash = g(r"offering \$([\d.,]+) billion of Treasury securities"), g(r"to refund approximately \$([\d.,]+) billion"), g(r"new cash from private investors of approximately \$([\d.,]+) billion")
            secs = re.findall(r"A (\d+)-year (note|bond) in the amount of \$([\d.,]+) billion", x)
            guide = [s.strip() for s in re.findall(r"[^.]*(?:anticipates|expects|continues to evaluate)[^.]*(?:coupon|auction sizes|bill)[^.]*\.", x)][:3]
            out["policy"] = {"url": TSY + ps, "offering": offering, "refund": refund, "new_cash": new_cash, "secs": [{"y": int(a), "kind": b, "amt": float(c.replace(",", ""))} for a, b, c in secs], "guidance": guide}
        return out
    return sources._cached("ust_qra.json", 12 * 3600, load)
