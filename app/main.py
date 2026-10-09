from contextlib import asynccontextmanager
from pathlib import Path
import os
import sys
import threading

# F5 / python app/main.py: work from any cwd by pinning the project root.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

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
    description='Campus clinic appointment desk.',
    version='0.1.0',
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')


if __name__ == '__main__':
    import uvicorn
    from run import HOST, PREFERRED, choose_port, open_browser

    port = choose_port(HOST, PREFERRED)
    url = f'http://{HOST}:{port}/'
    print(f'ClinicDesk starting on {url}', flush=True)
    threading.Thread(target=open_browser, args=(url, HOST, port), daemon=True).start()
    uvicorn.run(app, host=HOST, port=port, workers=1)
