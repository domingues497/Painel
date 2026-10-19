"""Aplicação principal do Painel Zabbix. Registra routers e configura o FastAPI."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers import alerts, executive, hosts, network, pages, settings, switches
import asyncio
from services.alert_manager import monitor_loop

app = FastAPI(title="Painel de infraestrutura Zabbix", version="2.0.0")

app.include_router(settings.router)
app.include_router(alerts.router)
app.include_router(switches.router)
app.include_router(hosts.router)
app.include_router(network.router)
app.include_router(executive.router)
app.include_router(pages.router)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


_alert_monitor_task = None

@app.on_event("startup")
async def start_alert_monitor():
    """Inicia o monitor de alertas em segundo plano."""
    global _alert_monitor_task
    if _alert_monitor_task is None or _alert_monitor_task.done():
        _alert_monitor_task = asyncio.create_task(monitor_loop())

@app.on_event("shutdown")
async def stop_alert_monitor():
    """Encerra a tarefa de monitoramento de forma limpa."""
    global _alert_monitor_task
    if _alert_monitor_task is not None:
        _alert_monitor_task.cancel()
        try:
            await _alert_monitor_task
        except asyncio.CancelledError:
            pass
        _alert_monitor_task = None
