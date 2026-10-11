FROM python:3.12.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY ingestion ./ingestion
COPY rag_engine ./rag_engine
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir ".[app]" \
    && useradd --create-home --uid 10001 app
USER app
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
