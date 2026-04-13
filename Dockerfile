# базовый образ
FROM python:3.13

# рабочая директория
WORKDIR /app

# копируем зависимости
COPY requirements.txt .



# ставим зависимости
RUN pip install --no-cache-dir -r requirements.txt

# копируем код
COPY . .

# переменные окружения
ENV PYTHONUNBUFFERED=1

# запуск
CMD ["python", "connection.py"]
