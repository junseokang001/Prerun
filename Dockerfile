FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ENV BACKEND_URL=http://127.0.0.1:8765
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY --from=web /src/frontend /app/frontend
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh
ENV BACKEND_URL=http://127.0.0.1:8765
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1
CMD ["/app/start.sh"]
