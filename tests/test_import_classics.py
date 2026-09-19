"""Importer evidence: complete ordered commentary, explicit failure on incomplete sources."""

import pytest

from scripts.import_classics import parse_hexagram

URL = "https://zh.wikisource.org/zh-hans/%E5%91%A8%E6%98%93/%E5%B1%A5"
JUDGMENT = "履虎尾，不咥人，亨。"
LINES = [
    "初九：素履，往无咎。",
    "九二：履道坦坦，幽人贞吉。",
    "六三：眇能视，跛能履，履虎尾，咥人，凶。武人为于大君。",
    "九四：履虎尾，愬愬终吉。",
    "九五：夬履，贞厉。",
    "上九：视履考祥，其旋元吉。",
]
TUAN = "履，柔履刚也。说而应乎干，是以履虎尾，不咥人，亨。刚中正，履帝位而不疚，光明也。"
XIANG = "上天下泽，履；君子以辨上下，定民志。"
LINE_XIANG = [
    "素履之往，独行愿也。",
    "幽人贞吉，中不自乱也。",
    "眇能视，不足以有明也。跛能履，不足以与行也。咥人之凶，位不当也。武人为于大君，志刚也。",
    "愬愬终吉，志行也。",
    "夬履贞厉，位正当也。",
    "元吉在上，大有庆也。",
]


def page(lines=LINES, line_xiang=LINE_XIANG, tuan=TUAN, xiang=XIANG):
    """Minimal source-shaped Wikisource markup (blue 经文 spans, plain 彖/象 lists)."""
    blue = "\n".join(f'<li><span style="color:blue">{line}</span></li>' for line in lines)
    small = "\n".join(f"<li>{item}</li>" for item in line_xiang)
    tuan_block = f'<ul><li><b>彖曰：</b><ul><li>{tuan}</li></ul></li></ul>' if tuan else ""
    xiang_block = f'<ul><li><b>象曰：</b><ul><li>{xiang}</li></ul><ol>{small}</ol></li></ul>' if xiang else ""
    return f"""<html><head><script>{{"wgRevisionId":2494097}}</script></head><body>
<p>周易 第十卦 履 兑下干上</p>
<ul><li><span style="color:blue"><b>易经：</b></span>
<ul><li><span style="color:blue">{JUDGMENT}</span></li></ul>
<ol>{blue}</ol></li></ul>
{tuan_block}
{xiang_block}
</body></html>"""


def test_parse_imports_complete_ordered_commentary():
    key, record = parse_hexagram(page(), "履", URL)
    assert key == "1,2"
    assert record["name"] == "天泽履"
    assert record["number"] == 10
    assert record["judgment"] == JUDGMENT
    assert record["lines"] == LINES
    assert record["tuan"] == TUAN
    assert record["xiang"] == XIANG
    assert record["line_xiang"] == LINE_XIANG
    assert record["source"] == URL


@pytest.mark.parametrize("broken", [
    page(line_xiang=LINE_XIANG[:5]),
    page(line_xiang=LINE_XIANG + ["多出来的小象。"]),
    page(tuan=""),
    page(xiang=""),
    page(lines=LINES[:5]),
], ids=["missing-line-xiang", "extra-line-xiang", "missing-tuan", "missing-xiang", "missing-line"])
def test_incomplete_source_fails_loudly(broken):
    with pytest.raises(ValueError):
        parse_hexagram(broken, "履", URL)
