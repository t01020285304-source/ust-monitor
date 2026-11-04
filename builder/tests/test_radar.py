"""원자재 레이더 계산 테스트 — 인터넷 없이 실행 (python builder/tests/test_radar.py, pytest 로도 실행 가능)"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar as R  # noqa: E402
import radar_meta as M  # noqa: E402
import radar_store as RS  # noqa: E402

# CFTC 실제 응답 일부 (WTI-PHYSICAL 067651, 2026-10-27)
WTI = {"report_date_as_yyyy_mm_dd": "2026-10-27T00:00:00.000", "cftc_contract_market_code": "067651", "contract_units": "(CONTRACTS OF 1,000 BARRELS)",
       "open_interest_all": "1886280", "prod_merc_positions_long": "629668", "prod_merc_positions_short": "263276",
       "swap_positions_long_all": "135085", "swap__positions_short_all": "604445",
       "m_money_positions_long_all": "157433", "m_money_positions_short_all": "126305",
       "other_rept_positions_long": "172735", "other_rept_positions_short": "129520"}


def weeks(n, start="2023-01-03", f=lambda i: i):
    d0 = date.fromisoformat(start)
    return [((d0 + timedelta(days=7 * i)).isoformat(), f(i)) for i in range(n)]


def test_1_field_mapping():
    got = {g: int(WTI[l]) - int(WTI[s]) for g, (l, s) in M.COT_FIELDS.items()}
    assert got == {"pm": 366392, "sd": -469360, "mm": 31128, "or": 43215}
    assert M.COT_FIELDS["sd"][1] == "swap__positions_short_all"          # 밑줄 2개


def test_2_net_and_pct_oi():
    net = R.net_rows([("2026-10-27", 157433)], [("2026-10-27", 126305)])
    assert net == [("2026-10-27", 31128)]
    assert round(31128 / 1886280 * 100, 2) == 1.65


def test_3_missing_week_is_blank():
    rows = weeks(10)
    del rows[5]                                    # 6번째 주 빠짐
    last = rows[-1][0]                             # 10번째 주 → 4주 전이 바로 빠진 6번째 주
    assert R.change(rows, last, 28) is None        # 이웃 주(5·7번째)로 대체하지 않음
    assert R.change(rows, last, 7) == 1
    assert R.change(rows, last, 91) is None        # 13주 전은 자료 범위 밖


def test_4_percentile():
    rows = weeks(156, f=lambda i: i)
    assert R.percentile(rows, rows[-1][0]) == round(155.5 / 156 * 100, 1)     # 최댓값
    low = weeks(156, f=lambda i: 156 - i)
    assert R.percentile(low, low[-1][0]) == round(0.5 / 156 * 100, 1)         # 최솟값
    same = weeks(156, f=lambda i: 7)
    assert R.percentile(same, same[-1][0]) == 50.0                              # 모두 같은 값
    assert R.percentile(weeks(129), weeks(129)[-1][0]) is None                  # 표본 부족


def test_5_units_check():
    assert R.units_ok("067651", "(CONTRACTS OF 1,000 BARRELS)")
    assert R.units_ok("023651", "(Contracts of 10,000  MMBTU'S)")
    assert R.units_ok("189691", "(1000) Kilograms")
    assert not R.units_ok("067651", "(CONTRACTS OF 42,000 GALLONS)")


def _store():
    return {"schema": 1, "rows": []}


def test_6_revision_keeps_old_version():
    st = _store()
    row = {"sid": "cot.x.oi", "obs": "2026-10-27", "v": 100, "unit": "contracts", "pub": "2026-10-30", "pk": "schedule", "src": "cftc"}
    assert RS.upsert(st, [row], seen="2026-10-31T00:00Z") == (1, 0)
    assert RS.upsert(st, [row], seen="2026-11-01T00:00Z") == (0, 0)           # 같은 값 → 중복 저장 안 함
    assert RS.upsert(st, [dict(row, v=120)], seen="2026-11-02T00:00Z") == (0, 1)
    vers = sorted(r["ver"] for r in st["rows"])
    assert vers == [1, 2] and RS.series(st, "cot.x.oi") == [("2026-10-27", 120)]


def test_7_point_in_time():
    st = _store()
    row = {"sid": "s", "obs": "2026-10-27", "v": 1, "unit": "u", "pub": "2026-10-30", "pk": "schedule", "src": "cftc"}
    RS.upsert(st, [row], seen="2026-10-31T00:22Z")
    assert RS.series(st, "s", as_of="2026-10-30T00:00Z") == []                 # 아직 받기 전
    assert RS.series(st, "s", as_of="2026-10-31T01:00Z") == [("2026-10-27", 1)]
    RS.upsert(st, [dict(row, v=2)], seen="2026-11-07T00:00Z")
    assert RS.series(st, "s", as_of="2026-11-01T00:00Z") == [("2026-10-27", 1)]   # 정정 전 값
    old = {"sid": "b", "obs": "2024-01-02", "v": 5, "unit": "u", "pub": "2024-01-05", "pk": "estimated", "src": "cftc"}
    RS.upsert(st, [old], seen="2026-11-05T00:00Z")                            # 과거 일괄 수집 → 추정 발표일 기준
    assert RS.series(st, "b", as_of="2024-01-06T00:00Z") == [("2024-01-02", 5)]
    assert RS.series(st, "b", as_of="2024-01-04T00:00Z") == []


def test_8_check_status_hides_cot():
    chk = [c["id"] for c in M.COMMODITIES if c["status"] == "check"]
    assert set(chk) == {"BRENT", "ALU", "LITH"}
    assert all(c.get("why") for c in M.COMMODITIES if c["status"] == "check")
    assert all(c["cot"] is None or c["cot"] in M.CONTRACTS for c in M.COMMODITIES)


def test_9_quadrant():
    oi = 100000
    assert R.quadrant(1.0, 5000, oi)["key"] == "up_up"
    assert R.quadrant(1.0, -5000, oi)["key"] == "up_down"
    assert R.quadrant(-1.0, 5000, oi)["key"] == "down_up"
    assert R.quadrant(-1.0, -5000, oi)["key"] == "down_down"
    assert R.quadrant(-1.0, 499, oi)["key"] == "flat"                          # 0.5% 미만
    assert R.quadrant(-1.0, 500, oi)["key"] == "down_up"                       # 경계
    assert R.quadrant(None, 500, oi) is None


def test_10_inventory_5y_excludes_this_year():
    rows = []
    for y in range(2020, 2027):
        d = date.fromisocalendar(y, 43, 5)
        rows.append((d.isoformat(), 100 + (y - 2020) * 10))
    f = R.inv_5y(rows, date.fromisocalendar(2026, 43, 5).isoformat())
    assert f["n"] == 5 and f["avg"] == (110 + 120 + 130 + 140 + 150) / 5 and f["hi"] == 150   # 2026(160) 제외
    assert R.inv_5y(rows[-3:], rows[-1][0]) is None                            # 3년 미만


def test_store_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        st = RS.load("x", base=t)
        RS.upsert(st, [{"sid": "a", "obs": "2026-01-01", "v": 1, "unit": "u", "pub": "2026-01-02", "pk": "seen", "src": "s"}])
        RS.save("x", st, base=t)
        assert RS.load("x", base=t)["rows"][0]["v"] == 1


def test_11_cycle_real_price_and_phase():
    cpi = [(f"{2000 + i // 12}-{i % 12 + 1:02d}-01", 100 + i) for i in range(300)]
    px = [(o, 50.0) for o, _ in cpi]
    real = R.real_rows(px, cpi)
    assert real[-1][1] == 50.0 and round(real[0][1], 2) == round(50 * 399 / 100, 2)   # 오늘 물가 기준으로 환산
    assert R.real_rows(px, cpi[:-12])[-1][0] == cpi[-13][0]                             # CPI 없는 달은 빼고 채우지 않음
    rising = [(o, float(i)) for i, (o, _) in enumerate(cpi)]
    pos = R.cycle_pos(rising)
    assert pos["pct"] == round(239.5 / 240 * 100, 1) and pos["mom12"] > 0 and pos["years"] == 20
    assert R.cycle_pos(rising[:119]) is None                                              # 10년 미만이면 판단 안 함
    assert R.phase(95, 5)["key"] == "boom" and R.phase(80, -1)["key"] == "downturn"
    assert R.phase(20, -3)["key"] == "trough" and R.phase(20, 4)["key"] == "recovery"
    assert R.phase(35, -1)["key"] == "mid" and R.phase(50, None) is None


def test_12_korean_particles():
    assert R._jo("브렌트유", "은", "는") == "는" and R._jo("금", "은", "는") == "은"
    assert R._jo("소맥 (SRW)", "은", "는") == "은" and R._jo("천연가스 (헨리허브)", "은", "는") == "는"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("통과", name)
            except AssertionError as e:
                fails += 1
                print("실패", name, e)
    print(f"테스트 {'실패 ' + str(fails) + '개' if fails else '모두 통과'}")
    sys.exit(1 if fails else 0)
