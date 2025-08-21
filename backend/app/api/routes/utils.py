import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.tasks import celery_app

router = APIRouter()

@router.get("/health-check", tags=["utils"])
async def health_check() -> bool:
    return True


class TaskStatus(BaseModel):
    task_id: uuid.UUID
    finished: bool
    success: bool
    state: str


@router.get(
    "/task-check/{task_id}", tags=["utils"], response_model=TaskStatus
)
async def check_tasks(
    task_id: uuid.UUID,
) -> TaskStatus:
    task = celery_app.AsyncResult(str(task_id))
    return TaskStatus(
        task_id=task_id,
        finished=task.ready(),
        success=task.successful(),
        state=task.state,
    )
