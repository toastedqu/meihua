import json
from itertools import product

import pytest
from fastapi.testclient import TestClient

from app.engine import BY_LINES, HOURS, SEASONS, TRIGRAMS, chart, classics, handle, relation, strength
from app.main import app


def request(a="12", b="23", moving="6", **changes):
    return {"method": "three", "numbers": [a, b, moving], "season": "autumn", **changes}


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
        assert result["mutual"]["lines"] == original[1:4] + original[2:5]
        assert result["body"]["number"] == (upper.number if moving <= 3 else lower.number)
        assert result["use"]["number"] == (lower.number if moving <= 3 else upper.number)
        assert result["moving_line"] == moving
        body_side = result["body_side"]
        assert result["transformed"][body_side] == result["body"]
        assert result["influences"][1]["trigram"] == result["mutual"][body_side]
        assert result["influences"][2]["trigram"] == result["mutual"][result["use_side"]]
        assert result["influences"][3]["trigram"] == result["transformed"][result["use_side"]]
        assert result["texts"][0]["text"] == result["original"]["judgment"]
        assert result["texts"][1]["text"] == result["original"]["line_texts"][moving - 1]
        assert result["texts"][2]["text"] == result["transformed"]["judgment"]
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
    assert result["mutual"]["name"] == "坤为地"
    assert result["transformed"]["name"] == "水地比"
    assert "乾坤无互" in result["notes"][-1]


def test_regression_examples_precision_and_season_isolation():
    result = chart(request())
    assert result["original"]["name"] == "雷山小过"
    assert result["mutual"]["name"] == "泽风大过"
    assert result["transformed"]["name"] == "火山旅"
    assert result["influences"][0]["relation"] == "用克体"
    assert result["influences"][3]["relation"] == "用生体"
    assert "先阻后转顺" in result["progression"]
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


def test_imagery_is_complete_and_rules_have_sources():
    data = classics()
    assert set(data["images"]) == set("乾兑离震巽坎艮坤")
    for trigram in TRIGRAMS:
        result = chart(request(str(trigram.number), str(trigram.number), "1"))
        for item in result["imagery"]:
            assert item["rows"] == data["images"][trigram.name]
            assert len(item["rows"]) >= 29
            categories = [row["category"] for row in item["rows"]]
            assert len(categories) == len(set(categories))
            assert all(row["text"] for row in item["rows"])
        assert len(result["additional_rules"]) == 9
        assert all(rule["source"].startswith("https://www.quanxue.cn/") for rule in result["additional_rules"])


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
