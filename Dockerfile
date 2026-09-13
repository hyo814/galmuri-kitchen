FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /srv/frontend/dist
ENV FRONTEND_DIST=/srv/frontend/dist
CMD flask --app app db upgrade && exec gunicorn -w 2 -b 0.0.0.0:${PORT:-8000} --access-logfile - "app:create_app()"
