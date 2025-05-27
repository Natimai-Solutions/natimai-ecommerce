import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.tasks import celery_app

from .core import login_routes
from .core.address import routes as address
from .core.company import routes as company
from .core.fenuapay import routes as fenuapay
from .core.file import routes as file
from .core.location.routes import island as island
from .core.location.routes import town as town
from .core.service import routes as service
from .core.task import routes as task
from .core.user import routes as user
from .core.user import routes_sponsorship as sponsorship
from .modules.contact.routes import contact as contact
from .modules.contact.routes import message as contact_message
from .modules.ia import routes as ia
from .modules.project.routes import (
    detail as project_detail,
)
from .modules.project.routes import (
    detail_answer as project_detail_answer,
)
from .modules.project.routes import (
    detail_option as project_detail_option,
)
from .modules.project.routes import (
    project as project,
)
from .modules.project.routes import (
    proposal as project_proposal,
)
from .modules.project.routes import (
    rating as project_rating,
)
from .modules.project.routes import (
    rating_answer as project_rating_answer,
)
from .modules.project.routes import (
    rating_category as project_rating_category,
)
from .modules.realization import routes as realization

api_router = APIRouter()

api_router.include_router(login_routes.router, tags=["login"])
api_router.include_router(file.router, prefix="/file", tags=["file"])
api_router.include_router(
    fenuapay.router,
    prefix="/fenuapay",
    tags=["fenuapay"],
)
api_router.include_router(address.router, prefix="/address", tags=["address"])
api_router.include_router(company.router, prefix="/company", tags=["company"])
api_router.include_router(contact.router, prefix="/contact", tags=["contact"])
api_router.include_router(
    contact_message.router, prefix="/contact_message", tags=["contact"]
)
api_router.include_router(ia.router, prefix="/ia", tags=["ai"])
api_router.include_router(island.router, prefix="/island", tags=["localization"])
api_router.include_router(project.router, prefix="/project", tags=["project"])
api_router.include_router(
    project_detail.router, prefix="/project_detail", tags=["project detail"]
)
api_router.include_router(
    project_detail_option.router,
    prefix="/project_detail_option",
    tags=["project detail option"],
)
api_router.include_router(
    project_detail_answer.router,
    prefix="/project_detail_answer",
    tags=["project detail answer"],
)
api_router.include_router(
    project_proposal.router, prefix="/project_proposal", tags=["project proposal"]
)
api_router.include_router(
    project_rating.router, prefix="/project_rating", tags=["rating"]
)
api_router.include_router(
    project_rating_answer.router, prefix="/project_rating_answer", tags=["rating"]
)
api_router.include_router(
    project_rating_category.router, prefix="/project_rating_category", tags=["rating"]
)
api_router.include_router(service.router, prefix="/service", tags=["service"])
api_router.include_router(town.router, prefix="/town", tags=["localization"])
api_router.include_router(
    realization.router, prefix="/realization", tags=["realization", "company"]
)
api_router.include_router(
    sponsorship.router, prefix="/sponsorship", tags=["sponsorship"]
)
api_router.include_router(task.router, prefix="/task", tags=["task"])
api_router.include_router(user.router, prefix="/user", tags=["users"])


@api_router.get("/utils/health-check", tags=["utils"])
async def health_check() -> bool:
    return True


class TaskStatus(BaseModel):
    task_id: uuid.UUID
    finished: bool
    success: bool
    state: str


@api_router.get(
    "/utils/task-check/{task_id}", tags=["utils"], response_model=TaskStatus
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
