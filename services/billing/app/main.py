"""Billing Service main application"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.logging import configure_logging, get_logger
from .core.config import settings
from .services.message_consumer import BillingConsumer
from .models.database import init_db, close_db
from .api.v1 import health as health_router
from .api.v1 import usage as usage_router

configure_logging()
logger=get_logger(__name__)
consumer=BillingConsumer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await consumer.start()
    yield
    await consumer.stop()
    await close_db()

app=FastAPI(title="Billing Service",version=settings.service_version,lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.allow_origins,allow_methods=["*"],allow_headers=["*"],)

app.include_router(health_router.router,prefix="/health",tags=["Health"])
app.include_router(usage_router.router,prefix="/api/v1/billing",tags=["Billing"])

if __name__=="__main__":
    import uvicorn
    uvicorn.run("app.main:app",host=settings.service_host,port=settings.service_port,reload=settings.debug) 