FROM python:3.11-slim

# Устанавливаем часовой пояс, шрифты И fontconfig (для fc-cache)
ENV TZ=Europe/Moscow
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f -v

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY config.py .
COPY database.py .
COPY barcode_generator.py .
COPY excel_export.py .

RUN mkdir -p /app/data /app/labels

CMD ["python", "bot.py"]