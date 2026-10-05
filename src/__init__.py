from fastapi import FastAPI
from src.books.routes import book_router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Server is starting... ")
    yield
    print(f"Server has been stopped")

version = "v1"

app = FastAPI(
    title="Bookly",
    description="A REST API for a book review web service",
    version=version,
    lifespan=lifespan
)

app.include_router(book_router, prefix=f"/api/{version}/books", tags=['books'])

