"""API para configurar e testar alertas por e-mail/Telegram."""
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services import alert_manager

router = APIRouter(prefix="/api/alerts", tags=["Alertas"])


class AlertConfig(BaseModel):
    monitor_enabled: bool = False
    severity_levels: list[int] = Field(default_factory=lambda: [4, 5])
    # Optional to distinguish current multi-select clients from legacy single-select payloads.
    host_type_filters: Optional[list[Literal["all", "switches", "servers", "computers", "network"]]] = None
    # Compatibilidade com clientes antigos que enviam apenas um tipo.
    host_type_filter: Optional[Literal["all", "switches", "servers", "computers", "network"]] = None
    interval_seconds: int = Field(default=60, ge=15, le=3600)
    email_enabled: bool = False
    email_smtp_host: str = ""
    email_smtp_port: int = Field(default=587, ge=1, le=65535)
    email_security: Literal["starttls", "ssl", "none"] = "starttls"
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_recipients: list[str] = Field(default_factory=list)
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_ids: list[str] = Field(default_factory=list)


@router.get("/config")
def get_alert_config():
    return alert_manager.public_config()


@router.post("/config")
def save_alert_config(config: AlertConfig):
    try:
        payload = config.dict(exclude_none=True)
        supplied_fields = getattr(config, "model_fields_set", getattr(config, "__fields_set__", set()))
        # Honor the actual field supplied by the current checkbox UI. The model uses None
        # (not ["all"]) as default so legacy singular clients cannot be shadowed by a default.
        if "host_type_filters" in supplied_fields and payload.get("host_type_filters") is not None:
            host_types = list(dict.fromkeys(payload.get("host_type_filters") or []))
        elif payload.get("host_type_filter"):
            host_types = [payload["host_type_filter"]]
        else:
            host_types = ["all"]
        payload.pop("host_type_filter", None)
        allowed_types = {"all", "switches", "servers", "computers", "network"}
        host_types = [v for v in host_types if v in allowed_types]
        if "all" in host_types:
            host_types = ["all"]
        if not host_types:
            raise HTTPException(status_code=400, detail="Selecione Todos os hosts ou pelo menos uma categoria.")
        payload["host_type_filters"] = host_types
        if any(level < 0 or level > 5 for level in payload["severity_levels"]):
            raise HTTPException(status_code=400, detail="As severidades devem ficar entre 0 e 5.")
        payload["email_recipients"] = [v.strip() for v in payload["email_recipients"] if v.strip()]
        payload["telegram_chat_ids"] = [v.strip() for v in payload["telegram_chat_ids"] if v.strip()]
        return {"success": True, "message": "Configuração de alertas salva.", "config": alert_manager.save_config(payload)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Não foi possível salvar os alertas: {exc}") from exc


@router.get("/status")
def get_alert_status():
    return alert_manager.public_status()


@router.post("/test")
def test_alerts():
    try:
        return alert_manager.send_test()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Falha no teste das notificações: {str(exc)[:250]}") from exc
