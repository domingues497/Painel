"""Configuração e envio de alertas do Zabbix por e-mail e Telegram."""
from __future__ import annotations

import asyncio
import json
import os
import html
import smtplib
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests
from config import BASE_DIR, ZABBIX_URL
from services.zabbix_client import zbx
from services import dashboard

def _data_dir() -> Path:
    """Diretório persistente fora da pasta de instalação do painel.

    Isso evita perder a configuração ao atualizar/substituir os arquivos do projeto
    e compartilha a configuração entre reinicializações do processo.
    """
    override = os.getenv("PANEL_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA", "").strip()
        if root:
            return Path(root) / "PainelZabbix"
    root = os.getenv("XDG_DATA_HOME", "").strip()
    if root:
        return Path(root).expanduser() / "PainelZabbix"
    return Path.home() / ".local" / "share" / "PainelZabbix"


DATA_DIR = _data_dir()
CONFIG_PATH = DATA_DIR / "alert_config.json"
STATE_PATH = DATA_DIR / "alert_state.json"
# Migra automaticamente arquivos criados pelas versões anteriores, quando existirem.
LEGACY_CONFIG_PATH = BASE_DIR / "alert_config.json"
LEGACY_STATE_PATH = BASE_DIR / "alert_state.json"
_LOCK = threading.RLock()
_STATUS: dict[str, Any] = {
    "last_poll": None,
    "last_error": "",
    "active_problems": 0,
    "matched_problems": 0,
    "skipped_by_severity": 0,
    "skipped_by_host_type": 0,
    "notifications_sent": 0,
    "email_attempts": 0,
    "email_sent": 0,
    "email_failures": 0,
    "telegram_attempts": 0,
    "telegram_sent": 0,
    "telegram_failures": 0,
    "deduplicated_targets": 0,
    "last_decision": "",
    "last_problem": None,
    "last_notification": None,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "monitor_enabled": False,
    "severity_levels": [4, 5],
    "host_type_filters": ["all"],
    "interval_seconds": 60,
    "email_enabled": False,
    "email_smtp_host": "smtp.office365.com",
    "email_smtp_port": 587,
    "email_security": "starttls",
    "email_username": "",
    "email_password": "",
    "email_from": "",
    "email_recipients": [],
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_ids": [],
}

SEVERITY_NAMES = {
    0: "Não classificado",
    1: "Informação",
    2: "Aviso",
    3: "Média",
    4: "Alta",
    5: "Desastre",
}


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, path)


def _migrate_legacy_file(old_path: Path, new_path: Path) -> None:
    """Move old in-project JSON data to the persistent user-data directory once."""
    if new_path.exists() or not old_path.exists():
        return
    old_value = _read_json(old_path, None)
    if isinstance(old_value, dict):
        _write_json(new_path, old_value)


def _config() -> dict[str, Any]:
    with _LOCK:
        _migrate_legacy_file(LEGACY_CONFIG_PATH, CONFIG_PATH)
        loaded = _read_json(CONFIG_PATH, {})
        loaded = loaded if isinstance(loaded, dict) else {}
        # Migração específica para a caixa da Witmarsum, confirmada como Exchange Online.
        # Os hostnames locais de entrada/legados não correspondem ao endpoint SMTP
        # autenticado do Microsoft 365. Corrige somente esses valores conhecidos.
        old_host = str(loaded.get("email_smtp_host", "")).strip().lower()
        if old_host in {"smtp.witmarsum.coop.br", "mail.witmarsum.coop.br", "smtp@witmarsum.coop.br"}:
            loaded["email_smtp_host"] = "smtp.office365.com"
            loaded["email_smtp_port"] = 587
            loaded["email_security"] = "starttls"
            loaded["_m365_smtp_migrated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            _write_json(CONFIG_PATH, loaded)
        # Migra o campo singular usado pelas versões anteriores para seleção múltipla.
        allowed_host_types = {"all", "switches", "servers", "computers", "network"}
        if not isinstance(loaded.get("host_type_filters"), list):
            legacy_type = loaded.get("host_type_filter", "all")
            loaded["host_type_filters"] = [legacy_type if legacy_type in allowed_host_types else "all"]
        config = {**DEFAULT_CONFIG, **loaded}
        config["severity_levels"] = sorted({int(x) for x in config.get("severity_levels", [4, 5]) if str(x).isdigit() and 0 <= int(x) <= 5})
        host_types = [x for x in _as_list(config.get("host_type_filters", ["all"])) if x in allowed_host_types]
        if not host_types:
            host_types = ["all"]
        if "all" in host_types:
            host_types = ["all"]
        config["host_type_filters"] = list(dict.fromkeys(host_types))
        config.pop("host_type_filter", None)
        config["email_recipients"] = _as_list(config.get("email_recipients", []))
        config["telegram_chat_ids"] = _as_list(config.get("telegram_chat_ids", []))
        return config


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return list(dict.fromkeys(str(x).strip() for x in values if str(x).strip()))


def public_config() -> dict[str, Any]:
    config = _config()
    public = {key: value for key, value in config.items() if key not in {"email_password", "telegram_bot_token"}}
    public["email_password_saved"] = bool(config.get("email_password"))
    public["telegram_bot_token_saved"] = bool(config.get("telegram_bot_token"))
    public["config_saved_at"] = config.get("_saved_at")
    # Campo singular de compatibilidade para interfaces antigas. Em seleção múltipla,
    # retorna all apenas como fallback; a interface atual usa host_type_filters.
    selected_types = config.get("host_type_filters", ["all"])
    public["host_type_filter"] = selected_types[0] if len(selected_types) == 1 else "all"
    public["config_storage_version"] = 3
    return public


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        _migrate_legacy_file(LEGACY_CONFIG_PATH, CONFIG_PATH)
        current = _config()
        config = {**current, **payload}
        # Segredos são omitidos da resposta pública. Campo em branco preserva o segredo salvo.
        if not str(payload.get("email_password", "")).strip():
            config["email_password"] = current.get("email_password", "")
        if not str(payload.get("telegram_bot_token", "")).strip():
            config["telegram_bot_token"] = current.get("telegram_bot_token", "")
        config["severity_levels"] = sorted({int(x) for x in payload.get("severity_levels", []) if str(x).isdigit() and 0 <= int(x) <= 5})
        # Normalize selected host categories at the persistence boundary too, so config
        # remains valid even when posted by a client other than executivo.html.
        allowed_host_types = {"all", "switches", "servers", "computers", "network"}
        host_types = [x for x in _as_list(config.get("host_type_filters", ["all"])) if x in allowed_host_types]
        if not host_types or "all" in host_types:
            host_types = ["all"]
        config["host_type_filters"] = list(dict.fromkeys(host_types))
        config.pop("host_type_filter", None)
        config["interval_seconds"] = max(15, min(3600, int(config.get("interval_seconds", 60))))
        config["email_smtp_port"] = max(1, min(65535, int(config.get("email_smtp_port", 587))))
        config["email_recipients"] = _as_list(config.get("email_recipients", []))
        config["telegram_chat_ids"] = _as_list(config.get("telegram_chat_ids", []))
        config["email_security"] = config.get("email_security", "starttls") if config.get("email_security") in {"starttls", "ssl", "none"} else "starttls"
        config["_saved_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _write_json(CONFIG_PATH, config)
        # Confirma leitura de volta do mesmo arquivo; não declara sucesso se o dado
        # escrito não corresponder ao pedido recebido pela API.
        persisted = _read_json(CONFIG_PATH, None)
        if not isinstance(persisted, dict):
            raise RuntimeError(f"A configuração não foi encontrada após gravar em {CONFIG_PATH}.")
        verify_fields = (
            "email_smtp_host", "email_smtp_port", "email_security", "email_username",
            "email_from", "email_recipients", "email_enabled", "telegram_enabled",
            "telegram_chat_ids", "monitor_enabled", "interval_seconds", "severity_levels", "host_type_filters",
        )
        mismatches = [key for key in verify_fields if persisted.get(key) != config.get(key)]
        if mismatches:
            raise RuntimeError("A configuração foi gravada, mas a leitura de confirmação divergiu nos campos: " + ", ".join(mismatches))
    return public_config()


def _status_update(**values: Any) -> None:
    with _LOCK:
        _STATUS.update(values)


def public_status() -> dict[str, Any]:
    with _LOCK:
        status = dict(_STATUS)
    cfg = _config()
    status["monitor_enabled"] = bool(cfg["monitor_enabled"] and (cfg["email_enabled"] or cfg["telegram_enabled"]))
    status["zabbix_configured"] = bool(ZABBIX_URL)
    status["severity_levels"] = list(cfg.get("severity_levels", []))
    status["host_type_filters"] = list(cfg.get("host_type_filters", ["all"]))
    status["email_enabled"] = bool(cfg.get("email_enabled"))
    status["telegram_enabled"] = bool(cfg.get("telegram_enabled"))
    return status


def _problem_rows() -> list[dict[str, Any]]:
    # problem.get (Zabbix 7.x) does not support selectHosts. Retrieve active
    # trigger problems first, then resolve host information with trigger.get.
    rows = zbx(
        "problem.get",
        {
            "output": ["eventid", "name", "severity", "clock", "objectid"],
            "sortfield": ["eventid"],
            "sortorder": "DESC",
            # Keep enough rows so a busy Zabbix with many active problems does not
            # silently omit a newly raised outage from the alert worker.
            "limit": 1000,
        },
    ) or []
    if not rows:
        return []

    trigger_ids = sorted({
        str(row.get("objectid")) for row in rows
        if row.get("objectid") and str(row.get("objectid")).isdigit()
    })
    hosts_by_trigger: dict[str, list[dict[str, Any]]] = {}
    if trigger_ids:
        triggers = zbx(
            "trigger.get",
            {
                "output": ["triggerid"],
                "triggerids": trigger_ids,
                "selectHosts": "extend",
            },
        ) or []
        for trigger in triggers:
            hosts_by_trigger[str(trigger.get("triggerid", ""))] = trigger.get("hosts", []) or []

    # Retrieve each host's groups so the alert rule can filter switches, servers,
    # workstations and network devices using the same classification as the dashboard.
    all_hosts: dict[str, dict[str, Any]] = {}
    for trigger_hosts in hosts_by_trigger.values():
        for host in trigger_hosts:
            host_id = str(host.get("hostid") or "")
            if host_id:
                all_hosts[host_id] = host
    host_details: dict[str, dict[str, Any]] = {}
    if all_hosts:
        details = zbx(
            "host.get",
            {
                "output": ["hostid", "host", "name"],
                "hostids": list(all_hosts),
                "selectHostGroups": ["groupid", "name"],
            },
        ) or []
        host_details = {str(host.get("hostid")): host for host in details}

    for row in rows:
        trigger_hosts = hosts_by_trigger.get(str(row.get("objectid", "")), [])
        enriched_hosts = []
        for trigger_host in trigger_hosts:
            host_id = str(trigger_host.get("hostid") or "")
            details = host_details.get(host_id, {})
            merged = {**details, **trigger_host}
            # Prefer technical host name from host.get for configured switch-name matching.
            if details.get("host"):
                merged["host"] = details["host"]
            merged["hostgroups"] = details.get("hostgroups", []) or []
            enriched_hosts.append(merged)
        row["hosts"] = enriched_hosts
    return rows


def _alert_host_type(host: dict[str, Any]) -> str:
    """Classify hosts consistently, tolerating group/name variations in Zabbix."""
    groups_data = host.get("hostgroups", []) or []
    groups = [str(group.get("name", "")).strip() for group in groups_data if isinstance(group, dict)]
    technical_name = str(host.get("host") or "").strip()
    visible_name = str(host.get("name") or "").strip()
    role = dashboard.role_of({"host": technical_name, "name": visible_name, "tags": host.get("tags", [])}, groups)
    if role == "switch":
        return "switches"
    if role in {"wan", "device"}:
        return "network"

    normalized = [g.casefold() for g in groups]
    kind = dashboard.classify(groups)
    if kind == "server" or any(any(word in g for word in ("server", "servidor", "servidores")) for g in normalized):
        return "servers"
    if kind == "workstation" or any(any(word in g for word in ("workstation", "computador", "desktop", "notebook", "laptop", "usuários windows", "usuarios windows")) for g in normalized):
        return "computers"

    # Some Zabbix setups only use broad groups such as "Discovered hosts".
    # A technical host name can still carry an unambiguous role prefix/suffix.
    combined_name = f"{technical_name} {visible_name}".casefold()
    if any(token in combined_name for token in ("server", "servidor", "-srv-", "_srv_", "srv-", "srv_")):
        return "servers"
    if dashboard.NETWORK_HOST_RE.search(combined_name):
        return "network"
    return "other"


def _filter_problem_by_host_type(config: dict[str, Any], problem: dict[str, Any]) -> dict[str, Any] | None:
    """Filter event hosts using all selected categories, or keep all hosts when requested."""
    selected = config.get("host_type_filters")
    if not isinstance(selected, list):
        selected = [str(config.get("host_type_filter", "all"))]
    selected = set(str(x) for x in selected)
    if not selected or "all" in selected:
        return problem
    hosts = problem.get("hosts", []) or []
    matched = [host for host in hosts if _alert_host_type(host) in selected]
    if not matched:
        return None
    filtered = dict(problem)
    filtered["hosts"] = matched
    return filtered


def _fmt_uptime(value: Any) -> str:
    'Format seconds as a readable duration; omit unsupported/missing values.'
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return "Não disponível"
    days, remainder = divmod(seconds, 86400)
    hours = remainder // 3600
    return f"{days} d {hours} h" if days else f"{hours} h"


def _fmt_percent(value: Any) -> str:
    try:
        return f"{float(value):.2f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "Não disponível"


def _event_text(problem: dict[str, Any], host_snapshots: dict[str, dict[str, Any]] | None = None) -> tuple[str, str, str]:
    'Create a plain-text fallback and an Outlook-compatible HTML alert card.'
    host_snapshots = host_snapshots or {}
    severity = int(problem.get("severity", 0))
    severity_name = SEVERITY_NAMES.get(severity, str(severity))
    severity_colors = {
        0: ("#64748b", "#e2e8f0"), 1: ("#2563eb", "#dbeafe"),
        2: ("#ca8a04", "#fef3c7"), 3: ("#ea580c", "#ffedd5"),
        4: ("#dc2626", "#fee2e2"), 5: ("#991b1b", "#fecaca"),
    }
    accent, badge_bg = severity_colors.get(severity, severity_colors[0])
    problem_name = str(problem.get("name") or "Problema sem descrição")
    hosts = problem.get("hosts", []) or []
    names = [str(host.get("name") or host.get("host") or "Host sem nome") for host in hosts]
    host_text = ", ".join(dict.fromkeys(names)) or "Host não informado"
    try:
        started = datetime.fromtimestamp(int(problem.get("clock", 0))).astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError, OSError):
        started = "horário não informado"
    event_id = str(problem.get("eventid", "N/D"))
    subject = f"[Zabbix][{severity_name}] {host_text}"

    card_texts: list[str] = []
    cards_html: list[str] = []
    matched_hosts = hosts or [{"name": host_text, "hostid": ""}]
    for host in matched_hosts:
        host_id = str(host.get("hostid") or host.get("id") or "")
        snapshot = host_snapshots.get(host_id, {})
        host_name = str(snapshot.get("name") or host.get("name") or host.get("host") or "Host sem nome")
        status = str(snapshot.get("status") or "unknown").lower()
        status_label = "Online" if status == "online" else "O Zabbix não consegue falar com este servidor" if status == "offline" else "Status não disponível"
        uptime = _fmt_uptime(snapshot.get("uptime"))
        availability = _fmt_percent(snapshot.get("availability"))
        unsupported = snapshot.get("unsupported")
        unsupported_text = f"{unsupported} item(ns) não suportado(s)" if isinstance(unsupported, (int, float)) else "Não disponível"
        card_texts.append(
            f"Servidor: {host_name}\nStatus: {status_label}\nUptime: {uptime}\n"
            f"Disponibilidade 24 h: {availability}\nColeta: {unsupported_text}"
        )
        safe_host = html.escape(host_name)
        safe_status = html.escape(status_label)
        safe_uptime = html.escape(uptime)
        safe_availability = html.escape(availability)
        safe_unsupported = html.escape(unsupported_text)
        safe_problem = html.escape(problem_name)
        safe_started = html.escape(started)
        safe_event_id = html.escape(event_id)
        safe_severity = html.escape(severity_name)
        cards_html.append(f'''<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width:100%;border-collapse:separate;border-spacing:0;margin:0 0 18px 0;background:#1b2430;border:1px solid #344154;border-top:4px solid {accent};border-radius:8px;color:#e8eef7;font-family:Segoe UI,Arial,sans-serif;">
<tr><td style="padding:18px 18px 8px 18px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"><tr><td style="font-size:17px;font-weight:700;color:#f8fafc;">{safe_host}</td><td align="right" style="text-align:right;"><span style="display:inline-block;background:{badge_bg};color:{accent};font-size:12px;font-weight:700;padding:5px 10px;border-radius:16px;">{safe_severity}</span></td></tr></table></td></tr>
<tr><td style="padding:0 18px 12px 18px;font-size:14px;line-height:1.5;color:#c9d7e8;">{safe_status}</td></tr>
<tr><td style="padding:0 18px 14px 18px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;"><tr><td colspan="2" style="padding:10px 12px;background:#111820;border-radius:5px;color:#f8fafc;font-size:14px;line-height:1.5;"><strong>Problema detectado</strong><br>{safe_problem}</td></tr>
<tr><td width="50%" style="padding:12px 8px 4px 0;color:#93a4bb;font-size:12px;">Uptime</td><td width="50%" style="padding:12px 0 4px 8px;color:#93a4bb;font-size:12px;">Disponibilidade 24 h</td></tr><tr><td style="padding:0 8px 10px 0;color:#f1f5f9;font-size:14px;font-weight:600;">{safe_uptime}</td><td style="padding:0 0 10px 8px;color:#f1f5f9;font-size:14px;font-weight:600;">{safe_availability}</td></tr>
<tr><td colspan="2" style="padding:8px 0;border-top:1px solid #344154;color:#cbd5e1;font-size:12px;">Coleta: {safe_unsupported}</td></tr></table></td></tr>
<tr><td style="padding:11px 18px;background:#151c25;border-top:1px solid #344154;font-size:11px;color:#93a4bb;">Início: {safe_started} &nbsp; | &nbsp; Evento Zabbix: {safe_event_id}</td></tr></table>''')

    body = (
        "Alerta de infraestrutura detectado pelo Painel Executivo.\n\n"
        f"Severidade: {severity_name}\nHost(s): {host_text}\nProblema: {problem_name}\n"
        f"Início: {started}\nEvento Zabbix: {event_id}\n\n"
        + "\n\n".join(card_texts)
    )
    html_body = f'''<!doctype html><html><body style="margin:0;padding:0;background:#111820;color:#e8eef7;font-family:Segoe UI,Arial,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width:100%;background:#111820;"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0" width="680" style="width:100%;max-width:680px;"><tr><td style="padding:0 0 16px 0;color:#f8fafc;font-size:20px;font-weight:700;">Alerta de infraestrutura <span style="font-size:12px;font-weight:400;color:#9fb0c4;">PAINEL EXECUTIVO / ZABBIX</span></td></tr><tr><td style="padding:0 0 16px 0;color:#cbd5e1;font-size:13px;line-height:1.5;">Foi identificado um problema ativo no monitoramento. Confira o card abaixo.</td></tr><tr><td>{''.join(cards_html)}</td></tr><tr><td style="padding-top:4px;color:#64748b;font-size:11px;line-height:1.5;">Mensagem automática do Painel Executivo. Não responda a este e-mail.<br>Evento: {html.escape(event_id)}</td></tr></table></td></tr></table></body></html>'''
    return subject, body, html_body


def _send_email(config: dict[str, Any], recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
    host = str(config.get("email_smtp_host", "")).strip()
    sender = str(config.get("email_from", "")).strip()
    if not host or not sender:
        raise RuntimeError("Preencha o servidor SMTP e o e-mail remetente.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    port = int(config.get("email_smtp_port", 587))
    security = config.get("email_security", "starttls")
    context = ssl.create_default_context()
    smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    with smtp_class(host, port, timeout=20, context=context) if security == "ssl" else smtp_class(host, port, timeout=20) as smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        username = str(config.get("email_username", "")).strip()
        password = str(config.get("email_password", ""))
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def _send_telegram(config: dict[str, Any], chat_id: str, body: str) -> None:
    token = str(config.get("telegram_bot_token", "")).strip()
    if not token:
        raise RuntimeError("Informe o token do bot do Telegram.")
    # Do not surface the API URL/exception, because the URL contains the bot token.
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": body},
            timeout=15,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Telegram recusou a mensagem (HTTP {response.status_code}). Verifique token e chat ID.")
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError("Telegram não aceitou a mensagem. Verifique token, chat ID e permissões do bot.")
    except requests.RequestException as exc:
        raise RuntimeError("Falha de rede ao acessar o Telegram. Verifique internet e proxy/firewall.") from exc


def _state() -> dict[str, Any]:
    with _LOCK:
        _migrate_legacy_file(LEGACY_STATE_PATH, STATE_PATH)
        state = _read_json(STATE_PATH, {})
        return state if isinstance(state, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    # Bound persistent state size. Event IDs are unique and old entries are retained only for deduplication.
    if len(state) > 2500:
        state = dict(list(state.items())[-2000:])
    with _LOCK:
        _write_json(STATE_PATH, state)


def _deliver_problem(
    config: dict[str, Any],
    problem: dict[str, Any],
    state: dict[str, Any],
    host_snapshots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attempt delivery and return diagnostics explaining whether the event was sent."""
    result: dict[str, Any] = {
        "matched": 0, "skipped_by_severity": 0, "skipped_by_host_type": 0,
        "email_attempts": 0, "email_sent": 0, "email_failures": 0,
        "telegram_attempts": 0, "telegram_sent": 0, "telegram_failures": 0,
        "deduplicated_targets": 0, "errors": [], "decision": "",
    }
    event_id = str(problem.get("eventid", ""))
    if not event_id:
        result["decision"] = "Problema ignorado: evento sem eventid retornado pelo Zabbix."
        return result
    try:
        severity = int(problem.get("severity", 0))
    except (TypeError, ValueError):
        severity = 0
    names = [str(h.get("name") or h.get("host") or "Host sem nome") for h in (problem.get("hosts") or [])]
    host_label = ", ".join(dict.fromkeys(names)) or "host não identificado"
    problem_label = str(problem.get("name") or "problema sem descrição")

    if severity not in config["severity_levels"]:
        result["skipped_by_severity"] = 1
        result["decision"] = f"Evento {event_id} ({host_label}) ignorado: severidade {severity} não está selecionada. Problema: {problem_label}"
        return result
    filtered_problem = _filter_problem_by_host_type(config, problem)
    if filtered_problem is None:
        result["skipped_by_host_type"] = 1
        host_types = ", ".join(config.get("host_type_filters", ["all"]))
        result["decision"] = f"Evento {event_id} ({host_label}) ignorado pelo filtro de tipo de host [{host_types}]. Problema: {problem_label}"
        return result
    problem = filtered_problem
    result["matched"] = 1

    host_snapshots = host_snapshots or {}
    subject, body, html_body = _event_text(problem, host_snapshots)
    record = state.setdefault(event_id, {})
    destinations_enabled = False
    any_sent = False
    if config.get("email_enabled"):
        recipients = config.get("email_recipients", [])
        destinations_enabled = True
        if not recipients:
            result["errors"].append("E-mail está ativado, mas não há destinatários configurados.")
        for recipient in recipients:
            target_key = f"email:{recipient.lower()}"
            if record.get(target_key):
                result["deduplicated_targets"] += 1
                continue
            result["email_attempts"] += 1
            try:
                _send_email(config, recipient, subject, body, html_body)
                record[target_key] = True
                result["email_sent"] += 1
                any_sent = True
                _save_state(state)
            except Exception as exc:
                result["email_failures"] += 1
                result["errors"].append(f"E-mail ({recipient}): {str(exc)[:220]}")
    if config.get("telegram_enabled"):
        destinations_enabled = True
        chat_ids = config.get("telegram_chat_ids", [])
        if not chat_ids:
            result["errors"].append("Telegram está ativado, mas não há grupos/chat IDs configurados.")
        for chat_id in chat_ids:
            target_key = f"telegram:{chat_id}"
            if record.get(target_key):
                result["deduplicated_targets"] += 1
                continue
            result["telegram_attempts"] += 1
            try:
                _send_telegram(config, chat_id, f"{subject}\n\n{body}")
                record[target_key] = True
                result["telegram_sent"] += 1
                any_sent = True
                _save_state(state)
            except Exception as exc:
                result["telegram_failures"] += 1
                result["errors"].append(f"Telegram ({chat_id}): {str(exc)[:220]}")
    if any_sent:
        _status_update(notifications_sent=int(_STATUS.get("notifications_sent", 0)) + 1,
                       last_notification=datetime.now().astimezone().isoformat(timespec="seconds"))
    if result["errors"]:
        result["decision"] = f"Evento {event_id} elegível, mas houve falha de entrega: " + "; ".join(result["errors"][:2])
    elif result["email_sent"] or result["telegram_sent"]:
        result["decision"] = f"Evento {event_id} enviado para {result['email_sent']} destinatário(s) de e-mail e {result['telegram_sent']} destino(s) Telegram. Problema: {problem_label}"
    elif result["deduplicated_targets"] and destinations_enabled:
        result["decision"] = f"Evento {event_id} já havia sido notificado para todos os destinos habilitados; nenhuma duplicação enviada. Problema: {problem_label}"
    elif not destinations_enabled:
        result["decision"] = f"Evento {event_id} corresponde aos filtros, mas nenhum canal está habilitado. Problema: {problem_label}"
    return result


def poll_once() -> dict[str, Any]:
    config = _config()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if not config.get("monitor_enabled") or not (config.get("email_enabled") or config.get("telegram_enabled")):
        _status_update(last_poll=now, last_error="", last_decision="Monitoramento não executado: ative o monitor e pelo menos um canal de envio.")
        return {"active_problems": 0, "processed": 0, "matched_problems": 0}
    if not ZABBIX_URL:
        msg = "Conexão com o Zabbix não configurada."
        _status_update(last_error=msg, last_poll=now, last_decision=msg)
        return {"active_problems": 0, "processed": 0, "matched_problems": 0}
    config_issues = []
    if not config.get("severity_levels"):
        config_issues.append("Selecione ao menos uma severidade.")
    if config.get("email_enabled") and (not config.get("email_recipients") or not config.get("email_smtp_host") or not config.get("email_from")):
        config_issues.append("E-mail ativado, mas SMTP, remetente ou destinatários não estão completos.")
    if config.get("telegram_enabled") and (not config.get("telegram_bot_token") or not config.get("telegram_chat_ids")):
        config_issues.append("Telegram ativado, mas token do bot ou chat IDs não estão completos.")
    if config_issues:
        message = " ".join(config_issues)
        _status_update(last_poll=now, last_error=message, last_decision=message)
        return {"active_problems": 0, "processed": 0, "matched_problems": 0, "error": message}
    try:
        problems = _problem_rows()
        state = _state()
        # Resolve host snapshot cards once per polling cycle, not once per problem.
        host_snapshots: dict[str, dict[str, Any]] = {}
        try:
            dashboard_hosts = dashboard.get_hosts("all").get("hosts", [])
            host_snapshots = {str(row.get("id")): row for row in dashboard_hosts if row.get("id") is not None}
        except Exception:
            host_snapshots = {}

        totals = {
            "matched_problems": 0, "skipped_by_severity": 0, "skipped_by_host_type": 0,
            "email_attempts": 0, "email_sent": 0, "email_failures": 0,
            "telegram_attempts": 0, "telegram_sent": 0, "telegram_failures": 0,
            "deduplicated_targets": 0,
        }
        decisions: list[str] = []
        last_problem_info: dict[str, Any] | None = None
        for problem in problems:
            if last_problem_info is None:
                raw_hosts = problem.get("hosts", []) or []
                last_problem_info = {
                    "eventid": str(problem.get("eventid", "")),
                    "name": str(problem.get("name") or "Problema sem descrição"),
                    "severity": int(problem.get("severity", 0) or 0),
                    "hosts": [str(h.get("name") or h.get("host") or "Host sem nome") for h in raw_hosts],
                    "clock": problem.get("clock"),
                }
            outcome = _deliver_problem(config, problem, state, host_snapshots)
            for key in totals:
                if key == "matched_problems":
                    totals[key] += outcome.get("matched", 0)
                else:
                    totals[key] += outcome.get(key, 0)
            if outcome.get("decision"):
                decisions.append(outcome["decision"])
        _save_state(state)

        # Show relevant decisions (most recent first) so it is possible to diagnose
        # why a server-down event did not produce an email without exposing credentials.
        last_decision = decisions[0] if decisions else (
            "Nenhum problema ativo retornado pelo Zabbix." if not problems else
            f"{len(problems)} problema(s) ativo(s), mas nenhum correspondeu às severidades/tipos de host selecionados."
        )
        delivery_errors = []
        if totals["email_failures"]:
            delivery_errors.append(f"Falha em {totals['email_failures']} envio(s) de e-mail")
        if totals["telegram_failures"]:
            delivery_errors.append(f"Falha em {totals['telegram_failures']} envio(s) Telegram")
        if totals["skipped_by_severity"] and totals["matched_problems"] == 0 and totals["skipped_by_host_type"] == 0:
            last_decision = f"{totals['skipped_by_severity']} problema(s) ignorado(s) porque a severidade não está selecionada. " + last_decision
        elif totals["skipped_by_host_type"] and totals["matched_problems"] == 0:
            last_decision = f"{totals['skipped_by_host_type']} problema(s) ignorado(s) pelo filtro de tipo de host. " + last_decision
        error_text = "; ".join(delivery_errors) or ""
        if error_text and totals["email_failures"] + totals["telegram_failures"]:
            details = [d for d in decisions if "falha de entrega" in d.casefold()]
            if details:
                error_text += ": " + details[-1][:200]
        _status_update(
            last_poll=now,
            last_error=error_text,
            active_problems=len(problems),
            last_decision=last_decision,
            last_problem=last_problem_info,
            **totals,
        )
        return {"active_problems": len(problems), "processed": len(problems), **totals, "last_problem": last_problem_info, "last_decision": last_decision, "last_error": error_text}
    except Exception as exc:
        msg = f"Falha ao consultar os problemas do Zabbix: {str(exc)[:250]}"
        _status_update(last_poll=now, last_error=msg, last_decision=msg)
        return {"active_problems": 0, "processed": 0, "matched_problems": 0, "error": msg}


def send_test() -> dict[str, Any]:
    config = _config()
    results: dict[str, Any] = {}
    body = "Teste de notificação do Painel Executivo. Se você recebeu esta mensagem, o canal está configurado corretamente."
    if config.get("email_enabled"):
        recipients = config.get("email_recipients", [])
        if not recipients:
            results["email"] = {"success": False, "message": "Informe ao menos um destinatário de e-mail."}
        else:
            failures = []
            successes = []
            for recipient in recipients:
                try:
                    _send_email(config, recipient, "[Teste] Painel Executivo / Zabbix", body)
                    successes.append(recipient)
                except Exception as exc:
                    failures.append(f"{recipient}: {str(exc)[:180]}")
            results["email"] = {"success": not failures, "message": f"Enviado para {len(successes)} destinatário(s)." if not failures else "; ".join(failures)}
    else:
        results["email"] = {"success": False, "message": "Canal de e-mail desativado."}
    if config.get("telegram_enabled"):
        chat_ids = config.get("telegram_chat_ids", [])
        if not chat_ids:
            results["telegram"] = {"success": False, "message": "Informe ao menos um grupo/chat ID do Telegram."}
        else:
            failures = []
            successes = []
            for chat_id in chat_ids:
                try:
                    _send_telegram(config, chat_id, body)
                    successes.append(chat_id)
                except Exception as exc:
                    failures.append(f"{chat_id}: {str(exc)[:180]}")
            results["telegram"] = {"success": not failures, "message": f"Enviado para {len(successes)} grupo(s)/chat(s)." if not failures else "; ".join(failures)}
    else:
        results["telegram"] = {"success": False, "message": "Canal do Telegram desativado."}
    return results


async def monitor_loop() -> None:
    """Poller de fundo; `requests` roda em thread para não bloquear o event loop do FastAPI."""
    while True:
        config = _config()
        interval = int(config.get("interval_seconds", 60))
        active = bool(config.get("monitor_enabled") and (config.get("email_enabled") or config.get("telegram_enabled")))
        if active:
            try:
                await asyncio.to_thread(poll_once)
            except Exception as exc:  # keep worker alive if an unexpected error escapes
                _status_update(last_error=f"Erro no monitor de alertas: {str(exc)[:200]}")
        await asyncio.sleep(max(15, min(interval, 3600)))
