import json
import re
from itertools import product
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import BY_LINES, HOURS, SEASONS, TRIGRAMS, chart, classics, handle, relation, strength
from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def request(a="12", b="23", moving="6", **changes):
    return {"method": "three", "numbers": [a, b, moving], "season": "autumn", **changes}


def mutual_source(original: list[int], changed: list[int], upper, lower) -> list[int]:
    """AC6: pure 乾/坤 take the mutual from the changed lines; all others from the original."""
    pure = upper.number == lower.number and upper.name in ("乾", "坤")
    return changed if pure else original


def test_every_hexagram_and_moving_line():
    data = classics()
    assert len(data["hexagrams"]) == 64
    assert {entry["number"] for entry in data["hexagrams"].values()} == set(range(1, 65))
    for upper, lower, moving in product(TRIGRAMS, TRIGRAMS, range(1, 7)):
        result = chart(request(str(upper.number), str(lower.number), str(moving)))
        original = list(lower.lines + upper.lines)
        changed = original.copy()
        changed[moving - 1] ^= 1
        assert result["original"]["lines"] == original
        assert result["transformed"]["lines"] == changed
        assert sum(a != b for a, b in zip(original, changed)) == 1
        source = mutual_source(original, changed, upper, lower)
        assert result["mutual"]["lines"] == source[1:4] + source[2:5], (upper.name, lower.name, moving)
        assert result["body"]["number"] == (upper.number if moving <= 3 else lower.number)
        assert result["use"]["number"] == (lower.number if moving <= 3 else upper.number)
        assert result["moving_line"] == moving
        body_side = result["body_side"]
        assert result["transformed"][body_side] == result["body"]
        assert result["influences"][1]["trigram"] == result["mutual"][body_side]
        assert result["influences"][2]["trigram"] == result["mutual"][result["use_side"]]
        assert result["influences"][3]["trigram"] == result["transformed"][result["use_side"]]
        assert [item["title"] for item in result["texts"]] == [
            f"本卦 · {result['original']['name']}",
            f"动爻 · 第{moving}爻",
            f"变卦 · {result['transformed']['name']}",
        ]
        assert result["texts"][0]["passages"] == [
            {"label": "卦辞", "text": result["original"]["judgment"]},
            {"label": "彖辞", "text": result["original"]["tuan"]},
            {"label": "象辞", "text": result["original"]["xiang"]},
        ]
        assert result["texts"][1]["passages"] == [
            {"label": "爻辞", "text": result["original"]["line_texts"][moving - 1]},
            {"label": "象辞", "text": result["original"]["line_xiang"][moving - 1]},
        ]
        assert result["texts"][2]["passages"] == [
            {"label": "卦辞", "text": result["transformed"]["judgment"]},
            {"label": "彖辞", "text": result["transformed"]["tuan"]},
            {"label": "象辞", "text": result["transformed"]["xiang"]},
        ]
        assert all(item["source"].startswith("https://zh.wikisource.org/") for item in result["texts"])
        assert [item["stage"] for item in result["influences"]] == ["当下", "过程", "过程", "结果"]
        assert [item["role"] for item in result["influences"]] == ["本卦用卦", "体互", "用互", "变卦用卦"]
        for index, sentence in enumerate(result["original"]["line_texts"]):
            polarity = "九" if original[index] else "六"
            prefix = f"初{polarity}" if index == 0 else f"上{polarity}" if index == 5 else f"{polarity}{'二三四五'[index - 1]}"
            assert sentence.startswith(prefix), (result["original"]["name"], index, sentence)
        for name in ("original", "mutual", "transformed"):
            assert BY_LINES[tuple(result[name]["lines"][:3])].number == result[name]["lower"]["number"]
            assert BY_LINES[tuple(result[name]["lines"][3:])].number == result[name]["upper"]["number"]


def test_two_numbers_use_reduced_trigram_numbers_for_all_hours():
    for a, b, hour in product(range(17), range(17), range(1, 13)):
        result = chart({"method": "two", "numbers": [str(a), str(b)], "hour": hour, "season": "spring"})
        upper, lower = a % 8 or 8, b % 8 or 8
        assert result["original"]["upper"]["number"] == upper
        assert result["original"]["lower"]["number"] == lower
        assert result["moving_line"] == ((upper + lower + hour) % 6 or 6)
    result = chart({"method": "two", "numbers": ["8", "8"], "hour": 1, "season": "earth"})
    assert result["moving_line"] == 5
    assert result["original"]["name"] == "坤为地"
    assert result["mutual"]["name"] == "山地剥"
    assert result["transformed"]["name"] == "水地比"
    assert "notes" not in result


def test_regression_examples_precision_and_season_isolation():
    result = chart(request())
    assert result["original"]["name"] == "雷山小过"
    assert result["mutual"]["name"] == "泽风大过"
    assert result["transformed"]["name"] == "火山旅"
    assert result["influences"][0]["relation"] == "用克体"
    assert result["influences"][3]["relation"] == "用生体"
    plum = chart(request("2", "3", "1"))
    assert [plum[k]["name"] for k in ("original", "mutual", "transformed")] == ["泽火革", "天风姤", "泽山咸"]
    assert plum["body"]["name"] == "兑"
    assert [i["trigram"]["name"] for i in plum["influences"]] == ["离", "乾", "巽", "艮"]
    zeros = chart(request("0", "0", "0"))
    assert zeros["moving_line"] == 6
    assert zeros["original"]["name"] == "坤为地"
    large = "9" * 100
    big = chart(request(large, "9007199254740993", large))
    assert big["moving_line"] == (int(large) % 6 or 6)
    assert big["original"]["lower"]["number"] == 1
    assert big["request"]["numbers"][0] == large
    for season in SEASONS:
        seasonal = chart(request(season=season))
        assert seasonal["original"]["lines"] == result["original"]["lines"]
        assert seasonal["texts"] == result["texts"]
        assert seasonal["moving_line"] == result["moving_line"]


def test_all_element_relations_seasons_and_hours():
    generates = {("金", "水"), ("水", "木"), ("木", "火"), ("火", "土"), ("土", "金")}
    controls = {("金", "木"), ("木", "土"), ("土", "水"), ("水", "火"), ("火", "金")}
    for body, use in product("金木水火土", repeat=2):
        expected = "比和" if body == use else "用生体" if (use, body) in generates else "体生用" if (body, use) in generates else "体克用" if (body, use) in controls else "用克体"
        assert relation(body, use) == expected
    for season, expected in zip(SEASONS, ("木火水金土", "火土木水金", "金水土火木", "水木金土火", "土金火木水"), strict=True):
        assert "".join(next(e for e in "金木水火土" if strength(e, season) == state) for state in "旺相休囚死") == expected
    assert "".join(hour["branch"] for hour in HOURS) == "子丑寅卯辰巳午未申酉戌亥"
    assert [hour["number"] for hour in HOURS] == list(range(1, 13))
    assert HOURS[0]["range"] == "23:00–01:00"
    assert HOURS[-1]["range"] == "21:00–23:00"


FORBIDDEN_CATEGORIES = {
    "万物属类（第二章）", "卦宫八卦（原文）", "卦应（第十二章）", "八卦类象",
    "婚姻", "生产", "求名", "谋旺", "交易", "求利", "出行", "谒见", "官讼", "坟墓", "家宅",
}
DIVINATION_WORDS = ("吉", "凶", "宜", "忌", "利于", "不利", "主有", "占")
SURVIVING_ENTITIES = {
    "乾": ("天鹅", "良马", "老马", "瘠马", "驳马", "雪", "顶", "面颊", "丸子",
           "停尸", "贵官之眷", "有声名之家", "刑官", "武职", "驿官"),
    "兑": ("刑官", "武职", "伶官", "译官", "饮食不飧"),
    "离": ("文官", "文书考案之士"),
    "震": ("苍筤竹", "声名之家", "掌刑狱之官", "反生"),
    "巽": ("寡发", "广颡", "多白眼", "风宪"),
    "坎": ("美脊", "薄蹄", "鱼盐河泊之职", "宫律", "近水傍之墓"),
    "艮": ("小石", "阍寺", "百禽", "东北之穴", "山中之穴"),
    "坤": ("子母牛", "大舆", "百禽", "教官", "农官", "寡妇之家"),
}
SYNONYM_PAIRS = (
    ("首", "头"), ("西北", "西北方"), ("白", "白色"), ("果蓏", "瓜果"), ("甘味", "甘"),
    ("芋笋", "芋笋之物"), ("心疾", "心病"),
)
RESIDUAL_OUTCOMES = ("近利市三倍",)


def tokens(rows):
    return [token.strip() for row in rows for token in re.split(r"[、，。；,;]", row["text"]) if token.strip()]


def test_curated_imagery_is_entity_only_and_deduplicated():
    data = classics()
    assert set(data["images"]) == set("乾兑离震巽坎艮坤")
    assert "meihua" not in data["provenance"]
    for trigram in TRIGRAMS:
        rows = data["images"][trigram.name]
        assert rows, trigram.name
        categories = [row["category"] for row in rows]
        assert len(categories) == len(set(categories)), trigram.name
        assert not set(categories) & FORBIDDEN_CATEGORIES, (trigram.name, set(categories) & FORBIDDEN_CATEGORIES)
        assert not any(category.startswith("卦应补充") for category in categories), trigram.name
        for row in rows:
            assert set(row) == {"category", "text"}, row
            assert row["text"].strip()
            assert not re.search(r"第[一二三四五六七八九十]+章", row["category"] + row["text"]), row
            assert not any(word in row["text"] for word in DIVINATION_WORDS), (trigram.name, row)
        values = tokens(rows)
        duplicates = {value for value in values if values.count(value) > 1}
        assert not duplicates, (trigram.name, duplicates)
        for first, second in SYNONYM_PAIRS:
            assert not (first in values and second in values), (trigram.name, first, second)
        for entity in SURVIVING_ENTITIES.get(trigram.name, ()):
            assert entity in values, (trigram.name, entity)
        for outcome in RESIDUAL_OUTCOMES:
            assert outcome not in " ".join(values), (trigram.name, outcome)
        result = chart(request(str(trigram.number), str(trigram.number), "1"))
        for item in result["imagery"]:
            assert item["rows"] == rows
        assert "additional_rules" not in result
        assert "progression" not in result


def test_classical_commentary_is_complete_and_matches_source():
    data = classics()
    assert len(data["hexagrams"]) == 64
    for key, record in data["hexagrams"].items():
        for field in ("judgment", "tuan", "xiang"):
            assert record[field].strip(), (key, field)
            assert not record[field].startswith(("彖曰", "象曰")), (key, field)
        assert len(record["lines"]) == 6, key
        assert len(record["line_xiang"]) == 6, key
        assert all(text.strip() for text in record["line_xiang"]), key
        assert all("用九" not in text and "用六" not in text for text in record["lines"] + record["line_xiang"]), key
    assert sum(len(record["lines"]) for record in data["hexagrams"].values()) == 384
    assert sum(len(record["line_xiang"]) for record in data["hexagrams"].values()) == 384
    lv = data["hexagrams"]["1,2"]
    assert lv["name"] == "天泽履"
    assert lv["judgment"] == "履虎尾，不咥人，亨。"
    assert lv["tuan"] == "履，柔履刚也。说而应乎干，是以履虎尾，不咥人，亨。刚中正，履帝位而不疚，光明也。"
    assert lv["xiang"] == "上天下泽，履；君子以辨上下，定民志。"
    assert lv["lines"][2] == "六三：眇能视，跛能履，履虎尾，咥人，凶。武人为于大君。"
    assert lv["line_xiang"][2] == "眇能视，不足以有明也。跛能履，不足以与行也。咥人之凶，位不当也。武人为于大君，志刚也。"


def test_no_source_book_citations_remain_in_shipped_code_and_data():
    files = [
        *(ROOT / "app").rglob("*.py"), *(ROOT / "app" / "static").iterdir(),
        ROOT / "app" / "data" / "classics.json", ROOT / "scripts" / "import_classics.py",
        ROOT / "scripts" / "build_static_site.py", ROOT / "web" / "pyodide-backend.js", ROOT / "README.md",
    ]
    for path in files:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        assert "quanxue.cn" not in content, path
        assert "《梅花易数》" not in content, path
    assert "zh.wikisource.org" in (ROOT / "app" / "data" / "classics.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", [
    None, [], {}, request(method="invalid"), request(numbers=["1", "2"]),
    request(numbers=["1", "2", "3", "4"]), request(numbers=["-1", "2", "3"]),
    request(numbers=["1.5", "2", "3"]), request(numbers=["1e5", "2", "3"]),
    request(numbers=["", "2", "3"]), request(numbers=[True, "2", "3"]),
    request(numbers=["１", "2", "3"]), request(numbers=["1" * 101, "2", "3"]),
    request(numbers=[9007199254740992, "2", "3"]), request(numbers=[{}, "2", "3"]),
    request(season=None), request(season=[]), request(season="土"),
    request(question="a" * 501), request(question={}), request(hour=1),
    request(extra="ignored?"),
    {"method": "two", "numbers": ["1", "2"], "season": "spring"},
    {"method": "two", "numbers": ["1", "2"], "season": "spring", "hour": False},
    {"method": "two", "numbers": ["1", "2"], "season": "spring", "hour": 13},
    {"method": "two", "numbers": ["1", "2"], "season": "spring", "hour": 0},
])
def test_invalid_input_same_error_in_http_and_browser(payload):
    with TestClient(app) as client:
        response = client.post("/api/v1/chart", json=payload) if payload is not None else client.post("/api/v1/chart", content="null")
    browser = json.loads(handle("/api/v1/chart", json.dumps(payload)))
    assert response.status_code == browser["status"] == 422
    assert response.json() == browser["payload"]
    assert browser["ok"] is False
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"]


def test_http_browser_response_parity():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        for data in (request(), request("1", "1", "6"), request("9" * 100),
                     {"method": "two", "numbers": ["8", "8"], "hour": 1, "season": "earth"}):
            response = client.post("/api/v1/chart", json=data)
            browser = json.loads(handle("/api/v1/chart", json.dumps(data)))
            assert response.status_code == browser["status"] == 200
            assert response.json() == browser["payload"]
        for invalid in ("{", "", "[1,"):
            response = client.post("/api/v1/chart", content=invalid)
            assert response.status_code == 422
            assert response.json() == json.loads(handle("/api/v1/chart", invalid))["payload"]
        assert client.post("/api/v1/divinations", json={}).status_code == 404
    assert json.loads(handle("/unknown", "{}"))["status"] == 404
