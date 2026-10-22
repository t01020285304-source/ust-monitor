"""국채 위기 모니터용 — 원본(가격결정자_리서치/plumbing.py)에서 단기채(Bill) 비중 추이 함수만 옮김"""
import json
from datetime import date, datetime, timedelta

import requests

import markets
import sources


# ── manual.py 에서 옮긴 카드·시계열 도우미 ──
def _f(sid, days=800):
    return markets.fred(sid, (date.today() - timedelta(days=days)).isoformat())


def _ago(rows, days):
    """days 일 전(이하)의 값"""
    if not rows:
        return None
    cut = (datetime.fromisoformat(rows[-1][0]) - timedelta(days=days)).date().isoformat()
    prev = [r for r in rows if r[0] <= cut]
    return prev[-1][1] if prev else None


def _y(sym, rng="1y"):
    c = markets.yahoo_chart(sym, rng, "1d")
    off = c.get("gmtoffset") or 0
    return [[datetime.utcfromtimestamp(t + off).date().isoformat(), v] for t, v in c["points"]]


def card(key, name, state, reading, value=None, unit="", rows=None, why=None, src=None, basis=None, rule_note=None, action=None):
    return {"key": key, "name": name, "state": state, "reading": reading, "value": value, "unit": unit, "rows": (rows or [])[-260:],
            "why": [w for w in (why or []) if w], "src": src or [], "basis": basis or [], "rule_note": rule_note, "action": action}



UA = {"User-Agent": "MangoResearch/1.0 (personal research)"}


FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


FU = markets.fred_url


def bills():
    def load():
        r = requests.get(FD + "/v1/debt/mspd/mspd_table_1", headers=UA, timeout=30,
                         params={"sort": "-record_date", "page[size]": "2000", "filter": f"record_date:gte:{(date.today() - timedelta(days=365 * 4)).isoformat()}"})
        r.raise_for_status()
        by = {}
        for x in r.json()["data"]:
            if x.get("security_type_desc") != "Marketable":
                continue
            d = x["record_date"]
            v = float(x["total_mil_amt"]) if x.get("total_mil_amt") not in (None, "null") else 0
            k = x["security_class_desc"]
            by.setdefault(d, {})[k] = v
        out = []
        for d in sorted(by):
            m = by[d]
            tot = m.get("Total Marketable") or sum(v for k, v in m.items() if k != "Total Marketable")
            if m.get("Bills") and tot:
                out.append([d, round(m["Bills"] / tot * 100, 2)])
        return out
    s = sources._cached("mspd_bills.json", 24 * 3600, load)
    v = s[-1][1]
    ch = v - (_ago(s, 365) or v)
    wb = _f("WSHOBL", 500)
    wch = wb[-1][1] - (_ago(wb, 91) or wb[-1][1])
    st = "경계" if (v >= 22 and ch >= 1) or (ch >= 2) else "정상"
    rd = ("단기물 비중이 구조적으로 오르는 중 — '돈이 필요한 것보다 장기금리가 더 무서운 상태'" if st == "경계" else "단기물 비중 안정")
    return card("bills", "국채 중 단기물(T-bill) 비중", st, rd, v, "%", s,
                [f"시장성 국채 중 단기물 {v:.1f}% · 1년 {ch:+.1f}%p", f"연준의 단기물 보유 3개월 {wch / 1000:+,.0f}B {'(사들이는 중)' if wch > 0 else ''}",
                 "원문 인용: TBAC 시나리오상 단기물 비중 21.7%"],
                [{"label": "미 재무부 MSPD", "url": "https://fiscaldata.treasury.gov/datasets/monthly-statement-public-debt/"}, {"label": "FRED WSHOBL", "url": FU("WSHOBL")}],
                ["사고흐름 칼럼 275 「미국 재무부가 단기물 발행을 늘릴 때」", "칼럼 320 「국채와 미국의 진정한 힘」"],
                rule_note="22% 이상이면서 1년 +1%p, 또는 1년 +2%p 이상 = 경계 (사이트 설정)",
                action="네 가지가 함께 움직이면 '장기금리 통제와 재정 스트레스 동시 확대': ① 쿠폰 증액 없이 단기물만 증가 ② 단기물 비중 구조적 상승 ③ 연준의 단기 구간 매입 ④ 장기물 입찰 약화")

