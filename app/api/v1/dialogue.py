import logging
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.exceptions import DialogException, ValidationException
from app.core.models import DialogCreate, DialogHistory, DialogResponse, MessageRequest
from app.services import DialogManager

router = APIRouter()
logger = logging.getLogger(__name__)


def get_dialog_manager() -> DialogManager:
    """
    Dependency для получения менеджера диалогов.

    Создает и возвращает экземпляр DialogManager для использования
    в маршрутах FastAPI через систему зависимостей.

    Returns
    -------
    DialogManager
        Инициализированный экземпляр менеджера диалогов.

    """
    return DialogManager()


@router.post("/create", response_model=DialogHistory)
async def create_dialog(
    dialog_create: DialogCreate,
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> DialogHistory:
    """
    Создание нового диалога с клиентом.

    Инициализирует новый диалог в системе колл-центра с предоставленной
    информацией о клиенте и начальным сообщением (если есть).

    Args:
    ----
        dialog_create (DialogCreate): Данные для создания диалога с информацией о клиенте.
        dialog_manager (DialogManager): Менеджер диалогов, внедряемый через DI.

    Returns:
    -------
    DialogHistory
        Полная история созданного диалога с уникальным идентификатором.

    Raises:
    ------
    HTTPException
        400: При ошибке валидации входных данных.
        500: При внутренней ошибке создания диалога.

    """
    try:
        dialog_history = await dialog_manager.create_dialog(dialog_create)
        logger.info(f"Создан диалог {dialog_history.dialog_id}")
        return dialog_history

    except ValidationException as e:
        logger.warning(f"Ошибка валидации при создании диалога: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DialogException as e:
        logger.error(f"Ошибка создания диалога: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{dialog_id}/message", response_model=DialogResponse)
async def send_message(
    dialog_id: str,
    message_request: MessageRequest,
    background_tasks: BackgroundTasks,
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> DialogResponse:
    """
    Отправка сообщения в существующий диалог.

    Обрабатывает новое сообщение пользователя в диалоге через систему агентов
    и возвращает ответ. Автоматически запускает фоновую очистку неактивных диалогов.

    Args:
    ----
        dialog_id (str): Уникальный идентификатор диалога.
        message_request (MessageRequest): Сообщение для отправки с метаданными.
        background_tasks (BackgroundTasks): Менеджер фоновых задач FastAPI.
        dialog_manager (DialogManager): Менеджер диалогов, внедряемый через DI.

    Returns:
    -------
    DialogResponse
        Ответ агента с информацией о текущем состоянии диалога.

    Raises:
    ------
    HTTPException
        400: При превышении лимита длины сообщения или ошибке валидации.
        404: Если диалог с указанным ID не найден.
        500: При внутренней ошибке обработки сообщения.

    """
    try:
        # Валидация длины сообщения
        if len(message_request.message) > 2000:
            raise ValidationException("Сообщение слишком длинное (максимум 2000 символов)")

        response = await dialog_manager.send_message(dialog_id, message_request)

        # Добавляем фоновую задачу очистки неактивных диалогов
        background_tasks.add_task(dialog_manager.cleanup_inactive_dialogs)

        logger.info(f"Обработано сообщение в диалоге {dialog_id}")
        return response

    except ValidationException as e:
        logger.warning(f"Ошибка валидации сообщения в диалоге {dialog_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DialogException as e:
        logger.error(f"Ошибка обработки сообщения в диалоге {dialog_id}: {e}")
        if "не найден" in str(e):
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{dialog_id}/history", response_model=DialogHistory)
async def get_dialog_history(
    dialog_id: str,
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> DialogHistory:
    """
    Получение истории диалога.

    Args:
    ----
        dialog_id: Идентификатор диалога
        dialog_manager: Менеджер диалогов

    Returns:
    -------
        История диалога

    Raises:
    ------
        HTTPException: Если диалог не найден

    """
    try:
        dialog_history = await dialog_manager.get_dialog_history(dialog_id)
        return dialog_history

    except DialogException as e:
        logger.warning(f"Диалог {dialog_id} не найден: {e}")
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{dialog_id}/close", response_model=DialogHistory)
async def close_dialog(
    dialog_id: str,
    reason: str = "manual",
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> DialogHistory:
    """
    Закрытие диалога.

    Args:
    ----
        dialog_id: Идентификатор диалога
        reason: Причина закрытия диалога
        dialog_manager: Менеджер диалогов

    Returns:
    -------
        Обновленная история закрытого диалога

    Raises:
    ------
        HTTPException: При ошибке закрытия диалога

    """
    try:
        dialog_history = await dialog_manager.close_dialog(dialog_id, reason)
        logger.info(f"Диалог {dialog_id} закрыт. Причина: {reason}")
        return dialog_history

    except DialogException as e:
        logger.warning(f"Ошибка закрытия диалога {dialog_id}: {e}")
        if "не найден" in str(e):
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/cleanup")
async def cleanup_inactive_dialogs(
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> Dict[str, Any]:
    """
    Принудительная очистка неактивных диалогов.

    Args:
    ----
        dialog_manager: Менеджер диалогов

    Returns:
    -------
        Информация о количестве закрытых диалогов

    """
    try:
        closed_count = await dialog_manager.cleanup_inactive_dialogs()
        return {
            "message": "Очистка завершена",
            "closed_dialogs": closed_count,
        }
    except Exception as e:
        logger.error(f"Ошибка очистки диалогов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки: {e}") from e


@router.get("/{dialog_id}/status")
async def get_dialog_status(
    dialog_id: str,
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> Dict[str, Any]:
    """
    Получение краткого статуса диалога.

    Args:
    ----
        dialog_id: Идентификатор диалога
        dialog_manager: Менеджер диалогов

    Returns:
    -------
        Краткая информация о статусе диалога

    Raises:
    ------
        HTTPException: Если диалог не найден

    """
    try:
        dialog_history = await dialog_manager.get_dialog_history(dialog_id)

        return {
            "dialog_id": dialog_id,
            "status": dialog_history.status,
            "current_agent": dialog_history.current_agent,
            "message_count": len(dialog_history.messages),
            "created_at": dialog_history.created_at,
            "updated_at": dialog_history.updated_at,
            "customer_name": dialog_history.customer_info.name,
        }

    except DialogException as e:
        logger.warning(f"Диалог {dialog_id} не найден: {e}")
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{dialog_id}")
async def delete_dialog(
    dialog_id: str,
    force: bool = False,
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> Dict[str, Any]:
    """
    Полное удаление диалога.

    Args:
    ----
        dialog_id: Идентификатор диалога
        force: Принудительное удаление (даже если диалог активен)
        dialog_manager: Менеджер диалогов

    Returns:
    -------
        Результат удаления

    Raises:
    ------
        HTTPException: При ошибке удаления диалога

    """
    try:
        success = await dialog_manager.delete_dialog(dialog_id, force=force)
        logger.info(f"Диалог {dialog_id} удален {'принудительно' if force else ''}")

        return {
            "success": success,
            "dialog_id": dialog_id,
            "message": f"Диалог {dialog_id} успешно удален",
        }

    except DialogException as e:
        logger.warning(f"Ошибка удаления диалога {dialog_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/cleanup/closed")
async def cleanup_closed_dialogs(
    older_than_days: int = 7,
    dialog_manager: DialogManager = Depends(get_dialog_manager),
) -> Dict[str, Any]:
    """
    Удаление старых закрытых диалогов.

    Args:
    ----
        older_than_days: Удалить диалоги старше этого количества дней
        dialog_manager: Менеджер диалогов

    Returns:
    -------
        Результат очистки

    """
    try:
        deleted_count = await dialog_manager.cleanup_closed_dialogs(older_than_days)
        logger.info(f"Удалено {deleted_count} старых закрытых диалогов")

        return {
            "deleted_count": deleted_count,
            "older_than_days": older_than_days,
            "message": f"Удалено {deleted_count} диалогов старше {older_than_days} дней",
        }

    except Exception as e:
        logger.error(f"Ошибка очистки закрытых диалогов: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
