"""자료 번역 붙이기 — 자료(JSON)에 들어가는 한국어 문장의 영어·번체(대만) 번역을 'i18n' 칸으로 함께 보낸다
화면(site/i18n.js)의 I18N.extend 가 이 칸을 읽어, 매일 바뀌는 해설도 Netlify 배포 없이 번역된다.
번역 원본은 화면과 같은 builder/i18n_dict.json (키 = 숫자를 {0}{1}… 로 바꾼 한국어 문장 틀).
규칙은 site/i18n.js 와 같다: ① 통째로 같은 문장(extra) ② 숫자 자리표 문장 틀 ③ ' · ' 같은 구분자로 나눈 조각."""
import json
import re
from pathlib import Path

DICT = json.loads((Path(__file__).resolve().parent / "i18n_dict.json").read_text(encoding="utf-8"))
NUM = re.compile(r"[+\-−]?\$?\d[\d,]*(?:\.\d+)?")
SEP = re.compile(r"( · | — | – | \| | → )")
HAN = re.compile("[가-힣]")
LANGS = ("en", "zh")


def norm(s):
    v = []

    def ph(m):
        v.append(m.group(0))
        return "{%d}" % (len(v) - 1)
    return NUM.sub(ph, re.sub(r"\s+", " ", s).strip()), v


SENT = re.compile(r"(?<=[.!?。])\s+(?=\S)")


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def fill(t, v):
    return re.sub(r"\{(\d+)\}", lambda m: v[int(m.group(1))] if int(m.group(1)) < len(v) else "", t)


def tl(s, lang):
    """한 문장 번역 (없으면 None) — 요약 문장을 언어별로 조립할 때 쓴다"""
    k, v = norm(s)
    t = (DICT.get(k) or {}).get(lang)
    return None if t is None else fill(t, v)


def tl_or(s, lang):
    return tl(s, lang) or s


def attach(obj, extra=None, skip=("band", "chart", "i18n", "i18n_missing", "paras")):
    """obj 안의 모든 한국어 문장에 대해, 화면이 쓸 번역표 {키: {en, zh}} 와 번역이 빠진 문장 틀 목록을 돌려준다.
    여러 문장이 이어진 글은 문장마다 번역해 다시 합친 결과를 '통째 문장' 키로 넣는다 (화면은 통째 문장부터 찾음)."""
    extra = {ws(k): v for k, v in (extra or {}).items()}
    out, miss = {}, set()

    def tr(s, rec):
        e = ws(s)
        if e in extra:
            return extra[e]
        k, v = norm(e)
        if k in DICT:
            out[k] = {L: DICT[k][L] for L in LANGS}          # 문장 틀도 같이 — 화면이 글을 조각으로 그려도 찾게
            return {L: fill(DICT[k][L], v) for L in LANGS}
        for sp, joins in ((SENT, {"en": " ", "zh": ""}), (SEP, None)):
            parts = sp.split(e)
            if len(parts) < 2:
                continue
            got = [p if (joins is None and i % 2) or not HAN.search(p) else tr(p, rec) for i, p in enumerate(parts)]
            if any(g is None for g in got):
                return None
            return {L: (joins[L] if joins else "").join(g if isinstance(g, str) else g[L] for g in got) for L in LANGS}
        if rec:
            miss.add(k)
        return None

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k not in skip:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and HAN.search(o):
            t = tr(o, True)
            if t:
                out[ws(o)] = t
    walk(obj)
    return out, sorted(miss)
