import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import CallCenterException


# Настройка логирования
def setup_logging() -> None:
    """
    Настройка системы логирования приложения.

    Конфигурирует базовые настройки логирования с использованием
    параметров из конфигурации и устанавливает уровни логирования
    для внешних библиотек для уменьшения шума в логах.
    """
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=settings.log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Устанавливаем уровень логирования для внешних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Управление жизненным циклом FastAPI приложения.

    Обрабатывает события startup и shutdown приложения. При запуске
    настраивает логирование, создает необходимые директории и логирует
    информацию о конфигурации. При завершении выполняет cleanup.

    Args:
    ----
        app (FastAPI): Экземпляр FastAPI приложения.

    Yields:
    ------
        None: Контроль выполнения для работы приложения.

    """
    # Startup
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info(f"Запуск приложения {settings.app_name} v{settings.app_version}")
    logger.info(f"Окружение: {settings.environment}")
    logger.info(f"Режим отладки: {settings.debug}")

    # Создаем необходимые директории
    settings.dialog_storage_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Хранилище диалогов: {settings.dialog_storage_path}")

    yield

    # Shutdown
    logger.info("Завершение работы приложения")


# Создание FastAPI приложения
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multi-agent система для колл-центра на базе LangGraph",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Глобальный обработчик исключений
@app.exception_handler(CallCenterException)
async def call_center_exception_handler(request: Request, exc: CallCenterException) -> JSONResponse:
    """
    Обработчик специфичных исключений системы колл-центра.

    Обрабатывает все кастомные исключения приложения и возвращает
    структурированный JSON ответ с детальной информацией об ошибке.

    Args:
    ----
        request (Request): HTTP запрос, вызвавший исключение.
        exc (CallCenterException): Исключение системы колл-центра.

    Returns:
    -------
    JSONResponse
        JSON ответ с информацией об ошибке и HTTP статусом 400.

    """
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "type": exc.__class__.__name__,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Общий обработчик необработанных исключений.

    Ловит все необработанные исключения, логирует их для диагностики
    и возвращает безопасный ответ пользователю. В production скрывает
    детали внутренних ошибок.

    Args:
    ----
        request (Request): HTTP запрос, вызвавший исключение.
        exc (Exception): Необработанное исключение.

    Returns:
    -------
    JSONResponse
        JSON ответ с информацией об ошибке и HTTP статусом 500.

    """
    logger = logging.getLogger(__name__)
    logger.error(f"Необработанное исключение: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "type": "InternalServerError",
                "message": "Внутренняя ошибка сервера",
                "details": {} if settings.is_production else {"original": str(exc)},
            }
        },
    )


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    Middleware для логирования HTTP запросов.

    Логирует информацию о всех входящих HTTP запросах включая
    метод, путь, статус ответа и время обработки для мониторинга
    производительности и диагностики.

    Args:
    ----
        request (Request): Входящий HTTP запрос.
        call_next: Следующий обработчик в цепочке middleware.

    Returns:
    -------
    Response
        HTTP ответ от следующего обработчика.

    """
    logger = logging.getLogger(__name__)
    start_time = __import__("time").time()

    response = await call_next(request)

    process_time = __import__("time").time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )

    return response


# Подключение роутеров
app.include_router(api_router, prefix=settings.api_prefix)


# Корневой эндпоинт
@app.get("/")
async def root() -> dict[str, str]:
    """
    Корневой эндпоинт приложения.

    Предоставляет базовую информацию о сервисе и ссылки на
    важные эндпоинты для первичного ознакомления с API.

    Returns
    -------
    dict
        Словарь с метаинформацией о приложении и полезными ссылками.

    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "api_docs": "/docs",
        "health_check": "/health",
    }


# Эндпоинт для проверки здоровья на корневом уровне
@app.get("/health")
async def health() -> dict[str, str]:
    """
    Простая проверка здоровья приложения на корневом уровне.

    Быстрая проверка доступности сервиса без детальной диагностики.
    Используется для базового мониторинга и проверки работоспособности.

    Returns
    -------
    dict
        Словарь с базовой информацией о статусе приложения.

    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
