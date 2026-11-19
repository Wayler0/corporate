# One image for Railway: the Django fare server, which also serves the built
# React dashboard at the site's root. See DEPLOY.md.

# ---- 1. Build the dashboard ----
FROM node:22-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# ---- 2. The server ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASHBOARD_DIR=/app/dashboard
WORKDIR /app/server
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ .
COPY --from=dashboard /dashboard/dist /app/dashboard
# The Django admin's CSS and JS (the key is only for this build step)
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput
CMD ["sh", "start.sh"]
