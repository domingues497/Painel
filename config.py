"""Configuração centralizada do Painel Zabbix.

Os valores podem ser definidos no arquivo .env ou nas variáveis de ambiente do sistema.
Variáveis de ambiente do sistema têm precedência sobre o arquivo .env.
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def _csv(name: str, default: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


# Conexão com a API do Zabbix. URL vazia mantém o modo de demonstração.
ZABBIX_URL = os.getenv("ZABBIX_URL", "").strip()
ZABBIX_TOKEN = os.getenv("ZABBIX_TOKEN", "").strip()
ZABBIX_AUTH_TYPE = os.getenv("ZABBIX_AUTH_TYPE", "token").strip().lower()
ZABBIX_USERNAME = os.getenv("ZABBIX_USERNAME", "").strip()
ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD", "")

# Hosts técnicos dos switches, separados por vírgula.
HOSTS = _csv("SWITCH_HOSTS", "sw-demo-1,sw-demo-2")

# Cache e comportamento da coleta.
CACHE_TTL = int(os.getenv("CACHE_TTL", "15"))
VERIFY_TLS = os.getenv("VERIFY_TLS", "1").strip().lower() not in {"0", "false", "no"}
AVAIL_HOURS = int(os.getenv("AVAIL_HOURS", "24"))
STALE_SECONDS = int(os.getenv("STALE_SECONDS", "900"))

# Grupos do Zabbix que classificam os hosts.
SERVER_GROUPS = _csv("SERVER_GROUPS", "Linux servers,Windows servers,Servidores")
WORKSTATION_GROUPS = _csv("WORKSTATION_GROUPS", "Workstations,Computadores,Desktops")
SWITCH_GROUPS = _csv("SWITCH_GROUPS", "Switches")
WAN_GROUPS = _csv("WAN_GROUPS", "WAN,Links WAN,Operadoras")
NETWORK_GROUPS = _csv(
    "NETWORK_GROUPS",
    "Rede,Network,Roteadores,Routers,Firewalls,Wireless,Energia,MikroTik",
)
# Identifica roteadores por nome técnico/visível quando o host não está em um grupo de rede conhecido.
NETWORK_HOST_PATTERN = os.getenv(
    "NETWORK_HOST_PATTERN",
    r"(mikrotik|routerboard|(?:^|[-_])rb[-_]?\d+)"
)
NETWORK_HOST_RE = re.compile(NETWORK_HOST_PATTERN, re.I)

# Regras para reconhecer interfaces e tags.
PORT_PATTERN = os.getenv(
    "PORT_PATTERN",
    r"^(ether|sfp|qsfp|combo|Gi|Fa|Te|Eth|Port)",
)
WAN_IF_PATTERN = os.getenv("WAN_IF_PATTERN", r"(wan|operadora|isp)")
PORT_RE = re.compile(PORT_PATTERN, re.I)
WAN_IF_RE = re.compile(WAN_IF_PATTERN, re.I)

TAG_UNIT = os.getenv("TAG_UNIT", "unidade").strip().lower()
TAG_CRIT = os.getenv("TAG_CRIT", "criticidade").strip().lower()
CRIT_HIGH = [value.lower() for value in _csv(
    "CRIT_HIGH",
    "alta,alto,crítica,critica,crítico,critico,high,critical",
)]
