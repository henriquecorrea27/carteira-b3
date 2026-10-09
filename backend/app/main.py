import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import analysis, corporate_events, fundamentals, imports, portfolio, report, transactions
from app.core.config import BACKEND_DIR
from app.core.db import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Carteira B3", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5180", "http://127.0.0.1:5180"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Flatten Pydantic errors into the same shape as ledger issues: {code, message, row}."""
    issues = []
    for err in exc.errors():
        loc = [part for part in err["loc"] if part != "body"]
        row = loc[1] if len(loc) > 1 and loc[0] == "items" and isinstance(loc[1], int) else None
        field = ".".join(str(part) for part in loc[2:] if row is not None) or ".".join(map(str, loc))
        message = str(err.get("ctx", {}).get("error") or err["msg"]).removeprefix("Value error, ")
        issues.append({"code": "INVALID_FIELD", "message": message, "row": row, "field": field or None})
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": issues})


@app.get("/api/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(transactions.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(imports.router, prefix="/api")
app.include_router(corporate_events.router, prefix="/api")
app.include_router(fundamentals.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(report.router, prefix="/api")

# Built frontend (npm run build), so the desktop shortcut needs a single process on :8000.
# In development the Vite dev server (:5180) is used instead.
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and FRONTEND_DIST.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")  # client-side routes (/carteira, /analise, ...)
