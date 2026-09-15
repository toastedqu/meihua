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
SOURCE_ROOT = "https://www.quanxue.cn/qt_mingxiang/meihua/"
RELATIONS = {
    "比和": ("偏吉", "体用同五行，比和相助，传统通则以顺遂论。"),
    "用生体": ("偏吉", "用卦生体，传统通则以进益、得助论。"),
    "体克用": ("偏吉而须有力", "体卦克用，传统人事通则以可制、可成论；仍须体有力，部分分占另论迟速。"),
    "体生用": ("偏凶·耗泄", "体卦生用，体气向外耗泄，传统通则以付出、耗失论。"),
    "用克体": ("偏凶·受克", "用卦克体，传统通则以受制、有阻论；须兼看体旺衰及是否得生。"),
}
ADDITIONAL_RULES = [
    {
        "title": "乾坤无互，互其变卦",
        "chapter": 2,
        "section": "互卦起例",
        "summary": "原文另列纯乾、纯坤从变卦取互的特殊说法。",
        "status": "本系统统一从本卦二三四爻取下互、三四五爻取上互；遇纯乾坤提示异例，不自动改盘。",
    },
    {
        "title": "体互、用互与终应",
        "chapter": 10,
        "section": "体用互变之诀",
        "summary": "与原体同侧的互卦叫体互，另一侧叫用互；体互较切。用为当下，互为中间，变为终应。",
        "status": "已标明体互、用互；互变始终相对本卦之体判断，不另立一个新体。",
    },
    {
        "title": "旺衰、党众与生克制化",
        "chapter": 8,
        "section": "体用、衰旺论",
        "summary": "体宜旺，生体之卦宜旺，克体之卦宜衰；生体者受克会减助，克体者受制可缓解，不能只数吉凶。",
        "status": "已列旺衰及用、互、变生克明细；党众、制化不机械打分，也不凭多数直接翻转结论。",
    },
    {
        "title": "十八类分占不是同一套断语",
        "chapter": 6,
        "section": "天时至坟墓十八占",
        "summary": "含天时、人事、家宅、屋舍、婚姻、生产、饮食、求谋、求名、求财、交易、出行、行人、谒见、失物、疾病、官讼、坟墓。天时不分体用；饮食、生产等不能套用体克用皆吉。",
        "status": "只自动给一般人事通则，不解析问题、不生成各类专断；古代医药、产育、诉讼断语仅作文献，不作现实建议。",
    },
    {
        "title": "三要、十应与内外合参",
        "chapter": 13,
        "section": "占卜十应诀",
        "summary": "除正、互、变应，还有方应、日应、刻应、外应、天时、地理、人事；须结合耳闻目见及其与体的关系。",
        "status": "未采集外应及日辰，不假装完成十应判断；静处无外应时可只论内卦。",
    },
    {
        "title": "外应的真生真克、轻重与向背",
        "chapter": 10,
        "section": "体用生克之诀",
        "summary": "实际火焰与仅有红色的物象不等量；外物来去、动静也有差别，向背另见第七章。",
        "status": "未自动化。数字输入无法提供这些条件，不从问题文字猜测外应。",
    },
    {
        "title": "应期与动静迟速",
        "chapter": 10,
        "section": "占卜克应之诀",
        "summary": "可参生克体之卦气、卦数、事物久暂，以及行坐卧等迟速；不同事项不能一律按天计算。",
        "status": "仅给当下／过程／结果，不虚构应验日期。",
    },
    {
        "title": "其他起卦、加姓数、观物与器物",
        "chapter": 9,
        "section": "起卦加数例、器物占",
        "summary": "另有年月日时、物数、声音、字数笔画、尺寸、方位、颜色起卦及同一时刻加姓数区分；也有器物成毁、射覆、饮食和宅气规则。",
        "status": "只实现指定双数／三数法，不额外加时、加姓数；观物细则另见第十、十一章。",
    },
    {
        "title": "卦爻辞、易理与不拘体用",
        "chapter": 5,
        "section": "先天后天论、卦断遗论、占卜论理诀",
        "summary": "先得数与先得象的侧重点不同；同一卦不能反复照搬同一具体故事，还须审理、卦义、爻辞及所问事项。",
        "status": "卦爻辞完整列在类象之后，供独立阅读，不用关键词扫描替代解读。",
    },
]


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
    tendency, explanation = RELATIONS[kind]
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
        "relation": kind, "tendency": tendency, "explanation": explanation,
        "qualification": qualifier,
        "source": f"{SOURCE_ROOT}meihua05.html",
        "strength_source": f"{SOURCE_ROOT}meihua08.html",
    }


def chart(payload: Any) -> dict[str, Any]:
    request = validate(payload)
    a, b, *third = request["numbers"]
    upper, lower = TRIGRAMS[reduced(a, 8) - 1], TRIGRAMS[reduced(b, 8) - 1]
    total = upper.number + lower.number + request["hour"] if request["method"] == "two" else third[0]
    moving = reduced(total, 6)
    lines = lower.lines + upper.lines
    changed = tuple(1 - line if i == moving - 1 else line for i, line in enumerate(lines))
    nuclear = lines[1:4] + lines[2:5]
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
        influence(body, changed_use, "结果", "变卦之用", season),
    ]
    favorable = {"比和", "用生体", "体克用"}
    start, end = [item["relation"] in favorable for item in (influences[0], influences[-1])]
    progression = {
        (True, True): "当下与结果的生克关系均偏顺，仍须参看过程及旺衰。",
        (True, False): "当下偏顺，结果转见耗泄或受克，属先顺后有阻的结构。",
        (False, True): "当下见耗泄或受克，结果转向生体、比和或体克用，属先阻后转顺的结构。",
        (False, False): "当下与结果均见耗泄或受克，过程中的生体、比和可作缓解因素，不能据此保证转吉。",
    }[(start, end)]
    formulas = [
        f"上卦：{a} ÷ 8 余 {a % 8}" + ("，余0作8" if a % 8 == 0 else "") + f" → {upper.name}（{upper.number}）。",
        f"下卦：{b} ÷ 8 余 {b % 8}" + ("，余0作8" if b % 8 == 0 else "") + f" → {lower.name}（{lower.number}）。",
    ]
    if request["method"] == "two":
        formulas.append(f"动爻：用折算后的卦数 {upper.number} + {lower.number} + 时辰数 {request['hour']} = {total}；{total} ÷ 6 余 {total % 6}" + ("，余0作6" if total % 6 == 0 else "") + f" → 第{moving}爻。")
    else:
        formulas.append(f"动爻：第三数 {total} ÷ 6 余 {total % 6}" + ("，余0作6" if total % 6 == 0 else "") + f" → 第{moving}爻；不加前两数或时辰。")
    notes = [
        "爻位从下往上数：初、二、三、四、五、上。动爻所在三爻卦为用，另一卦为体。",
        "互卦取本卦二三四爻为下卦、三四五爻为上卦；变卦仅翻转动爻的阴阳。",
        "以下仅为一般人事的体用通则。天时、生产、饮食等分占有例外，不能据此直接套断。",
        "旺衰严格使用所选月令及给定五行表。这里的“死”是传统旺衰名称，不是死亡预测。",
    ]
    if upper == lower and upper.name in ("乾", "坤"):
        notes.append("本卦为纯乾／纯坤：本页仍按本卦取互。原书另载“乾坤无互，互其变卦”，未自动启用该异例。")
    imagery = [
        {"role": role, "trigram": trigram_info(trigram, season), "rows": classics()["images"][trigram.name]}
        for role, trigram in (("体卦", body), ("用卦", use))
    ]
    return {
        "request": {**request, "numbers": [str(n) for n in request["numbers"]]},
        "hour": HOURS[request["hour"] - 1] if request["hour"] else None,
        "season": {"key": season, "label": SEASONS[season][0],
                   "strengths": dict(zip("旺相休囚死", SEASONS[season][1], strict=True))},
        "moving_line": moving, "body": trigram_info(body, season), "use": trigram_info(use, season),
        "body_side": body_side, "use_side": use_side,
        "original": original, "mutual": mutual, "transformed": transformed,
        "formulas": formulas, "influences": influences,
        "summary": f"{influences[0]['relation']}：{influences[0]['tendency']}。",
        "progression": progression, "notes": notes, "imagery": imagery,
        "texts": [
            {"label": "本卦卦辞", "name": original["name"], "text": original["judgment"], "source": original["source"]},
            {"label": "动爻爻辞", "name": f"{original['name']} · 第{moving}爻", "text": original["line_texts"][moving - 1], "source": original["source"]},
            {"label": "变卦卦辞", "name": transformed["name"], "text": transformed["judgment"], "source": transformed["source"]},
        ],
        "additional_rules": [{**rule, "source": f"{SOURCE_ROOT}meihua{rule['chapter']:02}.html"} for rule in ADDITIONAL_RULES],
        "provenance": classics()["provenance"],
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
