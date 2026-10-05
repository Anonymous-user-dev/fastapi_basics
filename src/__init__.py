from fastapi import FastAPI

from src.auth.routes import auth_router
from src.books.routes import book_router
from src.errors import register_all_errors
from src.middleware import register_middleware
from src.reviews.routes import review_router
from src.tags.routes import tags_router

version = "v1"
version_prefix = f"/api/{version}"

description = """
A REST API for a book review web service.

- Create, read, update, and delete books
- Add reviews to books
- Categorize books with tags
"""

app = FastAPI(
    title="Bookly",
    description=description,
    version=version,
    license_info={"name": "MIT License", "url": "https://opensource.org/license/mit"},
    contact={"name": "Bookly API"},
    terms_of_service="https://example.com/tos",
    openapi_url=f"{version_prefix}/openapi.json",
    docs_url=f"{version_prefix}/docs",
    redoc_url=f"{version_prefix}/redoc",
)

register_all_errors(app)
register_middleware(app)
app.include_router(auth_router, prefix=f"{version_prefix}/auth", tags=["auth"])
app.include_router(book_router, prefix=f"{version_prefix}/books", tags=["books"])
app.include_router(tags_router, prefix=f"{version_prefix}/tags", tags=["tags"])
app.include_router(review_router, prefix=f"{version_prefix}/reviews", tags=["reviews"])
