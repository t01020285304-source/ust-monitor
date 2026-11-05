"""🛢️ 원자재 레이더 (Commodity & Capital Radar) 1차 — CFTC COT + EIA 재고 + 공식 가격 → radar.json

원칙
- 가격 숫자는 공식 출처(FRED: EIA 현물 · IMF 월평균)만. 이번 주 방향(등락률)은 공식 일간이 없으면 Yahoo 선물 '등락률만' 참고로.
  Yahoo 원시 시세는 저장소·캐시에 남기지 않음 (공개 data 브랜치에 재배포하지 않기 위해).
- 빠진 주·없는 값은 빈칸. 이웃 값이나 추정으로 채우지 않음.
- 매핑이 불확실한 계약(radar_meta status='check')은 포지션을 기본으로 숨김.
"""
import os
import time
from datetime import date, datetime, timedelta, timezone

import requests

import markets
import radar_meta as M
import radar_store as RS
import sources

UA = {"User-Agent": "MangoUSTMonitor https://mango-ust.netlify.app"}
CFTC_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
YEARS = 3


# ══ 계산 (인터넷 없이 테스트 — tests/test_radar.py) ═══════════════
def _d(s):
    return date.fromisoformat(s[:10])


def find_near(rows, target, tol=3):
    """[(obs, v)]에서 target ±tol일 안의 가장 가까운 값 — 없으면 None (이웃 주로 대체하지 않음)"""
    t = _d(target)
    best = None
    for o, v in rows:
        dd = abs((_d(o) - t).days)
        if dd <= tol and (best is None or dd < best[0]):
            best = (dd, v)
    return best[1] if best else None


def find_before(rows, target, back=3):
    """target 당일 또는 그 이전 back일 안의 가장 최근 값 (가격: 화요일이 휴장이면 직전 영업일)"""
    t = _d(target)
    best = None
    for o, v in rows:
        dd = (t - _d(o)).days
        if 0 <= dd <= back and (best is None or dd < best[0]):
            best = (dd, v)
    return best[1] if best else None


def net_rows(longs, shorts):
    s = dict(shorts)
    return [(o, v - s[o]) for o, v in longs if o in s]


def change(rows, obs, days, tol=3):
    cur = dict(rows).get(obs)
    prev = find_near(rows, (_d(obs) - timedelta(days=days)).isoformat(), tol)
    return None if cur is None or prev is None else cur - prev


def percentile(rows, obs, weeks=156, min_n=130):
    """최근 156주(3년) 중 이번 주 값의 위치 (같은 값은 절반) — 표본 130주 미만이면 None"""
    win = [v for o, v in rows if o <= obs][-weeks:]
    cur = dict(rows).get(obs)
    if cur is None or len(win) < min_n:
        return None
    below = sum(1 for v in win if v < cur)
    eq = sum(1 for v in win if v == cur)
    return round((below + 0.5 * eq) / len(win) * 100, 1)


QUAD = {
    "up_up": ("① 추세 매수", "가격이 오르는데 투기자금도 더 샀어요 — 상승을 돈이 따라붙는 모습이에요."),
    "up_down": ("② 투기자금 없이 상승", "가격은 올랐지만 투기자금은 오히려 줄였어요 — 숏 커버(빌려 판 것 되사기)나 실수요가 끌어올린 상승일 수 있어 지속되는지 확인이 필요해요."),
    "down_up": ("③ 하락 중 저가 매수", "가격이 내리는데 투기자금은 더 샀어요 — 바닥을 찾는 매수일 수도, 성급한 매수일 수도 있어요."),
    "down_down": ("④ 매도 추세 확인", "가격이 내리고 투기자금도 빠져나갔어요 — 하락 흐름을 돈이 확인해 주는 모습이에요."),
    "flat": ("변화 거의 없음", "투기자금 포지션이 거의 그대로예요 (1주 변화가 전체 미결제약정의 0.5% 미만)."),
}


def quadrant(price_chg, net_chg, oi, oi_chg=None):
    if price_chg is None or net_chg is None or not oi:
        return None
    if abs(net_chg) < 0.005 * oi:
        k = "flat"
    else:
        k = ("up_" if price_chg >= 0 else "down_") + ("up" if net_chg > 0 else "down")
    lab, txt = QUAD[k]
    oi_note = None if oi_chg is None else ("미결제약정도 늘어 새 돈이 들어온 움직임이에요." if oi_chg > 0 else "미결제약정은 줄어 기존 포지션을 정리하는 움직임이에요.")
    return {"key": k, "label": lab, "text": txt, "oi_note": oi_note}


def inv_5y(rows, obs, years=5, min_years=3):
    """직전 5년 같은 주(ISO 주차) 평균·범위 — 올해는 넣지 않음 (EIA 방식)"""
    y, w, _ = _d(obs).isocalendar()
    by = {(_d(o).isocalendar()[0], _d(o).isocalendar()[1]): v for o, v in rows}
    vals = [by[(y - k, w)] for k in range(1, years + 1) if (y - k, w) in by]
    if len(vals) < min_years:
        return None
    return {"avg": sum(vals) / len(vals), "lo": min(vals), "hi": max(vals), "n": len(vals)}


def real_rows(px, cpi):
    """명목 월간 가격 → 오늘 물가 기준 실질가격 (CPI가 없는 달은 빼고, 추정으로 채우지 않음)"""
    c = dict((o[:7], v) for o, v in cpi)
    if not c:
        return []
    last = cpi[-1][1]
    return [(o, v * last / c[o[:7]]) for o, v in px if o[:7] in c]


def cycle_pos(real, months=240):
    """20년(240개월) 실질가격 중 지금 위치 · 10년 평균 대비 · 12개월 변화 — 표본 10년 미만이면 None"""
    win = [v for _, v in real[-months:]]
    if len(win) < 120:
        return None
    cur = win[-1]
    pct = round((sum(1 for v in win if v < cur) + 0.5 * sum(1 for v in win if v == cur)) / len(win) * 100, 1)
    avg10 = sum(win[-120:]) / 120
    prev = find_near(real, (_d(real[-1][0]) - timedelta(days=365)).isoformat(), tol=16)
    return {"obs": real[-1][0], "pct": pct, "vs10": (cur / avg10 - 1) * 100, "mom12": (cur / prev - 1) * 100 if prev else None,
            "n": len(win), "years": round(len(win) / 12)}


PHASE = {
    "trough": ("① 바닥권", "실질가격이 20년 중 낮은 곳에 있고 아직 내려가는 중이에요. 이런 시기에는 생산자가 투자를 줄여서, 수요가 돌아서면 다음 상승의 씨앗이 되기도 해요."),
    "recovery": ("② 회복기", "낮거나 중간 높이에서 오르기 시작했어요. 재고가 줄고 투기자금이 따라붙는지 확인하는 단계예요."),
    "boom": ("③ 과열·고점권", "실질가격이 20년 중 높은 곳에서 더 오르고 있어요. 높은 가격은 증산 투자와 수요 감소를 부르기 때문에, 이 단계는 오래가지 않는 경우가 많아요."),
    "downturn": ("④ 하강기", "중간 이상 높이에서 내려오는 중이에요. 늘어난 공급이나 줄어든 수요가 가격을 누르는 단계예요."),
    "mid": ("중간 지대", "20년 기준으로 높지도 낮지도 않고, 방향도 뚜렷하지 않아요."),
}


def phase(pct, mom12):
    """규칙 기반 '해석' — 실질가격 위치(20년 백분위)와 1년 방향만으로 나눔 (확정 사실이 아님)"""
    if pct is None or mom12 is None:
        return None
    k = ("boom" if pct >= 70 and mom12 > 0 else "downturn" if pct >= 40 and mom12 <= 0 else
         "trough" if pct <= 30 and mom12 <= 0 else "recovery" if mom12 > 0 else "mid")
    lab, txt = PHASE[k]
    return {"key": k, "label": lab, "text": txt}


def units_ok(code, units_text):
    exp = M.CONTRACTS[code]["units_text"].replace(" ", "").upper()
    return exp in (units_text or "").replace(" ", "").upper()


# ══ 수집 ══════════════════════════════════════════════════════════
def _get(url, params, tries=2):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i + 1 == tries:
                raise
            time.sleep(30)


def _cot_raw(full=True):
    # 처음엔 3년치, 그다음부터는 최근 10주만 (15분마다 도는 반복 실행에서 같은 3년치를 계속 받지 않게 — 최근 정정도 이 범위에서 잡힘)
    codes = [c for c in M.CONTRACTS]
    since = (date.today() - timedelta(days=365 * YEARS + 30 if full else 70)).isoformat()
    flds = ["report_date_as_yyyy_mm_dd", "cftc_contract_market_code", "contract_units", "open_interest_all"] + [f for p in M.COT_FIELDS.values() for f in p]

    def load():
        return _get(CFTC_URL, {"$select": ",".join(flds), "$limit": "50000",
                               "$where": f"cftc_contract_market_code in ({','.join(repr(c) for c in codes)}) AND report_date_as_yyyy_mm_dd >= '{since}'"})
    return sources._cached(f"radar_cot_{'full' if full else 'recent'}.json", 6 * 3600, load)


def _pk(obs, pub, seen_day):
    # 발표 예정일 직후 받았으면 '일정 기준', 과거 자료를 한꺼번에 받았으면 '추정 발표일'
    return "schedule" if (seen_day - _d(pub)).days <= 7 else "estimated"


def collect_cot(st, errs):
    have = {r["sid"].split(".")[1] for r in st["rows"] if r["sid"].startswith("cot.")}
    raw = _cot_raw(full=not set(M.CONTRACTS) <= have)
    today = datetime.now(timezone.utc).date()
    rows, warn = [], []
    for x in raw:
        code, obs = x["cftc_contract_market_code"], x["report_date_as_yyyy_mm_dd"][:10]
        if code not in M.CONTRACTS:
            continue
        if not units_ok(code, x.get("contract_units")) and code not in warn:
            warn.append(code)
        pub = (_d(obs) + timedelta(days=3)).isoformat()          # 화요일 기준 → 금요일 발표
        base = {"obs": obs, "pub": pub, "pk": _pk(obs, pub, today), "unit": "contracts", "src": "cftc"}

        def num(f):
            try:
                return int(float(x[f]))
            except (KeyError, TypeError, ValueError):
                return None
        rows.append(dict(base, sid=f"cot.{code}.oi", v=num("open_interest_all")))
        for g, (fl, fs) in M.COT_FIELDS.items():
            rows.append(dict(base, sid=f"cot.{code}.{g}_l", v=num(fl)))
            rows.append(dict(base, sid=f"cot.{code}.{g}_s", v=num(fs)))
    for c in warn:
        errs.append(f"CFTC {c} 계약 단위 문구가 기준표와 달라요 — 확인 필요")
    return RS.upsert(st, rows)


def collect_eia(st, errs):
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        errs.append("EIA_API_KEY 없음 — 재고 자료를 받지 못했어요")
        return 0, 0
    today = datetime.now(timezone.utc).date()
    add = rev = 0
    for kind, e in M.EIA_INV.items():
        def load(e=e):
            j = _get(f"https://api.eia.gov/v2/{e['route']}/data/", {"api_key": key, "frequency": "weekly", "data[0]": "value", "facets[series][]": e["series"],
                                                                     "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "420"})
            return [[r["period"], float(r["value"])] for r in j["response"]["data"] if r.get("value") not in (None, "")]
        try:
            data = sources._cached(f"radar_eia_{kind}.json", 3 * 3600, load)
        except Exception as ex:
            errs.append(f"EIA {kind}: {str(ex)[:80]}")
            continue
        lag = 5 if kind == "crude" else 6                            # 금요일 기준 → 수요일(원유)·목요일(가스) 발표
        rows = [{"sid": f"inv.{kind}", "obs": o, "v": v, "unit": e["unit"], "pub": (pub := (_d(o) + timedelta(days=lag)).isoformat()),
                 "pk": _pk(o, pub, today), "src": "eia"} for o, v in data]
        a, r = RS.upsert(st, rows)
        add, rev = add + a, rev + r
    return add, rev


def fred_jobs():
    since = (date.today() - timedelta(days=365 * YEARS + 30)).isoformat()
    long_ = f"{date.today().year - M.CYCLE_YEARS - 1}-01-01"
    six = (date.today() - timedelta(days=365 * 6)).isoformat()
    jobs = {c["price"][1]: since for c in M.COMMODITIES if c["price"]}
    jobs.update({c["cyc"]: long_ for c in M.COMMODITIES if c.get("cyc")})
    jobs.update({M.MACRO["cpi"][0]: long_, M.MACRO["usd"][0]: six, M.MACRO["real"][0]: six})
    return jobs


def collect_fred(st, errs):
    today = datetime.now(timezone.utc).date()
    add = rev = 0
    for s, since in sorted(fred_jobs().items()):
        monthly = s.startswith("P") or s == "CPIAUCSL"
        try:
            data = markets.fred(s, start=since)
        except Exception as ex:
            errs.append(f"FRED {s}: {str(ex)[:80]}")
            continue
        rows = [{"sid": f"px.{s}", "obs": o, "v": v, "unit": "USD", "pub": (pub := (_d(o) + timedelta(days=45 if monthly else 7)).isoformat()),
                 "pk": "estimated" if (today - _d(pub)).days > 7 else "seen", "src": "fred_imf" if s.startswith("P") else "fred"} for o, v in data]
        a, r = RS.upsert(st, rows)
        add, rev = add + a, rev + r
    return add, rev


def _yahoo_daily(sym):
    """참고 등락률용 — 파일로 저장하지 않음"""
    c = markets.yahoo_chart(sym, "5y", "1d")
    off = c.get("gmtoffset") or 0
    return [(datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(), v) for t, v in c["points"] if v is not None]


# ══ 화면용 요약 ════════════════════════════════════════════════════
def _today_et():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def _late(next_pub):
    """다음 발표 예정일(미국 동부)보다 하루 넘게 늦었으면 늦은 일수 — 공휴일이면 하루 밀리는 게 정상이라 하루 여유"""
    days = (_today_et() - _d(next_pub)).days
    return days if days >= 1 else None


def _stale(obs, kind):
    if not obs:
        return None
    days = (date.today() - _d(obs)).days
    return days if days > M.STALE_DAYS[kind] else None


FRED_S = "https://fred.stlouisfed.org/series/{}"


def _sources(c):
    """원자재별 공식 출처 — 화면의 모든 숫자 옆 링크"""
    out = {}
    if c["price"]:
        s = c["price"][1]
        orig = ({"label": "IMF 1차 상품 가격 (원자료)", "url": "https://www.imf.org/en/Research/commodity-prices"} if s.startswith("P") else
                {"label": "EIA 천연가스 현물 (원자료)", "url": "https://www.eia.gov/dnav/ng/hist/rngwhhdd.htm"} if s == "DHHNGSP" else
                {"label": "EIA 원유 현물 (원자료)", "url": "https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm"})
        out["price"] = [{"label": f"FRED {s}", "url": FRED_S.format(s)}, orig]
    if c["move"]:
        src, s = c["move"]
        out["move"] = ([{"label": f"FRED {s}", "url": FRED_S.format(s)}] if src == "fred" else
                       [{"label": f"Yahoo {s} (참고)", "url": M.YAHOO_Q.format(s.replace("=", "%3D"))}])
    if c["cot"]:
        out["cot"] = [{"label": "CFTC 주간 보고서 (원문)", "url": f"https://www.cftc.gov/dea/futures/{M.COT_PAGE[c['cot']]}.htm"},
                      {"label": "CFTC 공개 데이터셋", "url": M.COT_DATASET}]
    if c["inv"]:
        e = M.EIA_INV[c["inv"]]
        out["inv"] = [{"label": f"EIA {e['series']}", "url": e["url"]}, {"label": e["report"][0], "url": e["report"][1]}]
    if c.get("cyc"):
        out["cyc"] = [{"label": f"FRED {c['cyc']} (IMF 월평균)", "url": FRED_S.format(c["cyc"])}, {"label": "FRED CPIAUCSL (물가 보정)", "url": FRED_S.format("CPIAUCSL")}]
    return out


def macro(st):
    """사이클 공통 지표 — 달러(원자재는 달러로 거래돼 달러가 강하면 다른 나라에선 비싸져 수요가 줄어요) · 실질금리(금·은의 기회비용)"""
    out = {}
    u = RS.series(st, f"px.{M.MACRO['usd'][0]}")
    if u:
        o, v = u[-1]
        p3 = find_before(u, (_d(o) - timedelta(days=91)).isoformat(), back=7)
        win = [x for d_, x in u if d_ >= (_d(o) - timedelta(days=365 * 5)).isoformat()]
        out["usd"] = {"name": M.MACRO["usd"][1], "obs": o, "v": v, "c3m": (v / p3 - 1) * 100 if p3 else None,
                      "pct5": round(sum(1 for x in win if x < v) / len(win) * 100, 1) if len(win) > 900 else None,
                      "src": [{"label": "FRED DTWEXBGS", "url": FRED_S.format("DTWEXBGS")}, {"label": "연준 H.10 (원자료)", "url": "https://www.federalreserve.gov/releases/h10/"}]}
    r = RS.series(st, f"px.{M.MACRO['real'][0]}")
    if r:
        o, v = r[-1]
        p1 = find_before(r, (_d(o) - timedelta(days=365)).isoformat(), back=7)
        out["real"] = {"name": M.MACRO["real"][1], "obs": o, "v": v, "c1y": (v - p1) * 100 if p1 is not None else None,
                       "src": [{"label": "FRED DFII10", "url": FRED_S.format("DFII10")}]}
    return out


def _cycle(c, st, out, mac):
    """사이클 4층: 장기 실질가격 위치 · 재고 · 투기자금 쏠림 · 거시(달러·실질금리) — CAPEX(공급 투자)는 3차"""
    cy = {"layers": [], "counter": []}
    if c.get("cyc"):
        real = real_rows(RS.series(st, f"px.{c['cyc']}"), RS.series(st, f"px.{M.MACRO['cpi'][0]}"))
        pos = cycle_pos(real)
        if pos:
            cy["long"] = dict(pos, phase=phase(pos["pct"], pos["mom12"]))
            cy["layers"].append({"k": "장기 가격 위치", "v": f"{pos['years']}년 실질가격 중 {pos['pct']:.0f}% 높이",
                                 "st": "warn" if pos["pct"] >= 80 else "ok" if pos["pct"] <= 30 else "na", "d": pos["obs"], "src": "cyc",
                                 "note": f"10년 평균보다 {pos['vs10']:+.0f}%" + (f" · 1년 {pos['mom12']:+.0f}%" if pos["mom12"] is not None else "")})
    inv = out.get("inv")
    if inv and inv.get("vs5") is not None:
        tight = inv["lo5"] is not None and inv["v"] < inv["lo5"]
        loose = inv["hi5"] is not None and inv["v"] > inv["hi5"]
        cy["layers"].append({"k": "재고", "v": "5년 평균과 비슷" if abs(inv["vs5"]) < 0.5 else f"5년 평균보다 {inv['vs5']:+.1f}%", "st": "warn" if tight else "ok" if loose else "na", "d": inv["obs"], "src": "inv",
                             "note": "5년 범위보다 적음 (빠듯)" if tight else "5년 범위보다 많음 (넉넉)" if loose else "5년 범위 안"})
    cot = out.get("cot")
    pt = cot["groups"]["mm"]["pctile"] if cot and c["status"] == "ok" else None
    if pt is not None:
        cy["layers"].append({"k": "투기자금 쏠림", "v": f"3년 중 {pt:.0f}% 높이", "st": "warn" if pt >= 90 or pt <= 10 else "na", "d": cot["obs"], "src": "cot",
                             "note": "매수 쏠림 극단" if pt >= 90 else "매도·비관 극단" if pt <= 10 else "극단 아님"})
    u = mac.get("usd")
    if u and u.get("c3m") is not None:
        cy["layers"].append({"k": "달러", "v": f"3개월 {u['c3m']:+.1f}%", "st": "warn" if u["c3m"] >= 3 else "ok" if u["c3m"] <= -3 else "na", "d": u["obs"], "src": "usd",
                             "note": "달러 강세 — 원자재에 역풍" if u["c3m"] >= 3 else "달러 약세 — 원자재에 순풍" if u["c3m"] <= -3 else "큰 변화 없음"})
    rr = mac.get("real")
    if c["group"] == "precious" and rr and rr.get("c1y") is not None:
        cy["layers"].append({"k": "실질금리", "v": f"{rr['v']:.2f}% (1년 {rr['c1y']:+.0f}bp)", "st": "warn" if rr["c1y"] >= 50 else "ok" if rr["c1y"] <= -50 else "na",
                             "d": rr["obs"], "src": "real",
                             "note": "금·은을 들고 있는 기회비용이 커짐 (역풍)" if rr["c1y"] >= 50 else "기회비용이 줄어듦 (순풍)" if rr["c1y"] <= -50 else "큰 변화 없음"})
    cy["layers"].append({"k": "공급 투자(CAPEX)", "v": "준비 중 (3차)", "st": "na", "d": None, "src": None, "note": "생산기업 설비투자 추이 — SEC 공시로 3차 개발 예정"})
    ph = ((cy.get("long") or {}).get("phase") or {}).get("key")
    if ph in ("boom", "recovery") and inv and inv.get("vs5") is not None and inv["vs5"] > 5:
        cy["counter"].append("가격은 오름세인데 재고는 5년 평균보다 많아요 — 실물이 받쳐 주지 않는 상승일 수 있어요.")
    if ph in ("trough", "downturn") and inv and inv.get("vs5") is not None and inv["vs5"] < -5:
        cy["counter"].append("가격은 약세인데 재고는 5년 평균보다 적어요 — 실물은 빠듯해 반등 여지가 있어요.")
    if pt is not None and pt >= 90:
        cy["counter"].append("투기자금 매수가 3년 중 극단이라, 새로 살 사람이 적어 되돌림 위험이 커요.")
    elif pt is not None and pt <= 10:
        cy["counter"].append("투기자금 비관이 3년 중 극단이라, 조금만 좋아져도 되사기(숏 커버)로 튈 수 있어요.")
    if not c.get("cyc"):
        cy["missing"] = "장기 가격 사이클: 이 원자재는 공식 무료 장기 가격 자료(IMF·EIA)가 없어 판단하지 않았어요."
    return cy


def _item(c, st, ymove, mac=None):
    out = {k: c.get(k) for k in ("id", "name", "group", "status", "why", "alt", "see")}
    out["src"] = _sources(c)
    out["group_kr"] = M.GROUPS[c["group"]]
    warn = []
    # 가격 숫자 (공식)
    px_rows = []
    if c["price"]:
        _, s, unit, freq = c["price"]
        px_rows = RS.series(st, f"px.{s}")
        if px_rows:
            o, v = px_rows[-1]
            kind = "fred_month" if s.startswith("P") else "fred_day"
            out["price"] = {"v": v, "unit": unit, "obs": o, "freq": freq, "series": s, "url": f"https://fred.stlouisfed.org/series/{s}", "stale": _stale(o, kind)}
            if out["price"]["stale"]:
                warn.append(f"가격 자료가 {out['price']['stale']}일 지났어요")
    # 이번 주 방향 (공식 일간 또는 Yahoo 등락률)
    mv_rows = []
    if c["move"]:
        src, s = c["move"]
        mv_rows = px_rows if src == "fred" else ymove.get(s) or []
        if mv_rows:
            o, v = mv_rows[-1]
            p1, p4 = find_before(mv_rows, (_d(o) - timedelta(days=7)).isoformat()), find_before(mv_rows, (_d(o) - timedelta(days=28)).isoformat())
            out["move"] = {"obs": o, "w1": (v / p1 - 1) * 100 if p1 else None, "w4": (v / p4 - 1) * 100 if p4 else None,
                           "src": "공식 (EIA 현물, FRED)" if src == "fred" else "참고 (Yahoo 선물 등락률)", "ref": src == "yahoo",
                           "stale": _stale(o, "fred_day" if src == "fred" else "yahoo")}
    # COT
    code = c["cot"]
    if code:
        g = {}
        oi = RS.series(st, f"cot.{code}.oi")
        if oi:
            obs = oi[-1][0]
            oi_now = oi[-1][1]
            for k in M.COT_FIELDS:
                L, S_ = RS.series(st, f"cot.{code}.{k}_l"), RS.series(st, f"cot.{code}.{k}_s")
                net = net_rows(L, S_)
                cur = dict(net).get(obs)
                g[k] = {"name": M.GROUP_KR[k], "long": dict(L).get(obs), "short": dict(S_).get(obs), "net": cur,
                        "c1": change(net, obs, 7), "c4": change(net, obs, 28), "c13": change(net, obs, 91),
                        "pct_oi": (cur / oi_now * 100) if cur is not None and oi_now else None, "pctile": percentile(net, obs)}
            mm = net_rows(RS.series(st, f"cot.{code}.mm_l"), RS.series(st, f"cot.{code}.mm_s"))
            meta = RS.meta(st, f"cot.{code}.oi")
            ct = M.CONTRACTS[code]
            out["cot"] = {"code": code, "exch": ct["exch"], "contract": ct["name"], "size": ct["size"], "unit": ct["unit"],
                          "obs": obs, "pub": meta["pub"], "seen": meta["seen"], "oi": oi_now, "oi_c1": change(oi, obs, 7), "groups": g,
                          "next": (_d(meta["pub"]) + timedelta(days=7)).isoformat()}
            out["cot"]["stale"] = _late(out["cot"]["next"])
            if out["cot"]["stale"]:
                warn.append(f"CFTC가 발표 예정일({out['cot']['next'][5:]})보다 {out['cot']['stale']}일 늦어요 — 공식 지연일 수 있어 값을 채우지 않았어요")
            # 차트: 투기자금 순포지션 + 같은 주 화요일 가격 (Yahoo는 3년 전=100 지수로만)
            hist = mm[-156:]
            ph = []
            if mv_rows:
                raw = [find_before(mv_rows, o) for o, _ in hist]
                if c["move"][0] == "yahoo":
                    b = next((x for x in raw if x), None)
                    raw = [round(x / b * 100, 1) if x and b else None for x in raw]
                ph = raw
            out["chart"] = {"obs": [o for o, _ in hist], "mm": [v for _, v in hist], "px": ph,
                            "px_kind": None if not ph else ("index" if c["move"][0] == "yahoo" else "price")}
            # 가격 × 포지션 사분면 — 이번 주 + 지난 13주 궤적
            if mv_rows:
                traj = []
                for o, _ in mm[-14:]:
                    p0, p1_ = find_before(mv_rows, o), find_before(mv_rows, (_d(o) - timedelta(days=7)).isoformat())
                    nc, oo = change(mm, o, 7), dict(oi).get(o)
                    if p0 and p1_ and nc is not None and oo:
                        traj.append({"obs": o, "pc": round((p0 / p1_ - 1) * 100, 2), "nc": round(nc / oo * 100, 2)})
                pc = traj[-1]["pc"] if traj and traj[-1]["obs"] == obs else None
                q = quadrant(pc, g["mm"]["c1"], oi_now, out["cot"]["oi_c1"])
                if q:
                    pt = g["mm"]["pctile"]
                    q["extreme"] = ("투기자금 순매수가 3년 중 상위 10% 안이에요 — 이미 많이 쏠려 있어 반대로 움직일 위험이 커요." if pt is not None and pt >= 90 else
                                    "투기자금 순매수가 3년 중 하위 10% 안이에요 — 비관이 극단이라 반대로 튈 위험이 있어요." if pt is not None and pt <= 10 else None)
                out["quad"] = q
                out["traj"] = traj
    # 재고
    if c["inv"]:
        rows = RS.series(st, f"inv.{c['inv']}")
        if rows:
            o, v = rows[-1]
            e = M.EIA_INV[c["inv"]]
            meta = RS.meta(st, f"inv.{c['inv']}")
            f5 = inv_5y(rows, o)
            prev = find_near(rows, (_d(o) - timedelta(days=7)).isoformat())
            band = []
            for oo, vv in rows[-53:]:
                b5 = inv_5y(rows, oo)
                band.append([oo, vv, b5 and round(b5["avg"]), b5 and b5["lo"], b5 and b5["hi"]])
            out["inv"] = {"name": e["name"], "unit": e["unit"], "obs": o, "v": v, "pub": meta["pub"], "seen": meta["seen"], "pub_rule": e["pub"],
                          "w1": None if prev is None else v - prev, "avg5": f5 and f5["avg"], "lo5": f5 and f5["lo"], "hi5": f5 and f5["hi"],
                          "vs5": (v / f5["avg"] - 1) * 100 if f5 else None, "band": band,
                          "next": (_d(meta["pub"]) + timedelta(days=7)).isoformat()}
            out["inv"]["stale"] = _late(out["inv"]["next"])
            if out["inv"]["stale"]:
                warn.append(f"EIA가 발표 예정일({out['inv']['next'][5:]})보다 {out['inv']['stale']}일 늦어요 — 공식 지연일 수 있어 값을 채우지 않았어요")
    out["warn"] = warn
    out["line"] = (out.get("quad") or {}).get("label")
    out["cycle"] = _cycle(c, st, out, mac or {})
    return out


# ══ 원자재 보드 종합 해설 (공식 숫자로만 쓰는 서술문 · 문단마다 출처) ══════
def _jo(word, a, b):
    """받침에 맞는 조사 — 마지막 한글 글자 기준 (은/는 · 이에요/예요 · 이/가)"""
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return a if (ord(ch) - 0xAC00) % 28 else b
    return b


def _chg(v, unit="계약"):
    return "그대로였어요" if not v else f"{abs(v):,}{unit} {'늘었어요' if v > 0 else '줄었어요'}"


def _vs(v, base="5년 평균"):
    return f"{base}과 비슷해요" if v is None or abs(v) < 0.5 else f"{base}보다 {abs(v):.1f}% {'많아요' if v > 0 else '적어요'}"


def _p(v, d=1):
    return "—" if v is None else f"{v:+.{d}f}%"


def _ptxt(p):
    return ("표본 부족" if p is None else "3년 중 가장 높은 쪽(쏠림 극단)" if p >= 90 else "3년 중 높은 편" if p >= 70 else
            "3년 중 가장 낮은 쪽(비관 극단)" if p <= 10 else "3년 중 낮은 편" if p <= 30 else "3년 중 중간")


def _md(s):
    return f"{int(s[5:7])}월 {int(s[8:10])}일" if s else "—"


def _srcs(*lists):
    seen, out = set(), []
    for L in lists:
        for x in L or []:
            if x["url"] not in seen:
                seen.add(x["url"])
                out.append(x)
    return out


def _tight(inv):
    """재고가 5년 같은 주와 비교해 빠듯(-1) · 넉넉(+1) · 보통(0) · 모름(None)"""
    if not inv or inv.get("vs5") is None:
        return None
    if (inv["lo5"] is not None and inv["v"] < inv["lo5"]) or inv["vs5"] <= -5:
        return -1
    if (inv["hi5"] is not None and inv["v"] > inv["hi5"]) or inv["vs5"] >= 5:
        return 1
    return 0


def _take(it):
    """원자재 하나의 '한 줄 해석' — 서로 다른 자료가 같은/다른 말을 하는지 먼저 보고, 없으면 신호 뜻을 쓴다"""
    c = it.get("cot") if it["status"] == "ok" else None
    mm = c and c["groups"]["mm"]
    pct, c4 = (mm or {}).get("pctile"), (mm or {}).get("c4")
    ti = _tight(it.get("inv"))
    lg = (it.get("cycle") or {}).get("long") or {}
    ph = (lg.get("phase") or {}).get("key")
    if ti == -1 and c4 is not None and c4 < 0:
        return "실물 재고는 빠듯한데 투기자금은 빠지는 중 — 가격이 더 밀려도 재고가 버팀목이 될 수 있어요."
    if ti == 1 and c4 is not None and c4 > 0:
        return "재고가 넉넉한데 투기자금이 들어오는 중 — 실물 뒷받침이 약한 상승일 수 있어요."
    if pct is not None and pct <= 10:
        return "투기자금 비관이 3년 중 극단 — 작은 호재에도 되사기(숏 커버)로 크게 튈 수 있어요."
    if pct is not None and pct >= 90:
        return "투기자금 낙관이 3년 중 극단 — 새로 살 사람이 적어 작은 악재에도 밀릴 수 있어요."
    if ph == "boom":
        return "20년 기준 비싼 구간에서 더 오르는 중 — 높은 가격은 증산을 불러 오래가지 않는 경우가 많아요."
    if ph == "trough":
        return "20년 기준 싼 구간에서 아직 내리는 중 — 재고 감소·투기자금 유입 같은 바닥 신호를 기다리는 자리예요."
    if it.get("quad"):
        return it["quad"]["text"]
    if ph:
        return lg["phase"]["text"]
    return "이번 주에는 해석할 만큼의 자료가 모이지 않았어요."


def _facts(it):
    """원자재 하나의 요점 — [아이콘, 항목, 내용] 목록 (화면에서 줄마다 보여 줌)"""
    out = []
    p, m, c, inv, cy = it.get("price"), it.get("move"), it.get("cot"), it.get("inv"), it.get("cycle") or {}
    if p and not p["freq"].startswith("월평균"):
        out.append(["💵", "가격", f"{p['v']:,.2f} {p['unit']} ({_md(p['obs'])}) · 1주 {_p(m and m['w1'])}"])
    elif p:
        out.append(["💵", "가격", f"{int(p['obs'][5:7])}월 평균 {p['v']:,.0f} {p['unit']}" + (f" · 이번 주 선물 {_p(m['w1'])} (참고)" if m else "")])
    elif m:
        out.append(["💵", "가격", f"공식 무료 가격 없음 · 선물 등락률 1주 {_p(m['w1'])}, 4주 {_p(m['w4'])} (참고)"])
    if c and it["status"] == "ok":
        mm = c["groups"]["mm"]
        side = f"{mm['net']:,}계약 순매수" if mm["net"] >= 0 else f"{-mm['net']:,}계약 순매도"
        t = f"{side} — {_ptxt(mm['pctile'])}"
        if mm.get("c4"):
            t += f" · 4주 동안 순매수 {abs(mm['c4']):,}계약 {'증가' if mm['c4'] > 0 else '감소'}"
        out.append(["🧑‍💼", "투기자금", t])
        if it.get("quad"):
            out.append(["🔀", "이번 주 신호", f"「{it['quad']['label']}」"])
    elif it["status"] == "check":
        out.append(["🧑‍💼", "투기자금", "대표 계약 문제로 숫자를 빼고 봤어요"])
    if inv and inv.get("vs5") is not None:
        ti = _tight(inv)
        out.append(["🛢️", "재고", f"{inv['v']:,.0f} {inv['unit']} — {_vs(inv['vs5'])}" + (" (빠듯)" if ti == -1 else " (넉넉)" if ti == 1 else "")])
    lg = cy.get("long")
    if lg and lg.get("phase"):
        out.append(["🔄", "20년 사이클", f"물가 뺀 가격이 20년 중 아래에서 {lg['pct']:.0f}% 높이 → 「{lg['phase']['label']}」"])
    return out


def summary(items, mac):
    """보드 맨 위 '이번 주 원자재 종합 해설' — 핵심 몇 줄 + 원자재별 요점 + 공통 바람 + 반대 근거 + 다음 일정.
    표·사이클 지도 같은 도표는 화면(radar.js)이 items 로 직접 그린다."""
    cot_obs = next((i["cot"]["obs"] for i in items if i.get("cot")), None)
    inv_obs = max((i["inv"]["obs"] for i in items if i.get("inv")), default=None)
    ok = [i for i in items if i.get("cot") and i["status"] == "ok"]
    pc = lambda i: i["cot"]["groups"]["mm"]["pctile"]
    hi = [i["name"] for i in ok if pc(i) is not None and pc(i) >= 90]
    lo = [i["name"] for i in ok if pc(i) is not None and pc(i) <= 10]
    qs = {}
    for i in ok:
        if i.get("quad"):
            qs.setdefault(i["quad"]["key"], []).append(i)
    ph = {}
    for i in items:
        lg = (i.get("cycle") or {}).get("long")
        if lg and lg.get("phase"):
            ph.setdefault(lg["phase"]["key"], []).append(i["name"])
    names = lambda L: ", ".join(L)
    # ① 핵심 몇 줄
    key = []
    if qs:
        k, L = max(qs.items(), key=lambda kv: (len(kv[1]), kv[0] != "flat"))
        if k == "flat":
            key.append(f"투기자금이 거의 움직이지 않은 원자재가 {len(L)}개로 가장 많아요 — 이번 주는 큰 자금 이동이 없었어요.")
        else:
            key.append(f"이번 주 가장 많은 신호는 「{L[0]['quad']['label']}」({len(L)}개: {names(i['name'] for i in L)})예요 — {L[0]['quad']['text'].split(' — ')[0]}.")
    if hi or lo:
        key.append("투기자금이 3년 기준 한쪽 끝에 몰린 원자재: " + " / ".join(x for x in [f"낙관 극단 {names(hi)}" if hi else "", f"비관 극단 {names(lo)}" if lo else ""] if x) +
                   " — 쏠림이 극단이면 작은 소식에도 반대로 크게 움직일 수 있어요.")
    else:
        key.append("투기자금이 3년 기준 극단(상위·하위 10%)까지 몰린 원자재는 없어요.")
    if ph:
        key.append("20년 실질가격 사이클: " + " / ".join(f"{PHASE[k][0]} {names(v)}" for k, v in sorted(ph.items(), key=lambda kv: PHASE[kv[0]][0])) + ".")
    u, r = mac.get("usd"), mac.get("real")
    wind = []
    if u and u.get("c3m") is not None:
        d = "강해져 원자재 전반에 역풍" if u["c3m"] >= 3 else "약해져 원자재 전반에 순풍" if u["c3m"] <= -3 else "큰 방향이 없어 영향이 작아요"
        wind.append({"k": "달러 (연준 달러지수)", "v": f"{u['v']:.1f}", "chg": f"3개월 {_p(u['c3m'])}", "d": u["obs"], "say": f"달러가 {d}" + ("" if d.endswith("요") else "이에요"),
                     "why": "원자재는 대부분 달러로 거래돼서, 달러가 강해지면 다른 나라에는 비싸져 수요가 줄기 쉬워요. (DXY는 민간 상표 지수라 공식 자료인 연준 달러지수로 봐요.)", "src": u["src"]})
    if r and r.get("c1y") is not None:
        d = "올라 금·은에 역풍이에요" if r["c1y"] >= 25 else "내려 금·은에 순풍이에요" if r["c1y"] <= -25 else "큰 변화가 없어요"
        wind.append({"k": "미국 10년 실질금리 (TIPS)", "v": f"{r['v']:.2f}%", "chg": f"1년 {r['c1y']:+.0f}bp", "d": r["obs"], "say": f"실질금리가 {d}",
                     "why": "금·은은 이자가 나오지 않아서, 물가를 뺀 금리가 오르면 들고 있는 비용(기회비용)이 커져요.", "src": r["src"]})
    if wind:
        key.append(" · ".join(w["say"] for w in wind) + ".")
    # ② 그룹별 요점
    intro = {"energy": "경기·계절(난방·운전 수요)·산유국 공급 결정에 가장 민감해요.",
             "precious": "이자가 없는 자산이라 실질금리·달러에 크게 반응하고, 불안할 때 피난처가 돼요.",
             "industrial": "공장·건설·전력망에 쓰여서 세계 경기, 특히 중국 제조업의 체온계예요.",
             "agri": "날씨와 수확 전망에 따라 계절적으로 크게 움직이고, 투기자금이 자주 극단까지 가요."}
    groups = []
    for grp, name in M.GROUPS.items():
        its = [i for i in items if i["group"] == grp]
        rows = [{"id": i["id"], "name": i["name"], "take": _take(i), "facts": _facts(i)} for i in its]
        srcs = _srcs(*[s for i in its for s in (i.get("src") or {}).values()])
        groups.append({"id": grp, "h": name, "intro": intro[grp], "rows": rows, "src": srcs})
    # ③ 반대 근거 · 다음 일정
    tk = {i["id"]: _take(i) for i in items}
    dup = lambda i, x: ("투기자금" in x and "투기자금" in tk[i["id"]][:12]) or ("재고" in x and "재고" in tk[i["id"]][:12])   # 한 줄 해석에서 이미 말한 것
    contra = [{"name": i["name"], "t": x} for i in items for x in (i.get("cycle") or {}).get("counter", []) if not dup(i, x)]
    nxt_c = next((i["cot"]["next"] for i in items if i.get("cot")), None)
    nxt = ([{"k": "CFTC 투기자금 포지션", "d": nxt_c, "note": "미국 금요일 오후 발표 → 한국 토요일 새벽"}] if nxt_c else []) + \
          [{"k": i["inv"]["name"], "d": i["inv"]["next"], "note": i["inv"].get("pub_rule") or ""} for i in items if i.get("inv")] + \
          [{"k": "IMF 월평균 가격", "d": None, "note": "매월 초에 전달 평균값 발표"}]
    basis = {"cot": cot_obs, "inv": inv_obs}
    S = {"key": key, "groups": groups, "wind": wind, "contra": contra, "next": nxt, "basis": basis,
         "src": [{"label": "CFTC COT", "url": M.SOURCES["cftc"]["url"]}, {"label": "EIA 주간 재고", "url": M.SOURCES["eia"]["url"]}, {"label": "FRED", "url": "https://fred.stlouisfed.org/"},
                 {"label": "CFTC 발표 일정", "url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm"},
                 {"label": "EIA 발표 일정", "url": "https://www.eia.gov/petroleum/supply/weekly/schedule.php"}]}
    S["chars"] = sum(len(x) for x in key) + sum(len(g["intro"]) + sum(len(r["take"]) + sum(len(f[2]) for f in r["facts"]) for r in g["rows"]) for g in groups) + \
        sum(len(w["say"]) + len(w["why"]) for w in wind) + sum(len(c["t"]) for c in contra)
    return S


def build(errs=None):
    errs = errs if errs is not None else []
    t0 = time.time()
    st = RS.load("radar")
    log = {}
    for name, f in (("cot", collect_cot), ("eia", collect_eia), ("fred", collect_fred)):
        try:
            log[name] = f(st, errs)
        except Exception as ex:
            errs.append(f"원자재 {name}: {str(ex)[:100]}")
    RS.save("radar", st)
    ymove = {}
    for c in M.COMMODITIES:
        if c["move"] and c["move"][0] == "yahoo":
            try:
                ymove[c["move"][1]] = _yahoo_daily(c["move"][1])
            except Exception as ex:
                errs.append(f"참고 등락률 {c['move'][1]}: {str(ex)[:60]}")
    mac = macro(st)
    items = []
    for c in M.COMMODITIES:
        try:
            items.append(_item(c, st, ymove, mac))
        except Exception as ex:
            errs.append(f"원자재 {c['id']}: {str(ex)[:100]}")
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%MZ")
    revs = [{"sid": r["sid"], "obs": r["obs"], "prev": r.get("prev"), "v": r["v"], "seen": r["seen"]} for r in RS.revisions(st, since)][-40:]
    print(f"원자재 레이더 ({time.time() - t0:.0f}초) · 추가/정정 {log} · 오류 {len(errs)}개")
    return {"schema": 1, "built_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes"),
            "groups": M.GROUPS, "items": items, "macro": mac, "summary": summary(items, mac), "revisions": revs, "errors": errs, "sources": M.SOURCES,
            "store": {"rows": len(st["rows"])}}
