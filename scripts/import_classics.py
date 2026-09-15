"""Import only public-domain classical passages, never modern translations.

Run explicitly to refresh the checked-in dataset; neither builds nor requests
scrape websites. Source HTML is cached outside the application.
"""

from __future__ import annotations

import argparse
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
MEIHUA = "https://www.quanxue.cn/qt_mingxiang/meihua/"
WIKI = "https://zh.wikisource.org"
TRIGRAMS = "乾兑离震巽坎艮坤"
SYMBOLS = dict(zip(TRIGRAMS, "天泽火雷风水山地", strict=True))
NORMALIZE = str.maketrans("兌離歸節損臨豐濟賁隨頤復過蠱訟渙師遯漸謙晉觀剝壯", "兑离归节损临丰济贲随颐复过蛊讼涣师遁渐谦晋观剥壮")


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def text(html: str) -> str:
    parser = TextParser()
    parser.feed(html)
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


class BluePassages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []
        self.passages: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "span":
            if self.depth or "color:blue" in dict(attrs).get("style", "").replace(" ", ""):
                self.depth += 1

    def handle_endtag(self, tag):
        if tag == "span" and self.depth:
            self.depth -= 1
            if not self.depth:
                value = re.sub(r"\s+", " ", "".join(self.parts)).strip()
                if value:
                    self.passages.append(value)
                self.parts = []

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


def fetch(url: str, cache: Path, name: str) -> str:
    destination = cache / name
    if not destination.exists():
        time.sleep(3)
        content = subprocess.check_output(
            ["curl", "--fail", "--silent", "--show-error", "--location",
             "--max-time", "45", "--retry", "3", "--retry-all-errors", "--retry-delay", "10", url],
            text=True,
        )
        destination.write_text(content, encoding="utf-8")
    return destination.read_text(encoding="utf-8")


def parse_hexagram(html: str, title: str, url: str) -> tuple[str, dict]:
    parser = BluePassages()
    parser.feed(html)
    passages = [p for p in parser.passages if p not in ("易经：", "易經：")]
    # A single moving line never uses Qian's 用九 or Kun's 用六.
    lines = [p for p in passages if re.match(r"^(初[九六]|[九六][二三四五]|上[九六])[：:，]", p)]
    judgments = [p for p in passages if not re.match(r"^(初[九六]|[九六][二三四五]|上[九六]|用[九六])[：:，]", p)]
    pair = re.search(r"([乾兑离震巽坎艮坤])下\s*([乾兑离震巽坎艮坤])上", text(html).translate(NORMALIZE).replace("干下", "乾下").replace("干上", "乾上"))
    number = re.search(r"第([一二三四五六七八九十]+)卦", text(html))
    revision = re.search(r'"wgRevisionId":(\d+)', html)
    expected_judgments = 3 if title == "坤" else 1
    if len(lines) != 6 or len(judgments) != expected_judgments or not pair or not number or not revision:
        raise ValueError(f"{title}: incomplete source: {len(lines)} lines, {len(judgments)} judgments, pair={pair}")
    lower, upper = pair.groups()
    short = title.translate(NORMALIZE)
    name = f"{upper}为{SYMBOLS[upper]}" if upper == lower else f"{SYMBOLS[upper]}{SYMBOLS[lower]}{short}"
    key = f"{TRIGRAMS.index(upper) + 1},{TRIGRAMS.index(lower) + 1}"
    digits = "零一二三四五六七八九"
    numbers = {
        (digits[n] if n < 10 else (digits[n // 10] if n >= 20 else "") + "十" + (digits[n % 10] if n % 10 else "")): n
        for n in range(1, 65)
    }
    return key, {
        "number": numbers[number[1]], "name": name, "title": short,
        "judgment": "".join(judgments), "lines": lines,
        "source": url, "revision": revision[1],
    }


def parse_images(chapters: dict[int, str]) -> dict:
    images = {name: [] for name in TRIGRAMS}
    paragraphs = lambda html: [text(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", html, re.S | re.I)]
    for p in paragraphs(chapters[3]):
        if re.match(r"^[乾兑离震巽坎艮坤]：", p):
            images[p[0]].append({"category": "万物属类（第二章）", "text": p[2:], "chapter": 3})
    current = None
    for tag, body in re.findall(r"<(h2|p)\b[^>]*>(.*?)</\1>", chapters[4], re.S | re.I):
        value = text(body)
        if tag == "h2":
            match = re.search(r"万物属类：(.)卦", value)
            current = match[1] if match else None
        elif current:
            if "天时：" in value:
                palace, value = value.split("天时：", 1)
                images[current].append({"category": "卦宫八卦（原文）", "text": palace, "chapter": 4})
                value = f"天时：{value}"
            if "：" in value:
                category, content = value.split("：", 1)
                images[current].append({"category": category, "text": content, "chapter": 4})
        elif re.match(r"^[乾兑离震巽坎艮坤]：", value):
            images[value[0]].append({"category": "八卦类象", "text": value[2:], "chapter": 4})
    section = chapters[13].split("卦应（与前八卦类象", 1)
    if len(section) != 2:
        raise ValueError("Missing chapter 12 trigram correspondences")
    current = None
    for p in paragraphs(section[1]):
        if re.match(r"^[乾兑离震巽坎艮坤]为", p):
            current = p[0]
            images[current].append({"category": "卦应（第十二章）", "text": p, "chapter": 13})
        elif current and "：" in p:
            category, content = p.split("：", 1)
            images[current].append({"category": f"卦应补充·{category}", "text": content, "chapter": 13})
    for name, rows in images.items():
        required = {"天时", "地理", "人物", "人事", "身体", "时序", "静物", "屋舍", "家宅", "婚姻",
                    "饮食", "生产", "求名", "谋旺", "交易", "求利", "出行", "谒见", "疾病",
                    "官讼", "坟墓", "方道", "五色", "数目", "五味", "八卦类象", "卦应（第十二章）"}
        missing = required - {r["category"] for r in rows}
        if missing:
            raise ValueError(f"{name}: missing imagery categories: {missing}")
    return images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    index = fetch(f"{WIKI}/zh-hans/{quote('周易')}", args.cache, "zhouyi-index.html")
    links = list(dict.fromkeys(unquote(link) for link in re.findall(r'href="(/wiki/[^"]+)"', index)))
    titles = [link.removeprefix("/wiki/周易/") for link in links if link.startswith("/wiki/周易/")]
    titles = [title for title in titles if title not in ("彖", "大象", "小象", "文言", "繫辭上", "繫辭下", "說卦", "序卦", "雜卦")]
    if len(titles) != 64:
        raise ValueError(f"Expected 64 chapters; found {len(titles)}")
    hexagrams = {}
    for title in titles:
        url = f"{WIKI}/zh-hans/{quote('周易/' + title)}"
        key, record = parse_hexagram(fetch(url, args.cache, f"zhouyi-{title}.html"), title, url)
        if key in hexagrams:
            raise ValueError(f"Duplicate hexagram: {key}")
        hexagrams[key] = record
    chapters = {n: fetch(f"{MEIHUA}meihua{n:02}.html", args.cache, f"meihua{n:02}.html") for n in (3, 4, 13)}
    images = parse_images(chapters)
    if {h["number"] for h in hexagrams.values()} != set(range(1, 65)):
        raise ValueError("Incomplete King Wen sequence")
    payload = {
        "provenance": {
            "retrieved": date.today().isoformat(),
            "notice": "仅收公版古籍正文，不收现代译注。卦爻辞取维基文库简体显示，保留异体及原有标点；类象保留劝学网原文，包括古称、异文和疑似讹字。",
            "meihua": MEIHUA,
        },
        "hexagrams": dict(sorted(hexagrams.items())),
        "images": images,
    }
    destination = ROOT / "app" / "data" / "classics.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(hexagrams)} judgments, {sum(len(h['lines']) for h in hexagrams.values())} lines, "
          f"{sum(len(v) for v in images.values())} imagery rows.")


if __name__ == "__main__":
    main()
