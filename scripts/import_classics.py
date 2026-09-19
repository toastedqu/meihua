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


def passage(html: str) -> str:
    """Classical passage text: drop editorial <small> variant notes and all whitespace."""
    return re.sub(r"\s+", "", text(re.sub(r"<small\b.*?</small>", "", html, flags=re.S | re.I)))


SECTION = re.compile(r"<b>(易经：|易經：|彖曰：|象曰：|文言曰：)</b>")


def sections(html: str) -> dict[str, str]:
    """Split a Wikisource hexagram page into its labelled classical blocks."""
    marks = list(SECTION.finditer(html))
    found: dict[str, str] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(html)
        found.setdefault(mark[1], html[mark.end():end])
    return found


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


def commentary(html: str, title: str) -> tuple[str, str, list[str]]:
    """Return 彖辞, 大象辞 and the six ordinary 小象辞 in line order."""
    blocks = sections(html)
    tuan = passage(blocks.get("彖曰：", ""))
    xiang_block = blocks.get("象曰：", "")
    head, _, tail = xiang_block.partition("<ol")
    xiang = passage(head)
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", tail.partition("</ol>")[0], re.S | re.I)
    # A single moving line never uses Qian's 用九 or Kun's 用六, nor their 小象.
    line_xiang = [value for value in map(passage, items) if not value.startswith(("用九", "用六"))]
    if not tuan or not xiang or len(line_xiang) != 6:
        raise ValueError(
            f"{title}: incomplete commentary: 彖={len(tuan)} chars, 象={len(xiang)} chars, "
            f"{len(line_xiang)} 小象 (expected 6)"
        )
    return tuan, xiang, line_xiang


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
    tuan, xiang, line_xiang = commentary(html, title)
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
        "tuan": tuan, "xiang": xiang, "line_xiang": line_xiang,
        "source": url, "revision": revision[1],
    }


DESTINATION = ROOT / "app" / "data" / "classics.json"


def curated_images() -> dict:
    """Imagery is hand-curated in the dataset; a reimport must preserve it unchanged."""
    images = json.loads(DESTINATION.read_text(encoding="utf-8"))["images"]
    if set(images) != set(TRIGRAMS):
        raise ValueError(f"Curated imagery must cover all eight trigrams; found {sorted(images)}")
    for name, rows in images.items():
        if not rows or any(set(row) != {"category", "text"} or not row["text"].strip() for row in rows):
            raise ValueError(f"{name}: curated imagery rows must be non-empty category/text pairs")
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
    images = curated_images()
    if {h["number"] for h in hexagrams.values()} != set(range(1, 65)):
        raise ValueError("Incomplete King Wen sequence")
    payload = {
        "provenance": {
            "retrieved": date.today().isoformat(),
            "notice": "仅收公版古籍正文，不收现代译注。卦辞、爻辞、彖辞、象辞取维基文库简体显示，保留异体及原有标点；八卦类象为人工整理的物象条目。",
        },
        "hexagrams": dict(sorted(hexagrams.items())),
        "images": images,
    }
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(hexagrams)} judgments, {sum(len(h['lines']) for h in hexagrams.values())} lines, "
          f"{sum(len(h['line_xiang']) for h in hexagrams.values())} 小象, "
          f"{sum(len(v) for v in images.values())} curated imagery rows.")


if __name__ == "__main__":
    main()
