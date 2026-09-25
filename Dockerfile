FROM node:24-bookworm-slim AS web
WORKDIR /web
RUN npm install -g pnpm@10.15.1
COPY src/web/package.json src/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY src/web/ ./
RUN pnpm run build

FROM python:3.10-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 POETRY_VIRTUALENVS_IN_PROJECT=true
WORKDIR /app
RUN pip install --no-cache-dir poetry==2.2.1
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction
COPY README.md ./
COPY src/ninna/ src/ninna/
RUN poetry install --only-root --no-interaction
COPY --from=web /web/dist /app/src/web/dist
COPY examples/ examples/
ENV NINNA_WEB_DIST=/app/src/web/dist
EXPOSE 8000
CMD ["poetry", "run", "ninna", "serve"]
