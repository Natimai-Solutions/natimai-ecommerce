from celery import Celery

from app.core.config import settings

if settings.REDIS_CELERY_USER and settings.REDIS_CELERY_PASSWORD:
    BROKER_URL = f"redis://{settings.REDIS_CELERY_USER}:{settings.REDIS_CELERY_PASSWORD}@{settings.REDIS_SERVER}:{settings.REDIS_PORT}/{settings.REDIS_CELERY_DB_INDEX}"
    BACKEND_URL = f"redis://{settings.REDIS_CELERY_USER}:{settings.REDIS_CELERY_PASSWORD}@{settings.REDIS_SERVER}:{settings.REDIS_PORT}/{settings.REDIS_CELERY_DB_INDEX}"
else:
    BROKER_URL = f"redis://{settings.REDIS_SERVER}:{settings.REDIS_PORT}/{settings.REDIS_CELERY_DB_INDEX}"
    BACKEND_URL = f"redis://{settings.REDIS_SERVER}:{settings.REDIS_PORT}/{settings.REDIS_CELERY_DB_INDEX}"

task_imports = ["app.api.tasks"]

celery_app = Celery(
    "fenuapro", broker=BROKER_URL, backend=BACKEND_URL, include=task_imports
)
