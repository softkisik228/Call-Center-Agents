from fastapi import APIRouter

from .dialogue import router as dialogue_router
from .health import router as health_router

# Создаем основной роутер для API v1
api_router = APIRouter()

# Подключаем роутеры модулей
api_router.include_router(
    dialogue_router,
    prefix="/dialogue",
    tags=["dialogue"],
)

api_router.include_router(
    health_router,
    prefix="",
    tags=["health"],
)
