"""Main FastAPI application for the ALAB GPSS system."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from alab_gpss.backend.routers import (
    consumable_rack,
    dosing_head,
    ionic_conductivity,
    xrd_sample_holder,
)

app = FastAPI(
    title="ALAB GPSS API",
    description="API for managing ALAB GPSS devices",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the path to the frontend build directory
frontend_path = Path(__file__).parent.parent / "ui" / "build"

# Include API routers
app.include_router(
    xrd_sample_holder.router,
    prefix="/api/xrd-sample-holder",
    tags=["xrd-sample-holder"],
)
app.include_router(dosing_head.router, prefix="/api/dosing-head", tags=["dosing-head"])
app.include_router(
    consumable_rack.router, prefix="/api/consumable-rack", tags=["consumable-rack"]
)
app.include_router(
    ionic_conductivity.router,
    prefix="/api/ionic-conductivity",
    tags=["ionic-conductivity"],
)


# Middleware to redirect non-trailing slash URLs to trailing slash URLs
@app.middleware("http")
async def redirect_slashes(request: Request, call_next):
    if request.url.path != "/" and not request.url.path.endswith("/"):
        return RedirectResponse(url=request.url.path + "/", status_code=307)
    return await call_next(request)


# Serve static files if the frontend build exists
if frontend_path.exists():
    # Mount static files directory
    app.mount(
        "/static", StaticFiles(directory=str(frontend_path / "static")), name="static"
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Skip API routes
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, detail="API endpoint not found")

        # Try to serve the requested file
        file_path = frontend_path / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))

        # Serve index.html for all other routes (SPA routing)
        return FileResponse(str(frontend_path / "index.html"))

else:
    print("Frontend build not found at:", frontend_path)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        return JSONResponse(
            status_code=404,
            detail="Frontend build not found. Please build the frontend application first.",
        )
