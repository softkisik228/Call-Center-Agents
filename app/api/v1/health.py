import time
from datetime import datetime

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.models import HealthResponse
from app.services import DialogManager

router = APIRouter()

# Время запуска приложения
start_time = time.time()


def get_dialog_manager() -> DialogManager:
    """
    Dependency для получения менеджера диалогов в health endpoints.

    Создает и возвращает экземпляр DialogManager для проверки
    доступности системы и агентов.

    Returns
    -------
    DialogManager
        Инициализированный экземпляр менеджера диалогов.

    """
    return DialogManager()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> HealthResponse:
    """
    Проверка состояния системы колл-центра.

    Выполняет комплексную проверку всех компонентов системы:
    доступности агентов, хранилища данных и общего состояния.
    Возвращает детальную информацию для мониторинга.

    Args:
    ----
        dialog_manager (DialogManager): Менеджер диалогов для проверки агентов.

    Returns:
    -------
    HealthResponse
        Структурированная информация о состоянии всех компонентов системы.

    """
    current_time = time.time()
    uptime_seconds = current_time - start_time

    # Проверяем доступность агентов
    try:
        agents_info = await dialog_manager.orchestrator.get_agent_capabilities()
        agents_available = len(agents_info) > 0
    except Exception:
        agents_available = False

    # Проверяем доступность хранилища
    try:
        storage_available = settings.dialog_storage_path.exists()
    except Exception:
        storage_available = False

    # Определяем общий статус
    if agents_available and storage_available:
        status = "healthy"
    elif agents_available or storage_available:
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        timestamp=datetime.now(),
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=uptime_seconds,
        agents_available=agents_available,
        storage_available=storage_available,
    )
