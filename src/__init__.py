from fastapi import FastAPI

from src.auth.routes import auth_router
from src.errors import register_all_errors

version = "v1"
version_prefix = f"/api/{version}"

app = FastAPI(
    title="Bookly",
    description="A REST API for a book review web service",
    version=version,
    openapi_url=f"{version_prefix}/openapi.json",
    docs_url=f"{version_prefix}/docs",
    redoc_url=f"{version_prefix}/redoc",
)

register_all_errors(app)
app.include_router(auth_router, prefix=f"{version_prefix}/auth", tags=["auth"])
