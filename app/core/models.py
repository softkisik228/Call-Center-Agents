from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class CustomerInfo(BaseModel):
    """
    Информация о клиенте call-центра.

    Модель для хранения контактных данных и идентификаторов клиента.
    Включает валидацию email адресов и номеров телефонов.

    Attributes
    ----------
        name: Полное имя клиента.
        phone: Контактный номер телефона.
        email: Электронная почта клиента.
        customer_id: Уникальный идентификатор в CRM системе.

    """

    name: str = Field(..., description="Имя клиента", min_length=1, max_length=100)
    phone: Optional[str] = Field(None, description="Телефон клиента", max_length=20)
    email: Optional[str] = Field(None, description="Email клиента", max_length=100)
    customer_id: Optional[str] = Field(None, description="ID клиента в CRM", max_length=50)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """
        Валидация email адреса.

        Args:
        ----
            v: Email для валидации

        Returns:
        -------
            Валидированный email

        """
        if v and "@" not in v:
            raise ValueError("Некорректный email адрес")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """
        Валидация номера телефона.

        Args:
        ----
            v: Телефон для валидации

        Returns:
        -------
            Валидированный телефон

        """
        if v and not any(c.isdigit() for c in v):
            raise ValueError("Номер телефона должен содержать цифры")
        return v


class DialogCreate(BaseModel):
    """
    Модель для создания нового диалога с клиентом.

    Используется при инициации новой сессии общения с клиентом.
    Содержит всю необходимую информацию для начала диалога.

    Attributes
    ----------
        customer_info: Информация о клиенте.
        initial_message: Первое сообщение от клиента.
        source: Источник обращения (телефон, чат, email).
        priority: Приоритет обработки обращения.

    """

    customer_info: CustomerInfo = Field(..., description="Информация о клиенте")
    initial_message: Optional[str] = Field(None, description="Начальное сообщение", max_length=2000)
    source: str = Field(default="api", description="Источник диалога")
    priority: str = Field(default="normal", description="Приоритет диалога")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """
        Валидация приоритета диалога.

        Args:
        ----
            v: Приоритет для валидации

        Returns:
        -------
            Валидированный приоритет

        """
        allowed_priorities = ["low", "normal", "high", "urgent"]
        if v not in allowed_priorities:
            raise ValueError(f"Приоритет должен быть одним из: {allowed_priorities}")
        return v


class MessageRequest(BaseModel):
    """
    Запрос на отправку сообщения в диалог.

    Модель для передачи нового сообщения от клиента или агента
    в существующий диалог с валидацией типа и содержимого.

    Attributes
    ----------
        message: Текст сообщения для отправки.
        message_type: Тип отправителя (user/agent/system).
        metadata: Дополнительные данные о сообщении.

    """

    message: str = Field(..., description="Текст сообщения", min_length=1, max_length=2000)
    message_type: str = Field(default="user", description="Тип сообщения")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные сообщения")

    @field_validator("message_type")
    @classmethod
    def validate_message_type(cls, v: str) -> str:
        """
        Валидация типа сообщения.

        Args:
        ----
            v: Тип сообщения для валидации

        Returns:
        -------
            Валидированный тип сообщения

        """
        allowed_types = ["user", "agent", "system"]
        if v not in allowed_types:
            raise ValueError(f"Тип сообщения должен быть одним из: {allowed_types}")
        return v


class DialogMessage(BaseModel):
    """
    Сообщение в диалоге между клиентом и агентом.

    Представляет отдельное сообщение в истории диалога с полной
    информацией об отправителе, времени и контексте.

    Attributes
    ----------
        id: Уникальный идентификатор сообщения.
        dialog_id: Идентификатор диалога, к которому относится сообщение.
        sender: Тип отправителя (user/agent/system).
        message: Текст сообщения.
        agent_name: Имя агента, если отправитель - агент.
        timestamp: Время отправки сообщения.
        metadata: Дополнительные данные о сообщении.

    """

    id: str = Field(..., description="Идентификатор сообщения")
    dialog_id: str = Field(..., description="Идентификатор диалога")
    sender: str = Field(..., description="Отправитель (user/agent/system)")
    message: str = Field(..., description="Текст сообщения")
    agent_name: Optional[str] = Field(None, description="Имя агента-отправителя")
    timestamp: datetime = Field(..., description="Время отправки")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные")


class DialogResponse(BaseModel):
    """Ответ на сообщение в диалоге."""

    dialog_id: str = Field(..., description="Идентификатор диалога")
    message_id: str = Field(..., description="Идентификатор сообщения")
    agent_response: str = Field(..., description="Ответ агента")
    current_agent: str = Field(..., description="Текущий активный агент")
    previous_agent: Optional[str] = Field(None, description="Предыдущий агент")
    handoff_reason: Optional[str] = Field(None, description="Причина передачи управления")
    user_intent: Optional[str] = Field(None, description="Намерение пользователя")
    timestamp: datetime = Field(..., description="Время ответа")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные")


class DialogHistory(BaseModel):
    """История диалога."""

    dialog_id: str = Field(..., description="Идентификатор диалога")
    customer_info: CustomerInfo = Field(..., description="Информация о клиенте")
    status: str = Field(..., description="Статус диалога")
    created_at: datetime = Field(..., description="Время создания")
    updated_at: datetime = Field(..., description="Время последнего обновления")
    messages: list[DialogMessage] = Field(..., description="Список сообщений")
    current_agent: Optional[str] = Field(None, description="Текущий активный агент")
    conversation_summary: Optional[str] = Field(None, description="Краткое содержание")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные диалога")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """
        Валидация статуса диалога.

        Args:
        ----
            v: Статус для валидации

        Returns:
        -------
            Валидированный статус

        """
        allowed_statuses = ["active", "closed", "escalated", "pending"]
        if v not in allowed_statuses:
            raise ValueError(f"Статус должен быть одним из: {allowed_statuses}")
        return v


class HealthResponse(BaseModel):
    """Ответ на проверку состояния системы."""

    status: str = Field(..., description="Статус системы")
    timestamp: datetime = Field(..., description="Время проверки")
    version: str = Field(..., description="Версия приложения")
    environment: str = Field(..., description="Окружение")
    uptime_seconds: float = Field(..., description="Время работы в секундах")
    agents_available: bool = Field(..., description="Доступность агентов")
    storage_available: bool = Field(..., description="Доступность хранилища")


class AgentCapabilities(BaseModel):
    """Возможности агента."""

    agent_name: str = Field(..., description="Имя агента")
    capabilities: list[str] = Field(..., description="Список возможностей")
    is_available: bool = Field(..., description="Доступность агента")
    specialization: str = Field(..., description="Специализация агента")
