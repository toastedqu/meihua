const form = document.querySelector("#divination-form");
const button = document.querySelector("#chart-button");
const errorBox = document.querySelector("#error");
const result = document.querySelector("#result");
const formStatus = document.querySelector("#form-status");
const lineNames = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"];
let formVersion = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function sourceLink(url, label = "原文出处") {
  const link = element("a", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function updateMethod() {
  const two = form.elements.method.value === "two";
  const third = document.querySelector("#number-3");
  const hour = document.querySelector("#hour");
  document.querySelector("#third-number-field").hidden = two;
  document.querySelector("#hour-field").hidden = !two;
  third.disabled = two;
  third.required = !two;
  hour.disabled = !two;
  hour.required = two;
  document.querySelector("#method-description").textContent = two
    ? "前两数分别定上下卦；折算后的两个卦数加时辰数，除6取动爻。"
    : "前两数分别定上下卦；仅第三数除6取动爻，不加时辰或前两数。";
}

function invalidateResult() {
  formVersion += 1;
  result.hidden = true;
  result.replaceChildren();
  errorBox.hidden = true;
  formStatus.textContent = "";
}

form.addEventListener("input", invalidateResult);
form.addEventListener("change", () => {
  updateMethod();
  invalidateResult();
});

function payload() {
  const method = form.elements.method.value;
  const numbers = [1, 2, ...(method === "three" ? [3] : [])].map(
    (number) => document.querySelector(`#number-${number}`).value.trim()
  );
  const data = {
    method, numbers,
    season: document.querySelector("#season").value,
    question: document.querySelector("#question").value.trim(),
  };
  if (method === "two") data.hour = Number(document.querySelector("#hour").value);
  return data;
}

async function postJson(path, request) {
  if (window.meihuaBackend) return window.meihuaBackend(path, request);
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(request),
  });
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`服务未返回有效JSON（HTTP ${response.status}）。`);
  }
  return {ok: response.ok, status: response.status, payload: body};
}

function table(headers, rows, className) {
  const node = element("table", undefined, className);
  const head = element("thead");
  const headRow = element("tr");
  headers.forEach((value) => {
    const th = element("th", value);
    th.scope = "col";
    headRow.append(th);
  });
  head.append(headRow);
  const body = element("tbody");
  rows.forEach((values) => {
    const row = element("tr");
    values.forEach((value, index) => {
      const cell = element(index === 0 ? "th" : "td", value);
      if (index === 0) cell.scope = "row";
      row.append(cell);
    });
    body.append(row);
  });
  node.append(head, body);
  const wrap = element("div", undefined, "table-wrap");
  wrap.append(node);
  return wrap;
}

function details(title, open = false) {
  const node = element("details");
  node.open = open;
  node.append(element("summary", title));
  return node;
}

function trigramText(trigram) {
  return `${trigram.name} / ${trigram.image} / ${trigram.element} · ${trigram.strength}`;
}

function renderHexagram(chart, title, kind, data) {
  const card = element("article", undefined, "hexagram");
  card.dataset.kind = kind;
  card.append(element("h3", title), element("p", `${chart.name} · 第${chart.number}卦`, "hexagram-name"));
  const lines = element("ol", undefined, "yaos");
  lines.setAttribute("aria-label", `${chart.name}，从上爻至初爻`);
  for (let i = 5; i >= 0; i -= 1) {
    const moving = kind !== "mutual" && i + 1 === data.moving_line;
    const state = moving ? (kind === "original" ? "动" : "变") : "";
    const row = element("li", undefined, `yao${moving ? " moving" : ""}`);
    row.dataset.position = String(i + 1);
    row.setAttribute("aria-label", `${lineNames[i]}，${chart.lines[i] ? "阳爻" : "阴爻"}${state ? `，${state}爻` : ""}`);
    const mark = element("span", undefined, `line-mark${chart.lines[i] ? "" : " yin"}`);
    mark.setAttribute("aria-hidden", "true");
    mark.append(element("span"));
    if (!chart.lines[i]) mark.append(element("span"));
    row.append(element("span", lineNames[i]), mark, element("span", state));
    lines.append(row);
  }
  card.append(lines);
  ["upper", "lower"].forEach((side) => {
    let role;
    if (kind === "mutual") role = side === data.body_side ? "体互" : "用互";
    else role = side === data.body_side ? "体" : (kind === "transformed" ? "变用" : "用");
    card.append(element("small", `${side === "upper" ? "上" : "下"}卦：${trigramText(chart[side])}（${role}）`));
  });
  return card;
}

function render(data) {
  const fragment = document.createDocumentFragment();
  fragment.append(element("h2", "卦象 · 本卦、互卦、变卦"));
  const cards = element("div", undefined, "hexagrams");
  cards.append(
    renderHexagram(data.original, "本卦 · 当下", "original", data),
    renderHexagram(data.mutual, "互卦 · 过程", "mutual", data),
    renderHexagram(data.transformed, "变卦 · 结果", "transformed", data),
  );
  fragment.append(cards);
  if (data.request.question) fragment.append(element("p", `所占之事：${data.request.question}`));
  const method = data.request.method === "two" ? "双数法" : "三数法";
  fragment.append(element("p", `${method} · 数字 ${data.request.numbers.join("、")}${data.hour ? ` · ${data.hour.branch}时（${data.hour.number}）` : ""} · ${data.season.label}`));
  const calculation = details("排盘过程与取法");
  data.formulas.forEach((formula) => calculation.append(element("p", formula, "formula")));
  data.notes.slice(0, 2).forEach((note) => calculation.append(element("p", note)));
  calculation.append(sourceLink("https://www.quanxue.cn/qt_mingxiang/meihua/meihua02.html", "原书起卦与互卦说明"));
  fragment.append(calculation);
  if (data.notes.length > 4) fragment.append(element("p", data.notes[4], "notice"));

  fragment.append(element("h2", "体用生克 · 大体吉凶"));
  const summary = element("div", undefined, "summary");
  summary.append(
    element("strong", data.summary),
    element("p", `静体：${trigramText(data.body)}；动用：${trigramText(data.use)}。`),
    element("p", data.progression),
    element("p", data.notes[2], "muted"),
  );
  fragment.append(summary);
  fragment.append(table(
    ["阶段", "作用卦", "相对本卦之体", "通则倾向", "旺衰修正"],
    data.influences.map((item) => [
      `${item.stage} · ${item.role}`, trigramText(item.trigram),
      item.relation, item.tendency, item.qualification,
    ]),
    "influences",
  ));
  fragment.append(element("p", "表中“用”泛指该行的作用卦；体互、用互、变用均与原体比较。体互较切，过程可能吉凶并见；不相加打分，不把同一静体在变卦里重复计为一次助力。", "muted"));
  const reasoning = details("生克关系与旺衰依据", true);
  const seen = new Set();
  data.influences.forEach((item) => {
    if (!seen.has(item.relation)) {
      reasoning.append(element("p", `${item.relation}：${item.explanation}`));
      seen.add(item.relation);
    }
  });
  reasoning.append(table(["月令", "旺", "相", "休", "囚", "死"], [
    [data.season.label, ...["旺", "相", "休", "囚", "死"].map((key) => data.season.strengths[key])],
  ]));
  reasoning.append(element("p", data.notes[3]));
  reasoning.append(
    sourceLink(data.influences[0].source, "体用总诀"),
    document.createTextNode(" · "),
    sourceLink(data.influences[0].strength_source, "体用与衰旺论"),
  );
  fragment.append(reasoning);

  fragment.append(element("h2", "体卦、用卦 · 卦宫万物属类"));
  fragment.append(element("p", "这里的卦宫指体、用所属八卦的类象，不按纳甲六十四卦归宫另定体用。“全部”指所引章节已列条目，并非穷尽世间万物；保留古称、异文及原站疑似讹字，不将类象当作已发生事实。", "muted"));
  fragment.append(element("p", "下列疾病、生产、婚姻、官讼等内容是古籍原文，不是对你的诊断、产育预测或行动建议。原文中的“死”等断语也不代表现实结论。", "notice"));
  const imagery = details("完整类象对照（可收起）", true);
  const categories = [...new Set(data.imagery.flatMap((item) => item.rows.map((row) => row.category)))];
  const maps = data.imagery.map((item) => new Map(item.rows.map((row) => [row.category, row.text])));
  imagery.append(table(
    ["类别", ...data.imagery.map((item) => `${item.role} · ${item.trigram.name}宫（${item.trigram.element}）`)],
    categories.map((category) => [category, ...maps.map((map) => map.get(category) ?? "原文未单列")]),
    "imagery",
  ));
  [3, 4, 13].forEach((chapter, index) => {
    if (index) imagery.append(document.createTextNode(" · "));
    imagery.append(sourceLink(`${data.provenance.meihua}meihua${String(chapter).padStart(2, "0")}.html`, ["第二章属类", "第三章完整类象", "第十二章卦应"][index]));
  });
  fragment.append(imagery);

  fragment.append(element("h2", "卦辞与动爻爻辞"));
  fragment.append(element("p", "以下为《周易》古经原文，不是生成式解读。每次只有一爻动，乾坤也只取对应爻辞，不取用九、用六。", "muted"));
  data.texts.forEach((item) => {
    const section = element("article", undefined, "classical");
    section.append(element("h3", `${item.label} · ${item.name}`), element("blockquote", item.text), sourceLink(item.source, "维基文库原文"));
    fragment.append(section);
  });

  fragment.append(element("h2", "原书另有的规则与本页边界"));
  const rules = element("ol", undefined, "rules");
  data.additional_rules.forEach((rule) => {
    const item = element("li");
    item.append(
      element("strong", rule.title),
      element("p", rule.summary),
      element("p", rule.status, "muted"),
      sourceLink(rule.source, `第${rule.chapter - 1}章 · ${rule.section}`),
    );
    rules.append(item);
  });
  fragment.append(rules, element("p", `${data.provenance.notice} 资料收录：${data.provenance.retrieved}。`, "muted"));
  result.replaceChildren(fragment);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled || !form.reportValidity()) return;
  const version = formVersion;
  result.hidden = true;
  errorBox.hidden = true;
  button.disabled = true;
  form.setAttribute("aria-busy", "true");
  formStatus.textContent = "正在排盘…";
  try {
    const response = await postJson("/api/v1/chart", payload());
    if (version !== formVersion) return;
    if (!response.ok) {
      throw new Error(typeof response.payload.detail === "string"
        ? response.payload.detail : `排盘失败（HTTP ${response.status}）。`);
    }
    render(response.payload);
    result.hidden = false;
    formStatus.textContent = "排盘完成";
    result.focus({preventScroll: true});
    result.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    if (version !== formVersion) return;
    errorBox.textContent = `排盘失败：${error.message}`;
    errorBox.hidden = false;
    formStatus.textContent = "";
  } finally {
    button.disabled = false;
    form.removeAttribute("aria-busy");
  }
});

updateMethod();
