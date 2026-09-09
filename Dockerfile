FROM node:22-alpine AS web
WORKDIR /app/apps/web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src:/app
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY apps/api/ ./apps/api/
COPY apps/mcp_server/ ./apps/mcp_server/
COPY apps/worker/ ./apps/worker/
COPY pipelines/ ./pipelines/
COPY tools/ ./tools/
COPY scripts/ ./scripts/
RUN pip install --no-cache-dir . && pip check
COPY data/ ./data/
COPY db/ ./db/
COPY alembic.ini ./
COPY --from=web /app/apps/web/dist ./apps/web/dist
COPY apps/web/public/ ./apps/web/public/
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
