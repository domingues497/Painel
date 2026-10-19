"""Rotas administrativas para configurar a conexão com o Zabbix."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dotenv import set_key
from config import BASE_DIR, ZABBIX_URL, ZABBIX_AUTH_TYPE, ZABBIX_USERNAME, VERIFY_TLS
from services.zabbix_client import test_connection

router = APIRouter(prefix="/api/settings", tags=["Configuração"])

class ConnectionSettings(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    auth_type: str = "token"
    token: str = ""
    username: str = ""
    password: str = ""
    verify_tls: bool = True

@router.get("")
def get_settings():
    return {"url": ZABBIX_URL, "auth_type": ZABBIX_AUTH_TYPE,
            "username": ZABBIX_USERNAME, "verify_tls": VERIFY_TLS,
            "configured": bool(ZABBIX_URL)}

@router.post("/test")
def test_settings(settings: ConnectionSettings):
    try:
        return test_connection(url=settings.url.strip(), auth_type=settings.auth_type,
            token=settings.token.strip(), username=settings.username.strip(),
            password=settings.password, verify_tls=settings.verify_tls)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Falha na conexão: {exc}")

@router.post("/save")
def save_settings(settings: ConnectionSettings):
    url = settings.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="A URL deve começar com http:// ou https://.")
    if settings.auth_type == "token" and not settings.token.strip():
        raise HTTPException(status_code=400, detail="Informe o token da API.")
    if settings.auth_type == "password" and (not settings.username.strip() or not settings.password):
        raise HTTPException(status_code=400, detail="Informe usuário e senha.")
    try:
        test_connection(url=url, auth_type=settings.auth_type, token=settings.token.strip(),
            username=settings.username.strip(), password=settings.password, verify_tls=settings.verify_tls)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Não foi salvo. Teste de conexão falhou: {exc}")
    env_path = BASE_DIR / ".env"
    set_key(str(env_path), "ZABBIX_URL", url)
    set_key(str(env_path), "ZABBIX_AUTH_TYPE", settings.auth_type)
    set_key(str(env_path), "ZABBIX_TOKEN", settings.token.strip() if settings.auth_type == "token" else "")
    set_key(str(env_path), "ZABBIX_USERNAME", settings.username.strip() if settings.auth_type == "password" else "")
    set_key(str(env_path), "ZABBIX_PASSWORD", settings.password if settings.auth_type == "password" else "")
    set_key(str(env_path), "VERIFY_TLS", "1" if settings.verify_tls else "0")
    return {"success":True,"message":"Conexão validada e salva no .env. Reinicie o servidor para aplicar aos painéis.","restart_required":True}
