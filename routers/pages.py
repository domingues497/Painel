from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent

@router.get("/", include_in_schema=False)
def dashboard_home():
    return FileResponse(BASE_DIR / "index.html")

@router.get("/hosts.html", include_in_schema=False)
def dashboard_hosts():
    return FileResponse(BASE_DIR / "hosts.html")

@router.get("/rede.html", include_in_schema=False)
def dashboard_network():
    return FileResponse(BASE_DIR / "rede.html")


@router.get("/configuracao.html", include_in_schema=False)
def dashboard_settings():
    return FileResponse(BASE_DIR / "configuracao.html")


@router.get("/executivo.html", include_in_schema=False)
def dashboard_executive_page():
    return FileResponse(BASE_DIR / "executivo.html")
