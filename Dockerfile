FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system spy && useradd --system --gid spy --create-home spy

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY --chown=spy:spy . ./
USER spy

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec python -m uvicorn adapters.runtime:app --host 0.0.0.0 --port 8000"]
