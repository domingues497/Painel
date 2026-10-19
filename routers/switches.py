from fastapi import APIRouter
from services import dashboard

router = APIRouter()

@router.get("/api/switches")
def api_switches():
    return dashboard.get_switches()
