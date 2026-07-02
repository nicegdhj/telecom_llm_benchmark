import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.db import init_db
from backend.app.routers import analytics as analytics_router
from backend.app.routers import auth as auth_router
from backend.app.routers import batches as batches_router
from backend.app.routers import users as users_router
from backend.app.routers import evaluations as evaluations_router
from backend.app.routers import judges as judges_router
from backend.app.routers import jobs as jobs_router
from backend.app.routers import models as models_router
from backend.app.routers import predictions as predictions_router
from backend.app.routers import tasks as tasks_router
from backend.app.services.session_cleanup import session_cleanup_loop
from backend.app.services.worker import worker_loop


_worker_task = None
_session_cleanup_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task, _session_cleanup_task
    init_db()
    _worker_task = asyncio.create_task(worker_loop())
    _session_cleanup_task = asyncio.create_task(session_cleanup_loop())
    yield
    if _worker_task:
        _worker_task.cancel()
    if _session_cleanup_task:
        _session_cleanup_task.cancel()


app = FastAPI(title="Eval Backend", version="0.2.0", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(models_router.router)
app.include_router(judges_router.router)
app.include_router(tasks_router.router)
app.include_router(batches_router.router)
app.include_router(jobs_router.router)
app.include_router(predictions_router.router)
app.include_router(evaluations_router.router)
app.include_router(analytics_router.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
