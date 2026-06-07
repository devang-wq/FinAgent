from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.routers import chat, entity, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    from observability.setup import setup_telemetry
    setup_telemetry("finagent-api")
    yield


app = FastAPI(
    title="FinAgent Compliance API",
    description="AML / PEP / sanctions investigation platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(chat.router)
app.include_router(entity.router)
app.include_router(search.router)
