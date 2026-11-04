"""원자재 레이더 기준표 — 원자재 · 선물 계약 · 출처 (commodities · futures_contracts · source_metadata)

CFTC 계약 코드는 2026-11-05 CFTC 공식 API(72hh-3qpy) 응답으로 직접 확인한 값만 적는다.
대표 계약이 CFTC에 없거나 다른 상품(프리미엄 계약 등)이면 status 를 'check' 로 두고 화면에서 포지션을 기본으로 숨긴다.
"""

# 그룹: energy · precious · industrial · agri
# price: 가격 숫자(공식) — ("fred", 시리즈, 단위, 주기) / None
# move: 이번 주 방향(등락률) — ("fred", 시리즈) 공식 일간 / ("yahoo", 심볼) 참고
COMMODITIES = [
    {"id": "WTI", "name": "WTI 원유", "group": "energy", "cot": "067651", "status": "ok",
     "price": ("fred", "DCOILWTICO", "달러/배럴", "일간 · EIA"), "move": ("fred", "DCOILWTICO"), "inv": "crude",
     "alt": "ICE 거래소 WTI(067411)도 있지만 기준 계약인 NYMEX만 보여 줘요 (두 계약을 더하지 않아요)."},
    {"id": "BRENT", "name": "브렌트유", "group": "energy", "cot": None, "status": "check",
     "price": ("fred", "DCOILBRENTEU", "달러/배럴", "일간 · EIA"), "move": ("fred", "DCOILBRENTEU"), "inv": None,
     "why": "브렌트유는 영국 ICE 거래소 상품이라 미국 CFTC 보고서에 없어요. 같은 원유인 WTI의 투기자금 흐름을 함께 보세요.",
     "see": "WTI"},
    {"id": "NG", "name": "천연가스 (헨리허브)", "group": "energy", "cot": "023651", "status": "ok",
     "price": ("fred", "DHHNGSP", "달러/MMBtu", "일간 · EIA"), "move": ("fred", "DHHNGSP"), "inv": "gas",
     "alt": "ICE 거래소 천연가스(023391)는 계약 크기가 2,500 MMBtu로 달라서 더하지 않아요."},
    {"id": "GOLD", "name": "금", "group": "precious", "cot": "088691", "status": "ok",
     "price": None, "move": ("yahoo", "GC=F"), "inv": None, "alt": "소형 계약(Micro Gold, 088695)은 제외했어요."},
    {"id": "SILVER", "name": "은", "group": "precious", "cot": "084691", "status": "ok",
     "price": None, "move": ("yahoo", "SI=F"), "inv": None},
    {"id": "PLAT", "name": "백금", "group": "precious", "cot": "076651", "status": "ok",
     "price": None, "move": ("yahoo", "PL=F"), "inv": None},
    {"id": "COPPER", "name": "구리", "group": "industrial", "cot": "085692", "status": "ok",
     "price": ("fred", "PCOPPUSDM", "달러/톤", "월평균 · IMF"), "move": ("yahoo", "HG=F"), "inv": None,
     "alt": "세계 기준 시장인 런던금속거래소(LME) 구리는 CFTC 보고 대상이 아니라, 미국 COMEX 구리만 보여 줘요."},
    {"id": "ALU", "name": "알루미늄", "group": "industrial", "cot": "191693", "status": "check",
     "price": ("fred", "PALUMUSDM", "달러/톤", "월평균 · IMF"), "move": None, "inv": None,
     "why": "미국 CFTC에 있는 알루미늄 계약은 알루미늄 값이 아니라 미국 중서부에서 붙는 '웃돈(Midwest Premium)' 계약이에요. 이 포지션을 알루미늄 투기 흐름으로 읽으면 오해할 수 있어 기본으로 숨겨요."},
    {"id": "LITH", "name": "리튬", "group": "industrial", "cot": "189691", "status": "check",
     "price": None, "move": None, "inv": None,
     "why": "CFTC에는 수산화리튬 한 종류(COMEX)만 있고 거래도 적어요. 리튬 시장 전체를 대표하지 않아서 '참고로 보기'를 눌러야 나와요. 리튬 가격은 공식 무료 자료가 없어요."},
    {"id": "CORN", "name": "옥수수", "group": "agri", "cot": "002602", "status": "ok",
     "price": ("fred", "PMAIZMTUSDM", "달러/톤", "월평균 · IMF"), "move": ("yahoo", "ZC=F"), "inv": None},
    {"id": "SOY", "name": "대두", "group": "agri", "cot": "005602", "status": "ok",
     "price": ("fred", "PSOYBUSDM", "달러/톤", "월평균 · IMF"), "move": ("yahoo", "ZS=F"), "inv": None},
    {"id": "WHEAT", "name": "소맥 (SRW)", "group": "agri", "cot": "001602", "status": "ok",
     "price": ("fred", "PWHEAMTUSDM", "달러/톤", "월평균 · IMF"), "move": ("yahoo", "ZW=F"), "inv": None,
     "alt": "시카고 연질 적색 겨울밀(SRW) 기준이에요. 경질밀(HRW, 001612)·봄밀(001626)은 다른 계약이라 더하지 않아요."},
]
GROUPS = {"energy": "에너지", "precious": "귀금속", "industrial": "산업금속", "agri": "농산물"}

# CFTC 계약 단위 (실물 환산) — 실행마다 CFTC contract_units 문구와 대조, 다르면 경고
CONTRACTS = {
    "067651": {"exch": "NYMEX", "name": "WTI-PHYSICAL", "size": 1000, "unit": "배럴", "units_text": "1,000 BARRELS"},
    "023651": {"exch": "NYMEX", "name": "NAT GAS NYME", "size": 10000, "unit": "MMBtu", "units_text": "10,000 MMBTU"},
    "088691": {"exch": "COMEX", "name": "GOLD", "size": 100, "unit": "온스", "units_text": "100 TROY OUNCES"},
    "084691": {"exch": "COMEX", "name": "SILVER", "size": 5000, "unit": "온스", "units_text": "5,000 TROY OUNCES"},
    "076651": {"exch": "NYMEX", "name": "PLATINUM", "size": 50, "unit": "온스", "units_text": "50 TROY OUNCES"},
    "085692": {"exch": "COMEX", "name": "COPPER- #1", "size": 25000, "unit": "파운드", "units_text": "25,000 POUNDS"},
    "191693": {"exch": "COMEX", "name": "ALUMINUM MWP", "size": 25, "unit": "톤", "units_text": "25 MT"},
    "189691": {"exch": "COMEX", "name": "LITHIUM HYDROXIDE", "size": 1000, "unit": "kg", "units_text": "1000) KILOGRAMS"},
    "002602": {"exch": "CBOT", "name": "CORN", "size": 5000, "unit": "부셸", "units_text": "5,000 BUSHELS"},
    "005602": {"exch": "CBOT", "name": "SOYBEANS", "size": 5000, "unit": "부셸", "units_text": "5,000 BUSHELS"},
    "001602": {"exch": "CBOT", "name": "WHEAT-SRW", "size": 5000, "unit": "부셸", "units_text": "5,000 BUSHELS"},
}

# CFTC 응답 필드 — 그룹마다 이름 규칙이 다름 (Swap 숏은 밑줄 2개, Producer·Other 는 _all 없음)
COT_FIELDS = {
    "pm": ("prod_merc_positions_long", "prod_merc_positions_short"),
    "sd": ("swap_positions_long_all", "swap__positions_short_all"),
    "mm": ("m_money_positions_long_all", "m_money_positions_short_all"),
    "or": ("other_rept_positions_long", "other_rept_positions_short"),
}
GROUP_KR = {"pm": "Producer/Merchant (생산·실수요)", "sd": "Swap Dealer (스와프 딜러)", "mm": "Managed Money (투기자금)", "or": "Other Reportables (기타 대형)"}

# EIA 주간 재고
EIA_INV = {
    "crude": {"route": "petroleum/stoc/wstk", "series": "WCESTUS1", "name": "미국 원유 재고 (전략비축유 제외)", "unit": "천 배럴", "pub": "매주 수요일 10:30 (미국 동부)"},
    "gas": {"route": "natural-gas/stor/wkly", "series": "NW2_EPG0_SWO_R48_BCF", "name": "미국 천연가스 저장량 (Lower 48)", "unit": "Bcf", "pub": "매주 목요일 10:30 (미국 동부)"},
}

SOURCES = {
    "cftc": {"label": "CFTC Commitments of Traders (Disaggregated, Futures Only)", "url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
             "pub": "매주 금요일 15:30 (미국 동부) — 그 주 화요일 기준", "license": "미국 정부 공공 자료"},
    "eia": {"label": "EIA 주간 석유·천연가스 재고", "url": "https://www.eia.gov/petroleum/supply/weekly/", "license": "미국 정부 공공 자료"},
    "fred_eia": {"label": "FRED (원자료 EIA 현물 가격)", "url": "https://fred.stlouisfed.org/", "license": "미국 정부 공공 자료"},
    "fred_imf": {"label": "FRED (원자료 IMF Primary Commodity Prices)", "url": "https://www.imf.org/en/Research/commodity-prices", "license": "IMF — 출처 표시"},
    "yahoo": {"label": "Yahoo Finance 선물 시세 (등락률만, 참고)", "url": "https://finance.yahoo.com/", "license": "참고용 — 가격 숫자는 싣지 않음"},
}

# 오래된 자료 경고 (관측일로부터 일수)
STALE_DAYS = {"fred_day": 12, "fred_month": 75, "yahoo": 5}
