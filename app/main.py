import pymysql
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(
    title="CH Delivery API",
    version="1.0.0"
)


@app.exception_handler(pymysql.err.OperationalError)
def db_unavailable(request: Request, exc: pymysql.err.OperationalError):
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "message": "Database unavailable: cannot connect to MySQL at "
                       f"{settings.DB_HOST}:{settings.DB_PORT}",
            "detail": str(exc)
        }
    )

app.include_router(
    api_router,
    prefix="/api/v1"
)

@app.get("/")
def root():
    return {
        "application": "CH Delivery API",
        "status": "Running"
    }