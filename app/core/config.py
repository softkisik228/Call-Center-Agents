from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Настройки приложения call-center-agents.

    Центральный класс для управления конфигурацией приложения.
    Использует Pydantic Settings для загрузки настроек из переменных окружения
    и .env файла с валидацией типов и значений по умолчанию.

    Attributes
    ----------
        openai_api_key: Ключ для доступа к OpenAI API.
        embedding_model: Модель для генерации векторных представлений.
        default_model: LLM модель для генерации ответов агентов.
        debug: Флаг режима отладки.
        dialog_storage_path: Путь для сохранения файлов диалогов.

    """

    # OpenAI API
    openai_api_key: str = Field(description="Ключ API OpenAI")
    use_mock_llm: bool = Field(default=False, description="Использовать mock LLM вместо OpenAI")
    embedding_model: str = Field(
        default="text-embedding-ada-002", description="Модель для генерации эмбеддингов"
    )

    # Настройки LLM
    default_model: str = Field(default="gpt-4o-mini", description="Модель по умолчанию")
    max_tokens: int = Field(default=1000, description="Максимальное количество токенов")
    temperature: float = Field(default=0.3, description="Температура для генерации")

    # Настройки приложения
    app_name: str = Field(default="Call Center Agents", description="Название приложения")
    app_version: str = Field(default="0.1.0", description="Версия приложения")
    environment: str = Field(default="development", description="Окружение приложения")
    debug: bool = Field(default=False, description="Режим отладки")

    # Настройки API
    api_prefix: str = Field(default="/api/v1", description="Префикс для API")
    api_host: str = Field(default="0.0.0.0", description="Хост для API")
    api_port: int = Field(default=8000, description="Порт для API")

    # Логирование
    log_level: str = Field(default="INFO", description="Уровень логирования")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Формат логов"
    )

    # Хранение данных
    dialog_storage_path: Path = Field(
        default=Path("storage/dialogs"), description="Путь для хранения диалогов"
    )

    # Ограничения
    max_dialog_history_length: int = Field(
        default=100, description="Максимальное количество сообщений в истории диалога"
    )
    max_message_length: int = Field(
        default=2000, description="Максимальная длина сообщения пользователя"
    )
    dialog_timeout_minutes: int = Field(default=30, description="Таймаут диалога в минутах")

    # Настройки агентов
    router_temperature: float = Field(default=0.1, description="Температура для роутера")
    tech_support_temperature: float = Field(default=0.2, description="Температура для техподдержки")
    sales_temperature: float = Field(default=0.4, description="Температура для продаж")
    supervisor_temperature: float = Field(default=0.3, description="Температура для супервизора")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    def __init__(self, **data: Any) -> None:
        """
        Инициализация настроек с созданием необходимых директорий.

        Автоматически создает директории для хранения данных и настраивает
        режим отладки в зависимости от окружения.

        Args:
        ----
            **data: Дополнительные параметры конфигурации.

        """
        super().__init__(**data)

        # Создаем директории если они не существуют
        self.dialog_storage_path.mkdir(parents=True, exist_ok=True)

        # Настраиваем debug режим
        if self.environment.lower() in ["development", "dev"]:
            self.debug = True
            self.debug = True

    @property
    def is_production(self) -> bool:
        """
        Проверка запуска в продакшене.

        Определяет текущее окружение на основе значения environment.
        Используется для настройки различных параметров в зависимости
        от режима работы приложения.

        Returns
        -------
        bool
            True если приложение запущено в продакшене.

        """
        return self.environment.lower() in ["production", "prod"]

    @property
    def cors_origins(self) -> list[str]:
        """
        Разрешенные origins для CORS.

        Настраивает список разрешенных источников для Cross-Origin запросов.
        В режиме разработки разрешает все origins, в продакшене возвращает
        пустой список для ручной настройки.

        Returns
        -------
        list[str]
            Список разрешенных origins для CORS.

        """
        if self.is_production:
            return []  # В продакшене настраивается отдельно
        return ["*"]  # В разработке разрешаем все

    def get_dialog_file_path(self, dialog_id: str) -> Path:
        """
        Получение пути к файлу диалога.

        Формирует полный путь к JSON файлу для сохранения или загрузки
        диалога на основе его идентификатора.

        Args:
        ----
            dialog_id (str): Уникальный идентификатор диалога.

        Returns:
        -------
        Path
            Путь к файлу диалога в файловой системе.

        """
        return self.dialog_storage_path / f"{dialog_id}.json"


# Глобальный экземпляр настроек
settings = Settings()
