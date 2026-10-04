import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .api import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="TicketTriage Sentinel - Agent Arena")
app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
