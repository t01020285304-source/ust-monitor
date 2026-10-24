# -*- coding: utf-8 -*-
"""
🧯 강제매도 위험 진단 — 8대 지표 (윌리엄 「폭락을 두려워한다면 주가보다 먼저 확인해야 할 것들」)
  진짜 위험은 가격 하락이 아니라 '누군가 버티지 못하고 자산을 팔아야 하는 상황'.
  폭락 확정 신호가 아니라 '위험의 종류'를 구별하는 진단:
    ① 금리 문제인가  ② 기업 신용 문제인가  ③ 금융시장 자금조달 문제까지 번졌나
  지표: DFII10 · BAMLH0A3HYC(CCC) · BAMLH0A0HYM2(HY) · BAMLC0A0CM(IG) · SOFR−IORB · NFCI · SLOOS(DRTSCILM) · VIX
  출처: FRED(미 재무부·ICE BofA·연준·시카고 연은) · NY 연준 — 공식 공개 자료
  기준 숫자(1개월 변화 폭)는 원문에 없어 사이트 설정 (원문은 '절대 수준이 아니라 같은 기간의 변화 폭을 비교')
이 파일은 가격결정자_리서치와 국채위기모니터(builder) 양쪽에서 같은 내용으로 사용.
"""
from datetime import date, timedelta

# (키, 이름, FRED 시리즈, 단위 배수(→표시 단위), 표시 단위, 1개월 '주의' 변화, '위험' 변화, 질문 묶음, 쉬운 설명)
SPEC = [
    ("real", "실질금리 (10년)", "DFII10", 100, "bp", 25, 50, "rate", "성장주 가치가 먼저 압박받나 — 오르면 먼 미래 이익의 현재가치가 낮아져요"),
    ("ccc", "CCC 신용스프레드", "BAMLH0A3HYC", 100, "bp", 75, 150, "credit", "가장 약한 기업부터 돈줄이 막히나"),
    ("hy", "하이일드 스프레드", "BAMLH0A0HYM2", 100, "bp", 40, 100, "credit", "기업 부실 위험이 퍼지나"),
    ("ig", "우량 회사채 스프레드", "BAMLC0A0CM", 100, "bp", 15, 35, "fund", "위험이 강한 기업까지 번지나"),
    ("sofr", "SOFR − IORB", None, 1, "bp", None, None, "fund", "초단기 자금시장에 압력이 생겼나 — 월말·분기말 일시 상승은 제외"),
    ("nfci", "NFCI (금융여건)", "NFCI", 1, "", 0.10, 0.25, "fund", "금융시장 전체가 돈 빌리기 불리해지나 — 0은 평균일 뿐 폭락 기준선이 아님"),
    ("sloos", "SLOOS (대출기준 강화 비율)", "DRTSCILM", 1, "%p", None, None, "fund", "은행이 실제로 돈 빌려주기를 꺼리나 — 분기 조사(늦게 나오는 정보)"),
    ("vix", "VIX (주식 공포지수)", "VIXCLS", 1, "", 8, 15, "equity", "주식 참여자들이 변동성을 비싸게 보나"),
]
FRED_IDS = ["DFII10", "BAMLH0A3HYC", "BAMLH0A0HYM2", "BAMLC0A0CM", "SOFR", "IORB", "NFCI", "DRTSCILM", "VIXCLS"]
LINK = {"DFII10": "https://fred.stlouisfed.org/series/DFII10", "BAMLH0A3HYC": "https://fred.stlouisfed.org/series/BAMLH0A3HYC",
        "BAMLH0A0HYM2": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "BAMLC0A0CM": "https://fred.stlouisfed.org/series/BAMLC0A0CM",
        "SOFR": "https://www.newyorkfed.org/markets/reference-rates/sofr", "NFCI": "https://www.chicagofed.org/research/data/nfci/current-data",
        "DRTSCILM": "https://www.federalreserve.gov/data/sloos.htm", "VIXCLS": "https://www.cboe.com/tradable_products/vix/"}


def _at(rows, d):
    """d 이전(포함) 마지막 값"""
    v = None
    for r in rows:
        if r[0] <= d:
            v = r[1]
        else:
            break
    return v


def _chg(rows, days):
    if not rows:
        return None
    last = rows[-1]
    base = _at(rows, (date.fromisoformat(last[0]) - timedelta(days=days)).isoformat())
    return None if base is None else last[1] - base


def _month_end(d):
    """월말·분기말 전후 3영업일 — SOFR 일시 상승 구간"""
    x = date.fromisoformat(d)
    nxt = (x.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (nxt - x).days <= 3 or x.day <= 2


def compute(get):
    """get(series_id, days) → [[날짜, 값], ...]  (오래된 → 최신)"""
    S = {k: [] for k in FRED_IDS}
    errs = []
    for sid in FRED_IDS:
        try:
            S[sid] = [r for r in (get(sid, 500) or []) if r and r[1] is not None]
        except Exception as e:
            errs.append(f"{sid}: {str(e)[:60]}")
    # SOFR − IORB (bp) 일별
    io = S["IORB"]
    spread = [[d, round((v - _at(io, d)) * 100, 1)] for d, v in S["SOFR"] if _at(io, d) is not None]
    rows = []
    for key, name, sid, mul, unit, w1m, b1m, grp, why in SPEC:
        if key == "sofr":
            ser = spread
        else:
            ser = [[d, v] for d, v in S.get(sid) or []]
        if not ser:
            rows.append({"key": key, "name": name, "grp": grp, "why": why, "lv": "na", "txt": "자료 없음", "sid": sid}); continue
        last = ser[-1]
        c1w, c1m = _chg(ser, 7), _chg(ser, 30)
        c1w = None if c1w is None or key == "sloos" else c1w * mul
        c1m = None if c1m is None else c1m * mul
        lv, txt = "ok", ""
        if key == "sofr":
            calm = [v for d, v in ser[-10:] if not _month_end(d)]                         # 월말·분기말 제외
            med = sorted(calm)[len(calm) // 2] if calm else last[1]
            lv = "bad" if med >= 15 else "warn" if med >= 5 else "ok"
            txt = f"최근 2주(월말 제외) 중간값 {med:+.0f}bp"
        elif key == "sloos":
            prev = ser[-2][1] if len(ser) >= 2 else None
            lv = "bad" if last[1] >= 40 else "warn" if last[1] >= 20 or (prev is not None and last[1] - prev >= 10) else "ok"
            txt = f"대출기준 강화 비율 {last[1]:+.1f}%p" + (f" (직전 분기 {prev:+.1f})" if prev is not None else "")
            c1m = None if prev is None else last[1] - prev
        elif key == "vix":
            lv = "bad" if last[1] >= 35 or (c1m or 0) >= b1m else "warn" if last[1] >= 25 or (c1m or 0) >= w1m else "ok"
        else:
            lv = "bad" if (c1m or 0) >= b1m else "warn" if (c1m or 0) >= w1m else "ok"
        val = last[1] if key in ("real", "sofr") else last[1] * mul      # 실질금리는 % 그대로, 스프레드는 bp
        disp = "%" if key == "real" else unit
        rows.append({"key": key, "name": name, "sid": sid or "SOFR−IORB", "grp": grp, "why": why, "date": last[0], "v": round(val, 2), "unit": unit, "disp": disp,
                     "c1w": None if c1w is None else round(c1w, 2), "c1m": None if c1m is None else round(c1m, 2), "lv": lv, "txt": txt,
                     "rule": None if w1m is None else f"1개월 +{w1m}{unit} 이상 주의 · +{b1m}{unit} 이상 위험", "url": LINK.get(sid or "SOFR")})
    R = {r["key"]: r for r in rows}
    bad = lambda *ks: [k for k in ks if R.get(k, {}).get("lv") in ("warn", "bad")]
    # CCC가 하이일드보다 두드러지게 오르나 (같은 기간 변화 폭 비교)
    cc, hy = R.get("ccc", {}).get("c1m"), R.get("hy", {}).get("c1m")
    ccc_lead = cc is not None and hy is not None and cc >= 50 and cc > max(hy, 0) * 1.5
    q1 = bool(bad("real"))
    q2 = bool(bad("ccc", "hy")) or ccc_lead
    q3 = bool(bad("ig", "sofr", "nfci"))
    vix = bool(bad("vix"))
    Q = [{"q": "① 금리 문제인가?", "yes": q1, "ev": "실질금리 1개월 " + _f(R.get("real", {}).get("c1m"), "bp")},
         {"q": "② 기업 신용 문제인가?", "yes": q2, "ev": f"CCC {_f(cc, 'bp')} · 하이일드 {_f(hy, 'bp')} (1개월)" + (" — CCC가 두드러지게 확대" if ccc_lead else "")},
         {"q": "③ 금융시장 자금조달 문제까지 번졌나?", "yes": q3, "ev": f"우량채 {_f(R.get('ig', {}).get('c1m'), 'bp')} · SOFR−IORB {R.get('sofr', {}).get('txt', '—')} · NFCI {_f(R.get('nfci', {}).get('c1m'), '')} (1개월)"}]
    if q3 and (q2 or bad("ig")):
        case = {"n": 3, "lv": "bad", "t": "신용시장 전반으로 확산 의심", "d": "우량채 스프레드·단기자금시장까지 불안 — 차입·레버리지·유동성 위험을 재점검하세요 (예시 3)"}
    elif q2:
        case = {"n": 2, "lv": "warn", "t": "위험기업 자금조달 압박", "d": "CCC·하이일드 스프레드 확대 — 약한 기업의 부실 가능성을 집중 점검하세요 (예시 2)"}
    elif q1:
        case = {"n": 1, "lv": "warn", "t": "금리·밸류에이션 충격", "d": "실질금리만 오르고 신용시장은 안정 — 기업 부실보다 할인율 상승(성장주 압박)을 먼저 검토하세요 (예시 1)"}
    elif vix:
        case = {"n": 4, "lv": "warn", "t": "주식시장 불안 (금융시스템 위기 아님)", "d": "VIX만 오르고 신용·자금시장은 안정 — 주가 급락만으로 금융위기라 결론 내리지 마세요 (예시 4)"}
    elif q3:
        case = {"n": 0, "lv": "warn", "t": "자금시장 일부 긴장", "d": "신용은 안정적이지만 자금조달 지표 일부가 긴장 — 다음 주에도 이어지는지 확인하세요"}
    else:
        case = {"n": 0, "lv": "ok", "t": "강제매도 압력 낮음", "d": "금리·신용·자금시장 모두 큰 변화 없음 — 평소 루틴대로 매주 확인"}
    # 매주 금요일 기록 — 최근 6주 금요일 값 (자료 기록에서 자동)
    today = date.today()
    fri = today - timedelta(days=(today.weekday() - 4) % 7)
    weeks = [(fri - timedelta(days=7 * i)).isoformat() for i in range(6)][::-1]
    series_of = {"sofr": spread, **{k: S.get(sid) or [] for k, _, sid, *_ in SPEC if sid}}
    weekly = [{"key": r["key"], "name": r["name"], "unit": r.get("disp", r.get("unit", "")),
               "vals": [None if (v := _at(series_of.get(r["key"], []), d)) is None else round(v * (100 if r.get("unit") == "bp" and r["key"] not in ("sofr", "real") else 1), 2) for d in weeks]}
              for r in rows if r["key"] != "sloos"]
    return {"rows": rows, "questions": Q, "case": case, "ccc_lead": ccc_lead, "weeks": weeks, "weekly": weekly, "errors": errs,
            "src": "FRED (미 재무부 DFII10 · ICE BofA 스프레드 · 시카고 연은 NFCI · 연준 SLOOS · Cboe VIX) · NY 연준 SOFR · 연준 IORB",
            "note": "폭락 확정 신호가 아니라 위험의 종류를 구별하는 진단이에요. 기준 숫자(1개월 변화 폭)는 원문에 없어 사이트가 정한 값이에요."}


def _f(x, u):
    return "—" if x is None else f"{x:+.0f}{u}" if u == "bp" else f"{x:+.2f}{u}"
