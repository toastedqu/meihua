from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class Trigram:
    number: int
    name: str
    image: str
    element: str
    lines: tuple[int, int, int]


# Line order is always bottom to top, including the lower trigram first.
TRIGRAMS = (
    Trigram(1, "乾", "天", "金", (1, 1, 1)),
    Trigram(2, "兑", "泽", "金", (1, 1, 0)),
    Trigram(3, "离", "火", "火", (1, 0, 1)),
    Trigram(4, "震", "雷", "木", (1, 0, 0)),
    Trigram(5, "巽", "风", "木", (0, 1, 1)),
    Trigram(6, "坎", "水", "水", (0, 1, 0)),
    Trigram(7, "艮", "山", "土", (0, 0, 1)),
    Trigram(8, "坤", "地", "土", (0, 0, 0)),
)
BY_LINES = {trigram.lines: trigram for trigram in TRIGRAMS}
GENERATES = dict(zip("金水木火土", "水木火土金", strict=True))
CONTROLS = dict(zip("金木土水火", "木土水火金", strict=True))
SEASONS = {
    "spring": ("春（寅卯辰月）", "木火水金土"),
    "summer": ("夏（巳午未月）", "火土木水金"),
    "autumn": ("秋（申酉戌月）", "金水土火木"),
    "winter": ("冬（亥子丑月）", "水木金土火"),
    "earth": ("四季（辰戌丑未月末各十八天）", "土金火木水"),
}
HOURS = [
    {"number": i + 1, "branch": branch, "range": period}
    for i, (branch, period) in enumerate(zip(
        "子丑寅卯辰巳午未申酉戌亥",
        ("23:00–01:00", "01:00–03:00", "03:00–05:00", "05:00–07:00",
         "07:00–09:00", "09:00–11:00", "11:00–13:00", "13:00–15:00",
         "15:00–17:00", "17:00–19:00", "19:00–21:00", "21:00–23:00"),
        strict=True,
    ))
]
RELATIONS = {
    "比和": "偏吉",
    "用生体": "偏吉",
    "体克用": "偏吉而须有力",
    "体生用": "偏凶·耗泄",
    "用克体": "偏凶·受克",
}


class InputError(ValueError):
    pass


@lru_cache(maxsize=1)
def classics() -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "data" / "classics.json").read_text(encoding="utf-8"))


def reduced(value: int, modulus: int) -> int:
    return value % modulus or modulus


def parse_number(value: Any, label: str) -> int:
    if type(value) is int:
        # JavaScript cannot transmit larger numeric literals exactly; strings can.
        if not 0 <= value <= 9_007_199_254_740_991:
            raise InputError(f"{label}必须为非负安全整数；更大的数字请以字符串提交（最多100位）。")
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,100}", value.strip()):
        return int(value.strip())
    raise InputError(f"{label}须为0或非负整数，最多100位；不接受负数、小数、科学计数法或空值。")


def validate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("请求必须是JSON对象。")
    unknown = payload.keys() - {"method", "numbers", "hour", "season", "question"}
    if unknown:
        raise InputError(f"未知字段：{'、'.join(sorted(unknown))}。")
    method = payload.get("method")
    if method not in ("two", "three"):
        raise InputError("请选择双数法或三数法。")
    numbers = payload.get("numbers")
    count = 2 if method == "two" else 3
    if not isinstance(numbers, list) or len(numbers) != count:
        raise InputError(f"{'双' if count == 2 else '三'}数法必须提供{count}个数字。")
    parsed = [parse_number(value, f"第{i + 1}数") for i, value in enumerate(numbers)]
    hour = payload.get("hour")
    if method == "two":
        if type(hour) is not int or not 1 <= hour <= 12:
            raise InputError("双数法必须从十二时辰中选择时辰（1至12）。")
    elif hour is not None:
        raise InputError("三数法不使用时辰，请勿提交hour。")
    season = payload.get("season")
    if not isinstance(season, str) or season not in SEASONS:
        raise InputError("请选择月令；四季指辰戌丑未月末各十八天，不是整个土月。")
    question = payload.get("question", "")
    if not isinstance(question, str) or len(question) > 500:
        raise InputError("所占之事必须是500字以内的文字。")
    return {"method": method, "numbers": parsed, "hour": hour, "season": season, "question": question.strip()}


def relation(body: str, other: str) -> str:
    if body == other:
        return "比和"
    if GENERATES[other] == body:
        return "用生体"
    if GENERATES[body] == other:
        return "体生用"
    return "体克用" if CONTROLS[body] == other else "用克体"


def strength(element: str, season: str) -> str:
    return "旺相休囚死"[SEASONS[season][1].index(element)]


def trigram_info(trigram: Trigram, season: str) -> dict[str, Any]:
    return {**asdict(trigram), "strength": strength(trigram.element, season)}


def hexagram(lines: tuple[int, ...], season: str) -> dict[str, Any]:
    lower, upper = BY_LINES[lines[:3]], BY_LINES[lines[3:]]
    record = classics()["hexagrams"][f"{upper.number},{lower.number}"]
    return {
        **record, "lines": list(lines), "line_texts": record["lines"],
        "upper": trigram_info(upper, season), "lower": trigram_info(lower, season),
    }


def influence(body: Trigram, other: Trigram, stage: str, role: str, season: str) -> dict[str, Any]:
    kind = relation(body.element, other.element)
    tendency = RELATIONS[kind]
    own_strength, other_strength = strength(body.element, season), strength(other.element, season)
    if kind == "用生体":
        qualifier = "生体者旺相，助力得时。" if other_strength in "旺相" else "虽见生体，生体者休囚死，助力不宜夸大。"
    elif kind == "用克体":
        qualifier = ("克体者旺相，受制之势需留意。" if other_strength in "旺相" else "克体者休囚死，其克力按时令减看。")
        qualifier += "体旺相，较能承受。" if own_strength in "旺相" else "体亦休囚死，承受力不足。"
    elif kind == "体克用":
        qualifier = "体旺相，较有制用之力。" if own_strength in "旺相" else "体休囚死，不可只凭体克用便断成事。"
    elif kind == "体生用":
        qualifier = "体旺相而向外泄气，仍有付出。" if own_strength in "旺相" else "体休囚死又泄气，耗损更须留意。"
    else:
        qualifier = "同气得时，相助较有力。" if own_strength in "旺相" else "虽同气相助，但皆未得旺相，不等于力量充足。"
    return {
        "stage": stage, "role": role, "trigram": trigram_info(other, season),
        "relation": kind, "tendency": tendency, "qualification": qualifier,
    }


def chart(payload: Any) -> dict[str, Any]:
    request = validate(payload)
    a, b, *third = request["numbers"]
    upper, lower = TRIGRAMS[reduced(a, 8) - 1], TRIGRAMS[reduced(b, 8) - 1]
    total = upper.number + lower.number + request["hour"] if request["method"] == "two" else third[0]
    moving = reduced(total, 6)
    lines = lower.lines + upper.lines
    changed = tuple(1 - line if i == moving - 1 else line for i, line in enumerate(lines))
    # 乾坤无互，互其变卦：pure 乾 and pure 坤 take the nuclear lines from the transformed hexagram.
    pure = upper == lower and upper.name in ("乾", "坤")
    base = changed if pure else lines
    nuclear = base[1:4] + base[2:5]
    body, use = (upper, lower) if moving <= 3 else (lower, upper)
    body_side = "upper" if moving <= 3 else "lower"
    use_side = "lower" if moving <= 3 else "upper"
    season = request["season"]
    original, mutual, transformed = [hexagram(bits, season) for bits in (lines, nuclear, changed)]
    mutual_body = BY_LINES[nuclear[3:] if body_side == "upper" else nuclear[:3]]
    mutual_use = BY_LINES[nuclear[:3] if body_side == "upper" else nuclear[3:]]
    changed_use = BY_LINES[changed[:3] if use_side == "lower" else changed[3:]]
    influences = [
        influence(body, use, "当下", "本卦用卦", season),
        influence(body, mutual_body, "过程", "体互", season),
        influence(body, mutual_use, "过程", "用互", season),
        influence(body, changed_use, "结果", "变卦用卦", season),
    ]
    imagery = [
        {"role": role, "trigram": trigram_info(trigram, season), "rows": classics()["images"][trigram.name]}
        for role, trigram in (("体卦", body), ("用卦", use))
    ]

    def article(title: str, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": title,
            "passages": [
                {"label": "卦辞", "text": record["judgment"]},
                {"label": "彖辞", "text": record["tuan"]},
                {"label": "象辞", "text": record["xiang"]},
            ],
            "source": record["source"],
        }

    return {
        "request": {**request, "numbers": [str(n) for n in request["numbers"]]},
        "hour": HOURS[request["hour"] - 1] if request["hour"] else None,
        "season": {"key": season, "label": SEASONS[season][0]},
        "moving_line": moving, "body": trigram_info(body, season), "use": trigram_info(use, season),
        "body_side": body_side, "use_side": use_side,
        "original": original, "mutual": mutual, "transformed": transformed,
        "influences": influences, "imagery": imagery,
        "texts": [
            article(f"本卦 · {original['name']}", original),
            {
                "title": f"动爻 · 第{moving}爻",
                "passages": [
                    {"label": "爻辞", "text": original["line_texts"][moving - 1]},
                    {"label": "象辞", "text": original["line_xiang"][moving - 1]},
                ],
                "source": original["source"],
            },
            article(f"变卦 · {transformed['name']}", transformed),
        ],
    }


def dispatch(path: str, payload: Any) -> tuple[int, dict[str, Any]]:
    if path != "/api/v1/chart":
        return 404, {"detail": "Not Found"}
    try:
        return 200, chart(payload)
    except InputError as error:
        return 422, {"detail": str(error)}


def handle(path: str, request_json: str) -> str:
    try:
        payload = json.loads(request_json)
    except json.JSONDecodeError:
        status, result = 422, {"detail": "请求不是有效的JSON。"}
    else:
        status, result = dispatch(path, payload)
    return json.dumps({"status": status, "ok": status < 400, "payload": result}, ensure_ascii=False)
