import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agents import AgentOrchestrator
from app.core.config import settings
from app.core.exceptions import DialogException, StorageException
from app.core.models import (
    DialogCreate,
    DialogHistory,
    DialogMessage,
    DialogResponse,
    MessageRequest,
)

logger = logging.getLogger(__name__)


class DialogManager:
    """
    Менеджер для управления диалогами клиентов в системе колл-центра.

    Центральный сервис для создания, сохранения и управления диалогами.
    Координирует взаимодействие с системой агентов, обеспечивает
    персистентность диалогов и управляет их жизненным циклом.

    Attributes
    ----------
        orchestrator: Оркестратор агентов для обработки сообщений.
        storage_path: Путь к директории для сохранения диалогов.
        active_dialogs: Кэш активных диалогов с временными метками.

    """

    def __init__(self) -> None:
        """
        Инициализация менеджера диалогов.

        Создает экземпляр оркестратора агентов, настраивает пути хранения
        и инициализирует кэш активных диалогов.
        """
        self.orchestrator = AgentOrchestrator()
        self.storage_path = settings.dialog_storage_path
        self.active_dialogs: Dict[str, datetime] = {}

        logger.info("Инициализирован менеджер диалогов")

    async def create_dialog(self, dialog_create: DialogCreate) -> DialogHistory:
        """
        Создание нового диалога с клиентом.

        Инициализирует новый диалог с уникальным идентификатором,
        сохраняет информацию о клиенте и обрабатывает начальное
        сообщение, если оно предоставлено.

        Args:
        ----
            dialog_create (DialogCreate): Данные для создания диалога с информацией о клиенте.

        Returns:
        -------
        DialogHistory
            Полная история созданного диалога с первоначальным состоянием.

        Raises:
        ------
        DialogException
            При ошибке создания диалога или обработки начального сообщения.

        """
        dialog_id = str(uuid.uuid4())
        now = datetime.now()

        try:
            # Создаем историю диалога
            dialog_history = DialogHistory(
                dialog_id=dialog_id,
                customer_info=dialog_create.customer_info,
                status="active",
                created_at=now,
                updated_at=now,
                messages=[],
                metadata={
                    "source": dialog_create.source,
                    "priority": dialog_create.priority,
                },
                current_agent=None,
                conversation_summary=None,
            )

            # Если есть начальное сообщение, добавляем его и обрабатываем
            if dialog_create.initial_message:
                initial_message = DialogMessage(
                    id=str(uuid.uuid4()),
                    dialog_id=dialog_id,
                    sender="user",
                    message=dialog_create.initial_message,
                    agent_name=None,
                    timestamp=now,
                )
                dialog_history.messages.append(initial_message)

                # Обрабатываем начальное сообщение через оркестратор агентов
                agent_result = await self.orchestrator.process_dialog_turn(
                    dialog_id=dialog_id,
                    user_message=dialog_create.initial_message,
                    message_history=[],  # Пустая история для первого сообщения
                )

                # Создаем ответное сообщение агента
                agent_message = DialogMessage(
                    id=str(uuid.uuid4()),
                    dialog_id=dialog_id,
                    sender="agent",
                    message=agent_result["agent_response"],
                    agent_name=agent_result["current_agent"],
                    timestamp=now,
                    metadata=agent_result["metadata"],
                )

                # Добавляем ответ агента в историю
                dialog_history.messages.append(agent_message)

                # Обновляем метаданные диалога
                dialog_history.current_agent = agent_result["current_agent"]
                dialog_history.metadata.update(
                    {
                        "last_user_intent": agent_result.get("user_intent"),
                        "last_handoff_reason": agent_result.get("handoff_reason"),
                    }
                )

            # Сохраняем диалог
            await self._save_dialog(dialog_history)

            # Добавляем в активные диалоги
            self.active_dialogs[dialog_id] = now

            logger.info(
                f"Создан новый диалог {dialog_id} для клиента {dialog_create.customer_info.name}"
                + (
                    f", обработано начальное сообщение, назначен агент: {dialog_history.current_agent}"
                    if dialog_create.initial_message
                    else ""
                )
            )
            return dialog_history

        except Exception as e:
            logger.error(f"Ошибка создания диалога: {e}")
            raise DialogException(f"Не удалось создать диалог: {e}") from e

    async def send_message(self, dialog_id: str, message_request: MessageRequest) -> DialogResponse:
        """
        Отправка сообщения в диалог и получение ответа агента.

        Args:
        ----
            dialog_id: Идентификатор диалога
            message_request: Запрос с сообщением

        Returns:
        -------
            Ответ агента на сообщение

        Raises:
        ------
            DialogException: При ошибке обработки сообщения

        """
        try:
            # Загружаем историю диалога
            dialog_history = await self.get_dialog_history(dialog_id)

            # Проверяем статус диалога
            if dialog_history.status not in ["active", "pending"]:
                raise DialogException(
                    f"Диалог {dialog_id} не активен (статус: {dialog_history.status})"
                )

            # Создаем сообщение пользователя
            user_message = DialogMessage(
                id=str(uuid.uuid4()),
                dialog_id=dialog_id,
                sender=message_request.message_type,
                message=message_request.message,
                agent_name=None,
                timestamp=datetime.now(),
                metadata=message_request.metadata,
            )

            # Добавляем сообщение в историю
            dialog_history.messages.append(user_message)

            # Конвертируем историю в формат LangChain
            message_history = self._convert_to_langchain_messages(dialog_history.messages[:-1])

            # Обрабатываем через оркестратор агентов
            agent_result = await self.orchestrator.process_dialog_turn(
                dialog_id=dialog_id,
                user_message=message_request.message,
                message_history=message_history,
            )

            # Создаем ответное сообщение агента
            agent_message = DialogMessage(
                id=str(uuid.uuid4()),
                dialog_id=dialog_id,
                sender="agent",
                message=agent_result["agent_response"],
                agent_name=agent_result["current_agent"],
                timestamp=datetime.now(),
                metadata=agent_result["metadata"],
            )

            # Добавляем ответ агента в историю
            dialog_history.messages.append(agent_message)

            # Обновляем метаданные диалога
            dialog_history.current_agent = agent_result["current_agent"]
            dialog_history.updated_at = datetime.now()
            dialog_history.metadata.update(
                {
                    "last_user_intent": agent_result.get("user_intent"),
                    "last_handoff_reason": agent_result.get("handoff_reason"),
                }
            )

            # Ограничиваем историю сообщений
            if len(dialog_history.messages) > settings.max_dialog_history_length:
                # Сохраняем краткое содержание старых сообщений
                old_messages = dialog_history.messages[: -settings.max_dialog_history_length]
                dialog_history.conversation_summary = await self._summarize_messages(old_messages)
                dialog_history.messages = dialog_history.messages[
                    -settings.max_dialog_history_length :
                ]

            # Сохраняем обновленную историю
            await self._save_dialog(dialog_history)

            # Обновляем время активности
            self.active_dialogs[dialog_id] = datetime.now()

            # Создаем ответ
            response = DialogResponse(
                dialog_id=dialog_id,
                message_id=user_message.id,
                agent_response=agent_result["agent_response"],
                current_agent=agent_result["current_agent"],
                previous_agent=agent_result.get("previous_agent"),
                handoff_reason=agent_result.get("handoff_reason"),
                user_intent=agent_result.get("user_intent"),
                timestamp=agent_message.timestamp,
                metadata=agent_result["metadata"],
            )

            logger.info(
                f"Обработано сообщение в диалоге {dialog_id}, агент: {response.current_agent}"
            )
            return response

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения в диалоге {dialog_id}: {e}")
            raise DialogException(f"Не удалось обработать сообщение: {e}") from e

    async def get_dialog_history(self, dialog_id: str) -> DialogHistory:
        """
        Получение истории диалога.

        Args:
        ----
            dialog_id: Идентификатор диалога

        Returns:
        -------
            История диалога

        Raises:
        ------
            DialogException: Если диалог не найден

        """
        try:
            dialog_file = settings.get_dialog_file_path(dialog_id)

            if not dialog_file.exists():
                raise DialogException(f"Диалог {dialog_id} не найден")

            with dialog_file.open("r", encoding="utf-8") as f:
                dialog_data = json.load(f)

            return DialogHistory(**dialog_data)

        except DialogException:
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки диалога {dialog_id}: {e}")
            raise DialogException(f"Не удалось загрузить диалог: {e}") from e

    async def close_dialog(self, dialog_id: str, reason: str = "completed") -> DialogHistory:
        """
        Закрытие диалога.

        Args:
        ----
            dialog_id: Идентификатор диалога
            reason: Причина закрытия

        Returns:
        -------
            Обновленная история диалога

        Raises:
        ------
            DialogException: При ошибке закрытия диалога

        """
        try:
            dialog_history = await self.get_dialog_history(dialog_id)

            dialog_history.status = "closed"
            dialog_history.updated_at = datetime.utcnow()
            dialog_history.metadata["close_reason"] = reason

            await self._save_dialog(dialog_history)

            # Удаляем из активных диалогов
            self.active_dialogs.pop(dialog_id, None)

            logger.info(f"Диалог {dialog_id} закрыт. Причина: {reason}")
            return dialog_history

        except Exception as e:
            logger.error(f"Ошибка закрытия диалога {dialog_id}: {e}")
            raise DialogException(f"Не удалось закрыть диалог: {e}") from e

    async def cleanup_inactive_dialogs(self) -> int:
        """
        Очистка неактивных диалогов.

        Returns
        -------
            Количество закрытых диалогов

        """
        timeout_delta = timedelta(minutes=settings.dialog_timeout_minutes)
        current_time = datetime.utcnow()
        closed_count = 0

        inactive_dialogs = []
        for dialog_id, last_activity in self.active_dialogs.items():
            if current_time - last_activity > timeout_delta:
                inactive_dialogs.append(dialog_id)

        for dialog_id in inactive_dialogs:
            try:
                await self.close_dialog(dialog_id, "timeout")
                closed_count += 1
            except Exception as e:
                logger.error(f"Ошибка закрытия неактивного диалога {dialog_id}: {e}")

        if closed_count > 0:
            logger.info(f"Закрыто {closed_count} неактивных диалогов")

        return closed_count

    async def delete_dialog(self, dialog_id: str, force: bool = False) -> bool:
        """
        Полное удаление диалога.

        Args:
        ----
            dialog_id: Идентификатор диалога
            force: Принудительное удаление (даже если диалог активен)

        Returns:
        -------
            True если диалог успешно удален

        Raises:
        ------
            DialogException: При ошибке удаления диалога

        """
        try:
            # Проверяем существование диалога
            dialog_history = await self.get_dialog_history(dialog_id)

            # Проверяем статус диалога
            if dialog_history.status == "active" and not force:
                raise DialogException(
                    f"Нельзя удалить активный диалог {dialog_id}. Сначала закройте его или используйте force=True"
                )

            # Удаляем файл
            dialog_file = settings.get_dialog_file_path(dialog_id)
            if dialog_file.exists():
                dialog_file.unlink()
                logger.info(f"Файл диалога {dialog_id} удален")

            # Удаляем из активных диалогов
            self.active_dialogs.pop(dialog_id, None)

            logger.info(f"Диалог {dialog_id} полностью удален")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления диалога {dialog_id}: {e}")
            raise DialogException(f"Не удалось удалить диалог: {e}") from e

    async def cleanup_closed_dialogs(self, older_than_days: int = 7) -> int:
        """
        Удаление закрытых диалогов старше указанного количества дней.

        Args:
        ----
            older_than_days: Удалить диалоги старше этого количества дней

        Returns:
        -------
            Количество удаленных диалогов

        """
        deleted_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

        try:
            # Ищем все файлы диалогов
            for dialog_file in self.storage_path.glob("*.json"):
                try:
                    with dialog_file.open("r", encoding="utf-8") as f:
                        dialog_data = json.load(f)

                    # Проверяем статус и дату
                    if (
                        dialog_data.get("status") == "closed"
                        and datetime.fromisoformat(dialog_data.get("updated_at", "")) < cutoff_date
                    ):
                        dialog_id = dialog_data.get("dialog_id")
                        await self.delete_dialog(dialog_id, force=True)
                        deleted_count += 1

                except Exception as e:
                    logger.error(f"Ошибка обработки файла {dialog_file}: {e}")

            if deleted_count > 0:
                logger.info(f"Удалено {deleted_count} старых закрытых диалогов")

            return deleted_count

        except Exception as e:
            logger.error(f"Ошибка очистки закрытых диалогов: {e}")
            return 0

    async def _save_dialog(self, dialog_history: DialogHistory) -> None:
        """
        Сохранение истории диалога в файл.

        Args:
        ----
            dialog_history: История диалога для сохранения

        Raises:
        ------
            StorageException: При ошибке сохранения

        """
        try:
            dialog_file = settings.get_dialog_file_path(dialog_history.dialog_id)
            dialog_data = dialog_history.model_dump(mode="json")

            # Конвертируем datetime объекты в строки
            from typing import Any

            def convert_datetime(obj: Any) -> Any:
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: convert_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                return obj

            dialog_data = convert_datetime(dialog_data)

            with dialog_file.open("w", encoding="utf-8") as f:
                json.dump(dialog_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Ошибка сохранения диалога {dialog_history.dialog_id}: {e}")
            raise StorageException(f"Не удалось сохранить диалог: {e}") from e

    def _convert_to_langchain_messages(self, messages: List[DialogMessage]) -> List[BaseMessage]:
        """
        Конвертация сообщений в формат LangChain.

        Args:
        ----
            messages: Список сообщений диалога

        Returns:
        -------
            Список сообщений в формате LangChain

        """
        langchain_messages: List[BaseMessage] = []

        for msg in messages:
            if msg.sender == "user":
                langchain_messages.append(HumanMessage(content=msg.message))
            elif msg.sender == "agent":
                langchain_messages.append(AIMessage(content=msg.message))

        return langchain_messages

    async def _summarize_messages(self, messages: List[DialogMessage]) -> str:
        """
        Создание краткого содержания сообщений.

        Args:
        ----
            messages: Список сообщений для суммаризации

        Returns:
        -------
            Краткое содержание диалога

        """
        if not messages:
            return ""

        # Простая суммаризация (можно улучшить с помощью LLM)
        user_messages = [msg.message for msg in messages if msg.sender == "user"]
        agent_messages = [msg.message for msg in messages if msg.sender == "agent"]

        summary_parts = []
        if user_messages:
            summary_parts.append(f"Запросы клиента: {'; '.join(user_messages[:3])}")
        if agent_messages:
            summary_parts.append(f"Ответы агентов: {'; '.join(agent_messages[:3])}")

        return " | ".join(summary_parts)
