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
    : "前两数分别定上下卦；仅第三数除6取动爻。";
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
    card.append(element("small", `${side === "upper" ? "上" : "下"}卦：${chart[side].image} · ${role}`));
  });
  return card;
}

function render(data) {
  const fragment = document.createDocumentFragment();

  fragment.append(element("h2", "盘"));
  const cards = element("div", undefined, "hexagrams");
  cards.append(
    renderHexagram(data.original, "本卦", "original", data),
    renderHexagram(data.mutual, "互卦", "mutual", data),
    renderHexagram(data.transformed, "变卦", "transformed", data),
  );
  fragment.append(cards);
  if (data.request.question) fragment.append(element("p", `所占之事：${data.request.question}`));
  const method = data.request.method === "two" ? "双数法" : "三数法";
  fragment.append(element("p", `${method} · 数字 ${data.request.numbers.join("、")}${data.hour ? ` · ${data.hour.branch}时（${data.hour.number}）` : ""} · ${data.season.label}`));
  fragment.append(element("p", `第${data.moving_line}爻动 · 体：${data.body.image} · 用：${data.use.image}`));

  fragment.append(element("h2", "吉凶判定"));
  fragment.append(table(
    ["阶段", "体", "用", "体用生克", "通则倾向", "旺衰修正"],
    data.influences.map((item) => [
      item.stage, data.body.image, `${item.role} · ${item.trigram.image}`,
      item.relation, item.tendency, item.qualification,
    ]),
    "influences",
  ));

  fragment.append(element("h2", "卦象"));
  const imagery = details("完整类象对照（可收起）", true);
  const categories = [...new Set(data.imagery.flatMap((item) => item.rows.map((row) => row.category)))];
  const maps = data.imagery.map((item) => new Map(item.rows.map((row) => [row.category, row.text])));
  imagery.append(table(
    ["类别", ...data.imagery.map((item) => `${item.role} · ${item.trigram.image}`)],
    categories.map((category) => [category, ...maps.map((map) => map.get(category) ?? "—")]),
    "imagery",
  ));
  fragment.append(imagery);

  fragment.append(element("h2", "卦爻辞"));
  data.texts.forEach((item) => {
    const section = element("article", undefined, "classical");
    const quote = element("blockquote");
    item.passages.forEach((entry) => {
      const paragraph = element("p");
      paragraph.append(element("strong", entry.label), document.createTextNode(`：${entry.text}`));
      quote.append(paragraph);
    });
    section.append(element("h3", item.title), quote, sourceLink(item.source, "维基文库原文"));
    fragment.append(section);
  });

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
