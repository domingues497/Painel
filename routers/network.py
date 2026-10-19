from fastapi import APIRouter
from services import dashboard

router = APIRouter()

@router.get("/api/network")
def api_network():
    return dashboard.get_network()
