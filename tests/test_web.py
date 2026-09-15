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
    assert page.locator("#result h2").all_text_contents() == [
        "卦象 · 本卦、互卦、变卦", "体用生克 · 大体吉凶", "体卦、用卦 · 卦宫万物属类",
        "卦辞与动爻爻辞", "原书另有的规则与本页边界",
    ]
    assert page.locator("#result img").count() == 0
    data = chart({"method": "two", "numbers": ["12", "23"], "hour": 1, "season": "autumn"})
    for item in data["imagery"]:
        for row in item["rows"]:
            assert row["text"] in page.locator(".imagery").inner_text()
    assert page.locator(".classical blockquote").all_text_contents() == [item["text"] for item in data["texts"]]
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
