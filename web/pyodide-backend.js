(() => {
  const here = new URL(".", document.currentScript.src);
  const banner = document.createElement("p");
  banner.id = "runtime-status";
  banner.setAttribute("role", "status");
  banner.textContent = "正在加载浏览器排盘引擎；首次使用需下载 Python 运行时…";
  document.querySelector("h1").after(banner);

  async function fetchFile(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`加载 ${url.pathname} 失败（HTTP ${response.status}）。`);
    return response;
  }

  async function boot() {
    const manifest = await (await fetchFile(new URL("runtime-manifest.json", here))).json();
    const indexURL = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide_version}/full/`;
    const {loadPyodide} = await import(`${indexURL}pyodide.mjs`);
    const pyodide = await loadPyodide({indexURL});
    banner.textContent = "正在载入卦爻辞与排盘规则…";
    const archive = await (await fetchFile(new URL(manifest.engine, here))).arrayBuffer();
    pyodide.unpackArchive(archive, "zip", {extractDir: "/home/pyodide"});
    const handle = pyodide.runPython(`
import sys
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
from app.engine import handle
handle
`);
    banner.hidden = true;
    return handle;
  }

  const ready = boot();
  // Report startup failure even when the user has not submitted the form.
  ready.catch((error) => {
    banner.textContent = `排盘引擎加载失败：${error.message}。请检查网络后刷新页面重试。`;
    banner.classList.add("error");
    banner.setAttribute("role", "alert");
  });
  window.meihuaBackend = async (path, request) => {
    const handle = await ready;
    return JSON.parse(handle(path, JSON.stringify(request)));
  };
})();
