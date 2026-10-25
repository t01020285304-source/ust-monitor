# -*- coding: utf-8 -*-
"""
💧 돈의 배관 18지표 — 「돈을 기다리는 사람들」 보고서의 18개 지표를 한 표로
  국채 공급 계획 → 실제 결제 → 민간 완충재 → 돈의 가격 → 긴급 창구·시장성 → 레버리지 → 사모신용 → 은행 → 달러 조달 → MMF
  · 이미 국채 위기 모니터가 계산한 값(treasury.build_state의 S)은 다시 계산하지 않고 그대로 가져옴
  · 새로 받는 공식 자료: 은행 예금·대형 정기예금(FRED H.8, 주간) · MMF의 국채·국채 레포 보유(미 재무부 OFR, 월간) · 사모신용 BDC(bdc.py, SEC 분기)
  · 무료 공식 자료가 없는 지표(국채 호가·현물선물 베이시스·FX 베이시스)는 0이나 추정으로 채우지 않고 '자료 없음'과 대체 확인 방법을 표시
  · 상태는 '폭락 신호'가 아니라 그 배관의 압력 수준 (정상·주의·경계) — 서로 다른 2~3개가 같은 방향일 때 해석을 바꿈
이 파일은 가격결정자_리서치와 국채위기모니터(builder) 양쪽에서 같은 내용으로 사용.
"""
from datetime import date, timedelta

import requests

OFR = "https://data.financialresearch.gov/v1/series/timeseries"


def _ofr(mn, cached):
    def load():
        r = requests.get(OFR, params={"mnemonic": mn, "start_date": (date.today() - timedelta(days=500)).isoformat()},
                         headers={"User-Agent": "MangoResearch/1.0 (personal research)"}, timeout=40)
        r.raise_for_status()
        return [[d, v] for d, v in r.json() if v is not None]
    return cached(f"ofr_{mn}.json", 12 * 3600, load)


def _chg(rows, days):
    if not rows:
        return None
    end = date.fromisoformat(rows[-1][0]) - timedelta(days=days)
    base = None
    for d, v in rows:
        if d <= end.isoformat():
            base = v
    return None if base in (None, 0) else rows[-1][1] / base - 1


def build(S, fred, cached, bdc_data=None):
    """S: 국채 모니터 상태 · fred(series, days) → rows · cached(name, age, loader)"""
    L, R, A, D = S.get("liq") or {}, S.get("repo") or {}, (S.get("absorb") or {}), S.get("debt") or {}
    Q = (A.get("qra") or {}).get("estimates") or {}
    AU = (S.get("auctions") or {})
    rows = []

    def add(n, grp, name, val, chg, asof, lv, why, tab=None, url=None, avail=True, how=None):
        rows.append({"n": n, "grp": grp, "name": name, "val": val, "chg": chg, "asof": asof, "lv": lv, "why": why, "tab": tab, "url": url, "avail": avail, "how": how})

    # ── 공급 계획 ──
    qs = Q.get("quarters") or []
    nq = qs[-1] if qs else None
    add(1, "공급 계획", "재무부 분기 차입 전망", f"${nq['borrow']:,.0f}B ({nq['q']})" if nq else "—",
        f"직전 발표 대비 {Q['change']['amt']:+,.0f}B" if Q.get("change") else "", (A.get("qra") or {}).get("next", ["—"])[0] + " 갱신 예정" if (A.get("qra") or {}).get("next") else "",
        "na", "정부가 이만큼 빌릴 계획 — 실제 발행·결제와 구별", "issue", Q.get("url"))
    add(2, "공급 계획", "QRA (분기 국채 차환 계획)", "다음 발표 " + ((A.get("qra") or {}).get("next") or ["—"])[1] if len((A.get("qra") or {}).get("next") or []) > 1 else "—", "",
        "", "na", "단기물·장기물 발행 비중 — 장기물이 늘면 장기금리 압력", "issue", (A.get("qra") or {}).get("page"))
    # ── 실제 결제 ──
    add(3, "실제 결제", "국채 입찰 (중장기물 12건)", f"응찰 {AU.get('coupon_avg_btc', 0):.2f}배 · Primary Dealer {AU.get('coupon_avg_dealer', 0):.1f}%" if AU.get("coupon_avg_btc") else "—",
        "", (AU.get("rows") or [{}])[0].get("date", ""), "ok" if (AU.get("coupon_avg_btc") or 0) >= 2.4 and (AU.get("coupon_avg_dealer") or 99) <= 18 else "warn",
        "투자자가 충분히 받아가는가 — 딜러가 많이 떠안으면 레포 차입 필요", "auc")
    add(4, "실제 결제", "TGA (재무부 현금 통장)", f"${L.get('tga_now', 0):,.0f}B" if L.get("tga_now") else "—", f"30일 {L.get('tga_30', 0):+,.0f}B" if L.get("tga_30") is not None else "",
        (L.get("tga") or [[None]])[-1][0], "warn" if (L.get("tga_30") or 0) > 100 else "ok", "늘면 은행 준비금이 빠질 수 있음 (1대1 법칙은 아님)", "liq")
    # ── 민간 완충재 ──
    add(5, "민간 완충재", "은행 준비금", f"${L.get('res_now', 0):,.2f}T" if L.get("res_now") else "—", f"13주 {L.get('res_13w', 0):+,.0f}B" if L.get("res_13w") is not None else "",
        (L.get("res") or [[None]])[-1][0], "warn" if (L.get("res_13w") or 0) < -150 else "ok", "은행 시스템의 중앙은행 돈 — 줄면 자금 조달 금리 상승 압력", "liq")
    add(6, "민간 완충재", "ON RRP (역레포)", f"${L.get('rrp_now', 0):,.1f}B" if L.get("rrp_now") is not None else "—", L.get("rrp_badge", ""), (L.get("rrp") or [[None]])[-1][0],
        L.get("rrp_st", "na"), "MMF 단기자금 주차장 — 바닥이면 국채를 더 흡수할 완충 공간이 작음", "liq")
    # ── 돈의 가격 ──
    si = R.get("sofr_iorb")
    add(7, "돈의 가격", "SOFR − IORB", f"{si:+.0f}bp" if si is not None else "—", f"SOFR {R.get('sofr')}% · IORB {R.get('iorb')}%", (R.get("hist") or [[None]])[-1][0] if R.get("hist") else "",
        "bad" if (si or 0) >= 15 else "warn" if (si or 0) >= 5 else "ok", "배관의 수압계 — 지속적으로 + 이면 담보 현금 수요가 공급보다 강함", "repo")
    s75 = R.get("spread75")
    add(8, "돈의 가격", "SOFR 75−25 분위 간격", f"{s75:.0f}bp" if s75 is not None else "—", "", "", "warn" if (s75 or 0) >= 10 else "ok",
        "평균은 평온해도 일부 참여자가 비싸게 조달하는지", "repo")
    # ── 긴급 창구·시장성 ──
    add(9, "긴급 창구·시장성", "SRF (연준 상설 레포) 이용", f"${L.get('srf_now', 0):,.1f}B" if L.get("srf_now") is not None else "—", "", (L.get("srf") or [[None]])[-1][0],
        L.get("srf_st", "na"), "소방서 출동 — 반복·대규모 이용이면 민간 조달 대신 공식 창구 의존", "liq")
    add(10, "긴급 창구·시장성", "국채 매수·매도 호가 스프레드", "공식 무료 자료 없음", "", "", "na", "대량 매도 비용 — 딜러가 재고를 떠안기 어려울 때 벌어짐",
        None, "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics", False,
        "대체 확인: Primary Dealer 국채 보유 변화(흡수력 탭) · 채권 변동성 MOVE(역발상 탭)")
    # ── 레버리지 ──
    add(11, "레버리지", "국채 현물·선물 베이시스", "공식 무료 자료 없음", "", "", "na", "헤지펀드 레버리지 거래 — 레포 비용이 오르면 현물 매도 압력",
        None, "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm", False, "대체 확인: CFTC 레버리지 펀드 국채 선물 포지션(가격결정자 윌리엄 매뉴얼 탭)")
    # ── 사모신용 (BDC) ──
    B = bdc_data or {}
    s = B.get("summary") or {}
    pk = s.get("pik")
    add(12, "사모신용", "PIK 이자 비중 (대형 BDC 중간값)", f"{pk * 100:.1f}%" if pk is not None else "—", "", B.get("asof", ""),
        "bad" if (pk or 0) >= 0.12 else "warn" if (pk or 0) >= 0.08 else "ok" if pk is not None else "na", "이자를 현금 대신 원금에 얹어 받는 비율 — 오르면 현금 회수가 늦어짐", "pipes")
    nf = s.get("na_fv")
    add(13, "사모신용", "Non-accrual (공정가치, 중간값)", f"{nf:.1f}%" if nf is not None else "—", f"상승: {', '.join(s.get('rise') or []) or '없음'}", B.get("asof", ""),
        "bad" if (nf or 0) >= 3 else "warn" if (nf or 0) >= 1.5 or len(s.get("rise") or []) >= 2 else "ok" if nf is not None else "na", "이자 인식을 멈춘 대출 — 원가·공정가치 기준을 따로 봐야 함", "pipes")
    add(14, "사모신용", "비상장 BDC 환매 요청 vs 지급 한도", "공시 형식이 제각각 — 원문 확인", "", "", "na", "환매가 지급 한도를 여러 분기 연속 넘는지",
        None, next((r.get("tender") for r in B.get("rows") or [] if r.get("tender")), None), False, "BCRED 등 공개매수(SC TO) 공시 링크에서 확인")
    lv_ = s.get("lev")
    add(15, "사모신용", "펀드 빚 ÷ 순자산 (중간값)", f"{lv_:.2f}배" if lv_ is not None else "—", "남은 차입 한도는 아래 표", B.get("asof", ""),
        "warn" if (lv_ or 0) >= 1.25 else "ok" if lv_ is not None else "na", "펀드의 빚(대출받은 기업의 빚과 합산 금지) — 담보가치가 떨어지면 한도 축소", "pipes")
    # ── 은행 ──
    dep, ltd = fred("DPSACBW027SBOG", 500), fred("LTDACBW027SBOG", 500)
    d13, l13 = _chg(dep, 91), _chg(ltd, 91)
    add(16, "은행", "상업은행 예금 · 대형 정기예금", f"${dep[-1][1] / 1000:,.2f}T" if dep else "—",
        (f"예금 13주 {d13 * 100:+.1f}%" if d13 is not None else "") + (f" · 대형 정기예금 13주 {l13 * 100:+.1f}%" if l13 is not None else ""),
        dep[-1][0] if dep else "", "bad" if (d13 or 0) <= -0.03 else "warn" if (d13 or 0) <= -0.01 or (l13 or 0) >= 0.08 else "ok" if dep else "na",
        "예금이 빠지고 비싼 대형 정기예금(도매성 자금)이 급증하면 은행 조달비용 상승", None, "https://www.federalreserve.gov/releases/h8/current/default.htm")
    # ── 달러 조달 ──
    add(17, "달러 조달", "FX 스와프 · 크로스커런시 베이시스", "공식 무료 자료 없음", "", "", "na", "해외 기관의 달러 조달 비용",
        None, "https://www.newyorkfed.org/markets/desk-operations/central-bank-liquidity-swap-operations", False, "대체 확인: 연준 중앙은행 달러 스왑라인 이용액(가격결정자 윌리엄 매뉴얼 탭)")
    # ── MMF ──
    try:
        tot, tsy, rpt = _ofr("MMF-MMF_TOT-M", cached), _ofr("MMF-MMF_T_TOT-M", cached), _ofr("MMF-MMF_RP_T_TOT-M", cached)
        sh = (tsy[-1][1] + rpt[-1][1]) / tot[-1][1] if tot and tsy and rpt else None
        c1 = _chg([[d, a + b] for (d, a), (_, b) in zip(tsy, rpt)], 31) if tsy and rpt and len(tsy) == len(rpt) else None
        add(18, "MMF", "MMF의 국채 + 국채 레포 보유", f"${(tsy[-1][1] + rpt[-1][1]) / 1e12:,.2f}T (전체의 {sh * 100:.0f}%)" if sh else "—",
            f"한 달 {c1 * 100:+.1f}%" if c1 is not None else "", tsy[-1][0] if tsy else "", "warn" if (c1 or 0) <= -0.05 else "ok" if sh else "na",
            "누가 국채를 사는가 — MMF가 국채·레포에서 빠지면 국채 흡수 여력 감소 (정부형 MMF 잔액은 ICI가 접속을 막아 OFR 보유 내역으로 대신)",
            None, "https://www.financialresearch.gov/money-market-funds/")
    except Exception as e:
        add(18, "MMF", "MMF의 국채 + 국채 레포 보유", f"받지 못함 ({str(e)[:40]})", "", "", "na", "누가 국채를 사는가", None, "https://www.financialresearch.gov/money-market-funds/")

    # ── 종합: 보고서 8장의 세 가지 상태 ──
    bad = lambda grps: [r for r in rows if r["grp"] in grps and r["lv"] in ("warn", "bad")]
    pipe = bad({"돈의 가격", "긴급 창구·시장성"}) + [r for r in rows if r["n"] in (5, 6) and r["lv"] == "bad"]
    credit = bad({"사모신용"}) + bad({"은행"})
    s8 = (S.get("stress8") or {}).get("questions") or []
    q2 = bool(s8 and s8[1].get("yes"))
    q3 = bool(s8 and s8[2].get("yes"))
    if pipe and (credit or q3) and (q2 or q3):
        state = {"k": "shock", "lv": "bad", "t": "전이성 충격 의심", "d": "자금시장 배관과 신용·사모신용이 함께 나빠져요 — 신규 레버리지 자제, 유동성 보존", "act": "신규 레버리지 자제 · 유동성 보존"}
    elif credit or q2 or pipe:
        state = {"k": "select", "lv": "warn", "t": "선택적 조정", "d": "거시 배관은 대체로 작동하지만 일부 신용·사모신용·자금시장 지표가 압력 — 취약 기업과 견고한 기업을 나눠 보세요", "act": "취약 기업과 견고한 기업 분리"}
    else:
        state = {"k": "normal", "lv": "ok", "t": "완화·정상화", "d": "국채 수급·자금시장·신용 모두 큰 압력 없음 — 기업별 가치평가 갱신에 집중", "act": "기업별 가치평가 갱신"}
    warn = [f"{r['n']}. {r['name']}" for r in rows if r["lv"] in ("warn", "bad")]
    na = [r["n"] for r in rows if not r["avail"]]
    nar = [f"{state['t']} — {state['d']}",
           f"18개 중 압력 신호 {len(warn)}개" + (f": {', '.join(warn[:6])}" if warn else "") + f" · 공식 무료 자료가 없어 대체 지표로 보는 항목 {len(na)}개({', '.join(map(str, na))}번).",
           "한 지표가 나쁘다고 위기가 확정되는 게 아니라, 서로 다른 구간의 지표 2~3개가 같은 방향으로 움직일 때 해석을 바꿔요. 분기 자료(사모신용)는 일간 자료와 날짜가 다르니 기준일을 함께 보세요."]
    return {"rows": rows, "state": state, "narrative": nar, "src": "미 재무부 · NY 연준 · 연준 H.8 · FRED · 미 재무부 OFR · SEC(BDC 공시)",
            "basis": "「돈을 기다리는 사람들 — 미국 국채와 AI 인프라 그리고 사모신용이 만나는 지점」(2026-10-25) 18개 지표"}
