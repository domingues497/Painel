from fastapi import APIRouter
from services import dashboard

router = APIRouter()

@router.get("/api/hosts")
def api_hosts(kind: str = "all"):


    return dashboard.get_hosts(kind)
