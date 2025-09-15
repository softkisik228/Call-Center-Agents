FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock* ./

# Устанавливаем Poetry
RUN pip install poetry==1.7.1

# Настраиваем Poetry
RUN poetry config virtualenvs.create false

# Копируем исходный код
COPY . .

# Устанавливаем зависимости
RUN poetry install --only=main

# Копируем исходный код
COPY app/ ./app/

# Создаем необходимые директории
RUN mkdir -p /app/logs /app/storage/dialogs

# Открываем порт
EXPOSE 8000

# Запускаем приложение
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]