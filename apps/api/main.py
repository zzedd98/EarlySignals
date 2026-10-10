"""
Early Signals API - FastAPI application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import engine, init_db
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events: startup and shutdown"""
    # Startup
    await init_db()
    yield
    # Shutdown
    # Cleanup if needed


app = FastAPI(
    title="Early Signals API",
    description="API for Early Signals - Business intelligence tool",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "earlysignals-api",
        }
    )


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint - verifies DB connection"""
    try:
        from app.core.database import check_db_connection

        await check_db_connection()
        return JSONResponse(
            content={
                "status": "ready",
                "service": "earlysignals-api",
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "earlysignals-api",
                "error": str(e),
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
