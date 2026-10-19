from fastapi import APIRouter
from services import dashboard

router = APIRouter()

@router.get("/api/executive")
def api_executive(days: int = 7, unit: str = "", criticality: str = ""):
    return dashboard.get_executive(days, unit, criticality)
