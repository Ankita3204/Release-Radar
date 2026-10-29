FROM python:3.12-slim AS build
WORKDIR /w
COPY requirements.lock.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock.txt

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 --no-create-home releaseradar
COPY --from=build /install /usr/local
WORKDIR /srv
COPY app ./app
COPY alembic.ini .
USER 10001
EXPOSE 8000
# --forwarded-allow-ips must be the real proxy address(es), never "*" in production.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\" --no-server-header"]
