import re
from zipfile import ZipFile

from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright
import pytest

from app.engine import chart
from app.main import app
from scripts.build_static_site import ENGINE_FILES, ROOT, build


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    with TestClient(app) as client:
        def route_request(route):
            response = client.request(
                route.request.method,
                route.request.url.removeprefix("http://meihua.test"),
                content=route.request.post_data,
                headers={"Content-Type": "application/json"},
            )
            route.fulfill(status=response.status_code, body=response.content, headers={"Content-Type": response.headers.get("content-type", "text/plain")})
        page.route("http://meihua.test/**", route_request)
        page.goto("http://meihua.test/")
        yield page
    page.close()
    assert not errors, errors


def fill_two(page, a="12", b="23", hour="1", season="autumn"):
    page.locator("#number-1").fill(a)
    page.locator("#number-2").fill(b)
    page.locator("#hour").select_option(hour)
    page.locator("#season").select_option(season)


def test_form_modes_order_full_text_and_no_stale_results(page):
    fill_two(page)
    page.locator("#question").fill('<img src=x onerror="alert(1)">')
    page.locator("#chart-button").click()
    expect(page.locator("#result")).to_be_visible()
    expect(page.locator(".hexagram-name")).to_have_text(["雷山小过 · 第62卦", "泽风大过 · 第28卦", "火山旅 · 第56卦"])
    assert page.locator("#result h2").all_text_contents() == ["盘", "吉凶判定", "卦象", "卦爻辞"]
    assert page.locator("#result").evaluate("""node => {
      let heading = "";
      return Array.from(node.children).flatMap(child => {
        if (child.tagName === "H2") heading = child.textContent;
        return child.matches(".hexagrams, .table-wrap, details, .classical")
          ? [heading] : [];
      });
    }""") == ["盘", "吉凶判定", "卦象", "卦爻辞", "卦爻辞", "卦爻辞"]
    assert page.locator(".hexagram h3").all_text_contents() == ["本卦", "互卦", "变卦"]
    assert page.locator("#result img").count() == 0
    assert page.locator("#result .rules").count() == 0
    body = page.locator("#result").inner_text()
    for removed in (
        "排盘过程与取法", "生克关系与旺衰依据", "原书", "《梅花易数》", "quanxue.cn", "卦宫万物属类",
        "爻位从下往上数", "互卦取二三四爻", "不是死亡预测",
    ):
        assert removed not in body, removed
    data = chart({"method": "two", "numbers": ["12", "23"], "hour": 1, "season": "autumn"})
    for item in data["imagery"]:
        for row in item["rows"]:
            assert row["text"] in page.locator(".imagery").inner_text()
    assert page.locator(".imagery thead th").first.inner_text() == "类别"
    assert "宫" not in page.locator(".imagery thead").inner_text()
    influences = page.locator(".influences")
    assert influences.locator("thead th").all_text_contents() == [
        "阶段", "体", "用", "体用生克", "通则倾向", "旺衰修正",
    ]
    rows = influences.locator("tbody tr")
    assert rows.count() == 4
    assert [rows.nth(i).locator("th, td").nth(0).inner_text() for i in range(4)] == ["当下", "过程", "过程", "结果"]
    for index, role in enumerate(["本卦用卦", "体互", "用互", "变卦用卦"]):
        assert rows.nth(index).locator("th, td").nth(1).inner_text() == data["body"]["image"]
        use_cell = rows.nth(index).locator("th, td").nth(2).inner_text()
        assert role in use_cell and data["influences"][index]["trigram"]["image"] in use_cell
    for label in page.locator(".hexagram small").all_text_contents():
        assert not set(label) & set("乾兑离震巽坎艮坤"), label
        assert "/" not in label, label
    assert page.locator(".classical h3").all_text_contents() == [item["title"] for item in data["texts"]]
    quotes = page.locator(".classical blockquote")
    assert quotes.count() == 3
    for index, item in enumerate(data["texts"]):
        quote = quotes.nth(index).inner_text()
        assert quotes.nth(index).locator("strong").all_text_contents() == [
            entry["label"] for entry in item["passages"]
        ]
        positions = []
        for passage in item["passages"]:
            assert passage["text"] in quote
            positions.append(quote.index(passage["label"]))
        assert positions == sorted(positions), (index, quote)
    assert page.locator(".classical a").count() == 3
    assert page.locator(".classical a").first.get_attribute("href").startswith("https://zh.wikisource.org/")
    assert page.locator('[data-kind="original"] .moving').get_attribute("data-position") == "6"
    assert page.locator('[data-kind="mutual"] .moving').count() == 0
    page.locator('[name="method"][value="three"]').check()
    expect(page.locator("#result")).to_be_hidden()
    expect(page.locator("#hour")).to_be_disabled()
    expect(page.locator("#number-3")).to_be_enabled()
    assert page.locator("#number-3").get_attribute("required") is not None
    page.locator("#number-3").fill("1")
    page.locator("#chart-button").click()
    expect(page.locator("#result")).to_be_visible()
    assert page.locator('[data-kind="original"] .moving').get_attribute("data-position") == "1"
    page.locator("#number-1").fill("8")
    expect(page.locator("#result")).to_be_hidden()
    assert page.locator("#result").inner_text() == ""
    page.locator('[name="method"][value="two"]').check()
    expect(page.locator("#number-3")).to_be_disabled()
    expect(page.locator("#hour")).to_be_enabled()


def test_mobile_big_numbers_errors_and_accessible_lines(page):
    page.set_viewport_size({"width": 375, "height": 812})
    fill_two(page, "8", "8")
    page.locator("#chart-button").click()
    expect(page.locator("#result")).to_be_visible()
    assert page.locator('[data-kind="original"] .yao').count() == 6
    assert page.locator('[data-kind="original"] .moving').get_attribute("aria-label") == "五爻，阴爻，动爻"
    assert page.locator('[data-kind="transformed"] .moving').get_attribute("aria-label") == "五爻，阳爻，变爻"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.locator("#number-1").fill("9" * 100)
    page.locator("#chart-button").click()
    expect(page.locator("#result")).to_be_visible()
    assert "9" * 100 in page.locator("#result").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.evaluate("() => { window.meihuaBackend = async () => ({ok: false, status: 422, payload: {detail: '明确的输入错误'}}); }")
    page.locator("#chart-button").click()
    expect(page.locator("#error")).to_contain_text("明确的输入错误")
    expect(page.locator("#result")).to_be_hidden()
    expect(page.locator("#chart-button")).to_be_enabled()
    page.locator("#number-1").fill("-1")
    assert page.locator("#number-1").evaluate("(input) => !input.checkValidity()")


def test_reject_response_if_inputs_change_while_waiting(page):
    fill_two(page)
    page.evaluate("() => { window.meihuaBackend = () => new Promise(resolve => { window.finishChart = resolve; }); }")
    page.locator("#chart-button").click()
    page.locator("#number-1").fill("13")
    data = chart({"method": "two", "numbers": ["12", "23"], "hour": 1, "season": "autumn"})
    page.evaluate("(data) => window.finishChart({ok: true, status: 200, payload: data})", data)
    expect(page.locator("#chart-button")).to_be_enabled()
    expect(page.locator("#result")).to_be_hidden()
    assert page.locator("#result").inner_text() == ""


def test_static_build_parity_and_reproducibility(tmp_path):
    build(tmp_path)
    first = (tmp_path / "static/meihua-engine.zip").read_bytes()
    build(tmp_path)
    assert first == (tmp_path / "static/meihua-engine.zip").read_bytes()
    with ZipFile(tmp_path / "static/meihua-engine.zip") as archive:
        assert set(archive.namelist()) == set(ENGINE_FILES)
        for name in ENGINE_FILES:
            assert archive.read(name) == (ROOT / name).read_bytes()
    for name in ("app.js", "styles.css"):
        assert (tmp_path / "static" / name).read_bytes() == (ROOT / "app/static" / name).read_bytes()
    html = (tmp_path / "index.html").read_text()
    assert html.index("pyodide-backend.js") < html.index("app.js")
    for path in re.findall(r'(?:src|href)="(static/[^"]+)"', html):
        assert (tmp_path / path).is_file()
    assert (tmp_path / ".nojekyll").exists()


def test_static_startup_failure_is_visible_without_submission(browser, tmp_path):
    build(tmp_path)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    def serve(route):
        path = route.request.url.removeprefix("http://static.test/meihua/")
        if path == "static/runtime-manifest.json":
            route.fulfill(status=503, body="Unavailable")
            return
        file = tmp_path / (path or "index.html")
        content_type = "text/javascript" if file.suffix == ".js" else "text/css" if file.suffix == ".css" else "text/html"
        route.fulfill(status=200, body=file.read_bytes(), content_type=content_type)
    page.route("http://static.test/meihua/**", serve)
    page.goto("http://static.test/meihua/")
    expect(page.locator("#runtime-status")).to_contain_text("HTTP 503")
    fill_two(page)
    page.locator("#chart-button").click()
    expect(page.locator("#error")).to_contain_text("HTTP 503")
    expect(page.locator("#chart-button")).to_be_enabled()
    assert not errors
    page.close()


def test_form_prose_removed_but_controls_and_accessibility_intact(page):
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    for removed in (
        "传统文化研习工具", "以数起卦，静体动用", "接受0及非负整数", "四时旺衰",
        "月令不等于公历月份", "由你选择，不按设备时间推定", "各时段含起点、不含终点",
        "《梅花易数》", "quanxue.cn",
    ):
        assert removed not in html, removed
    described = set(re.findall(r'aria-describedby="([^"]+)"', html))
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert described <= ids, described - ids
    assert page.locator("#method-description").inner_text() != ""
    page.locator('[name="method"][value="three"]').check()
    assert "不加时辰或前两数" not in page.locator("#method-description").inner_text()
    assert page.locator('label[for="season"]').inner_text().strip() == "月令"
    for selector in ("#number-1", "#number-2", "#season", "#question"):
        assert page.locator(selector).count() == 1
    assert page.locator("#number-1").get_attribute("pattern") == "[0-9]{1,100}"
    assert page.locator("#number-1").get_attribute("required") is not None


def test_trigram_labels_are_image_only_with_role_and_no_strength(page):
    """AC8: exact standalone labels; strength survives only in the judgment table."""
    fill_two(page)
    page.locator("#chart-button").click()
    expect(page.locator("#result")).to_be_visible()
    assert "第6爻动 · 体：山 · 用：雷" in page.locator("#result").inner_text()
    assert page.locator('[data-kind="original"] small').all_text_contents() == ["上卦：雷 · 用", "下卦：山 · 体"]
    assert page.locator('[data-kind="mutual"] small').all_text_contents() == ["上卦：泽 · 用互", "下卦：风 · 体互"]
    assert page.locator('[data-kind="transformed"] small').all_text_contents() == ["上卦：火 · 变用", "下卦：山 · 体"]
    labels = page.locator(".hexagram small").all_text_contents()
    labels.append(page.locator("#result p").nth(1).inner_text())
    for label in labels:
        assert not set(label) & set("旺相休囚死"), label
    qualifications = page.locator(".influences tbody tr td:last-child").all_text_contents()
    assert any(set(text) & set("旺相休囚死") for text in qualifications), qualifications
