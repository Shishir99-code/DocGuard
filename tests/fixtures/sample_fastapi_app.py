"""Sample FastAPI application used as a test fixture for the parser."""

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI()


class UserCreate(BaseModel):
    name: str
    email: str
    age: int | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    age: int | None = None
    is_active: bool = True


class ItemResponse(BaseModel):
    id: int
    title: str
    price: float
    description: str | None = None


@app.get("/users", response_model=list[UserResponse], tags=["users"], summary="List all users")
async def list_users(skip: int = 0, limit: int = 10):
    pass


@app.get("/users/{user_id}", response_model=UserResponse, tags=["users"])
async def get_user(user_id: int):
    pass


@app.post("/users", response_model=UserResponse, status_code=201, tags=["users"])
async def create_user(user: UserCreate):
    pass


@app.delete("/users/{user_id}", status_code=204, tags=["users"])
async def delete_user(user_id: int):
    pass


@app.get("/items/{item_id}", response_model=ItemResponse, tags=["items"])
async def get_item(item_id: int, q: str | None = None):
    pass
