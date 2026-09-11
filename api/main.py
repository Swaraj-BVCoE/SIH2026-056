"""
api/main.py
───────────
FastAPI application entry point. 
Serves the REST API and mounts the static frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager

from api.routes import router as api_router
from db.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB on startup if it doesn't exist
    init_db()
    yield

app = FastAPI(
    title="AirFare Index India API",
    description="Experimental high-frequency domestic airfare index and CPI-oriented analytics API.",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
app.include_router(api_router, prefix="/api")

# Serve the production frontend build when present. Vite serves it separately in development.
web_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
