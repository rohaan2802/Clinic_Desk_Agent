from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import router
from app.config import ROOT
from app.memory import Memory


@asynccontextmanager
async def lifespan(app):
    app.state.memory = Memory()
    app.state.busy = set()
    yield


app = FastAPI(
    title='ClinicDesk Agent Arena',
    description='Bounded campus clinic appointment agent for the Agent Arena assignment.',
    lifespan=lifespan,
)
app.include_router(router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')
