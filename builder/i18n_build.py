"""번역 사전 만들기 — builder/i18n_dict.json(원본: 한국어 문장 틀 → en/zh) 을 화면용 site/i18n/en.js · zh.js 로 바꾼다
실행: python builder/i18n_build.py
- 키는 site/i18n.js 의 norm() 과 같은 규칙(숫자 → {0}{1}…)으로 만든 문장 틀이어야 한다.
- 날짜 뒤 요일 '(화)' 처럼 요일만 다른 문장은 7개 요일 모두로 자동으로 늘려 넣는다.
- 빠진 문장 찾기: python builder/tests/i18n_scan.py en"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "builder" / "i18n_dict.json"
KO = "월화수목금토일"
WD = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "zh": ["一", "二", "三", "四", "五", "六", "日"]}
PH = re.compile(r"\{\d+\}")


def expand(d):
    """요일만 다른 문장 늘리기 — 키에 '(요일)' 하나, 번역에 그 요일 표기 하나가 있을 때만"""
    out = dict(d)
    for k, v in d.items():
        m = re.findall(r"\(([월화수목금토일])\)", k)
        if len(m) != 1:
            continue
        i = KO.index(m[0])
        if any(v[L].count(WD[L][i]) != 1 for L in WD):
            continue
        for j, ch in enumerate(KO):
            nk = k.replace(f"({m[0]})", f"({ch})")
            if nk not in out:
                out[nk] = {L: v[L].replace(WD[L][i], WD[L][j]) for L in WD}
    return out


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    bad = [k for k, v in d.items() for L in WD if sorted(PH.findall(v[L])) != sorted(PH.findall(k))]
    if bad:
        raise SystemExit("자리표가 안 맞는 번역: " + ", ".join(bad[:5]))
    d = expand(d)
    for L in WD:
        m = {k: d[k][L] for k in sorted(d)}
        (ROOT / "site" / "i18n" / f"{L}.js").write_text(
            f"/* 자동 생성 — 고치려면 builder/i18n_dict.json 을 고치고 python builder/i18n_build.py */\nI18N.load({json.dumps(m, ensure_ascii=False, indent=0)});\n", encoding="utf-8")
    # 사전이 바뀌면 브라우저가 새 파일을 받도록 i18n.js 의 ?v= 를 내용 해시로 바꾼다
    h = hashlib.sha1((ROOT / "site" / "i18n" / "en.js").read_bytes() + (ROOT / "site" / "i18n" / "zh.js").read_bytes()).hexdigest()[:8]
    js = ROOT / "site" / "i18n.js"
    js.write_text(re.sub(r"\.js\?v=[0-9a-z]+'", f".js?v={h}'", js.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"번역 사전 {len(d)}개 문장 틀 → site/i18n/en.js · zh.js")


if __name__ == "__main__":
    main()
