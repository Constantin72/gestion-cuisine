FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY src ./src

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app

VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "stock_cuisine", "--database", "/data/stock.db", "web", "--host", "0.0.0.0", "--port", "8000"]
