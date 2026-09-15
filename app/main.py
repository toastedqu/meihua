from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.engine import handle

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="梅花易数排盘", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/v1/chart")
async def create_chart(request: Request):
    import json

    try:
        content = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse({"detail": "请求必须使用UTF-8编码。"}, status_code=422)
    response = json.loads(handle("/api/v1/chart", content))
    return JSONResponse(response["payload"], status_code=response["status"])
