"""Celery configuration.

* JSON only: pickle is disabled (CWE-502), so a poisoned queue message cannot execute code.
* Late acks + reject-on-worker-lost + idempotent tasks = safe retries.
* Hard time limits bound the damage of a stuck or abused task (CWE-770).
* TLS with certificate verification when the broker URL is rediss://.
"""
import ssl

from celery import Celery

from app.core.config import Settings, get_settings


def make_celery(settings: Settings | None = None) -> Celery:
    settings = settings or get_settings()
    url = settings.redis_url.get_secret_value()
    app = Celery("releaseradar", broker=url, include=["app.workers.tasks.events"])
    app.conf.update(
        task_serializer="json", accept_content=["json"], result_serializer="json",
        task_ignore_result=True, task_acks_late=True, task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1, task_time_limit=60, task_soft_time_limit=45,
        broker_connection_retry_on_startup=True, enable_utc=True,
    )
    if url.startswith("rediss://"):
        app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    app.set_default()
    return app


def celery_app() -> Celery:  # `celery -A app.workers.celery_app:celery_app worker`
    return make_celery()
