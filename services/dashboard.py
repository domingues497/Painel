"""Lógica de negócio e montagem dos dados dos dashboards."""
"""Painel de racks: backend que lê o Zabbix e entrega JSON para a página.

Variáveis de ambiente:
  ZABBIX_URL     ex.: https://zabbix.suaempresa.com/api_jsonrpc.php
                 (vazio = modo demonstração, com dados fictícios)
  ZABBIX_TOKEN   API token de um usuário só de leitura
  SWITCH_HOSTS   nomes técnicos dos hosts no Zabbix, separados por vírgula
  CACHE_TTL      segundos de cache (padrão 15)
  VERIFY_TLS     0 para aceitar certificado autoassinado
  SERVER_GROUPS       grupos de hosts do Zabbix que contam como servidores
  WORKSTATION_GROUPS  grupos de hosts do Zabbix dos computadores de usuários
  AVAIL_HOURS    janela (horas) da disponibilidade (histórico SNMP; ICMP como fallback; padrão 24)
  STALE_SECONDS  acima disso, o host aparece com "dados antigos" (padrão 900)
  SWITCH_GROUPS  grupos de hosts dos switches (padrão "Switches")
  WAN_GROUPS     grupos dos hosts de sonda ICMP, um por operadora (padrão "WAN,Links WAN,Operadoras")
  NETWORK_GROUPS grupos de roteadores, firewalls, APs e nobreaks
  PORT_PATTERN   regex dos nomes de portas físicas dos switches (contagem de portas)
  WAN_IF_PATTERN regex que marca interfaces WAN pelo alias (padrão: wan, operadora ou isp)
  TAG_UNIT / TAG_CRIT  nomes das tags de host para unidade e criticidade (padrão: unidade, criticidade)
  CRIT_HIGH      valores da tag de criticidade tratados como críticos (padrão: alta, crítica, high...)
"""
import random
import re
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from config import (
    AVAIL_HOURS,
    CACHE_TTL,
    CRIT_HIGH,
    HOSTS,
    NETWORK_GROUPS,
    NETWORK_HOST_RE,
    PORT_RE,
    SERVER_GROUPS,
    STALE_SECONDS,
    SWITCH_GROUPS,
    TAG_CRIT,
    TAG_UNIT,
    WAN_GROUPS,
    WAN_IF_RE,
    WORKSTATION_GROUPS,
    VERIFY_TLS,
    ZABBIX_TOKEN,
    ZABBIX_URL,
)

from services.zabbix_client import zbx

# CRS328-24P-4S+RM: 24 portas ether + 4 SFP+
PORTS = [f"ether{i}" for i in range(1, 25)] + [f"sfp-sfpplus{i}" for i in range(1, 5)]

# Nomes dos itens criados pelo template "Network Generic Device by SNMP".
ITEM_RE = re.compile(r"^Interface (.+?)\(.*\): (Operational status|Bits received|Bits sent)$")

_cache = {"t": 0.0, "data": None}


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_zabbix():
    hosts = zbx("host.get", {"output": ["hostid", "host", "name"], "filter": {"host": HOSTS}})
    if not hosts:
        return []
    items = zbx(
        "item.get",
        {
            "output": ["name", "key_", "lastvalue", "hostid"],
            "hostids": [h["hostid"] for h in hosts],
            "search": {"key_": "net.if."},
        },
    )
    by_host = {h["hostid"]: {"host": h["name"], "tech": h["host"], "ports": {}} for h in hosts}
    for it in items:
        m = ITEM_RE.match(it["name"])
        if not m or m.group(1) not in PORTS:
            continue
        port = by_host[it["hostid"]]["ports"].setdefault(
            m.group(1), {"status": None, "in_bps": 0.0, "out_bps": 0.0}
        )
        kind, val = m.group(2), it["lastvalue"]
        if kind == "Operational status":
            port["status"] = int(to_float(val)) if val != "" else None
        elif kind == "Bits received":
            port["in_bps"] = to_float(val)
        else:
            port["out_bps"] = to_float(val)
    result = sorted(by_host.values(), key=lambda s: HOSTS.index(s["tech"]))
    for s in result:
        del s["tech"]
    return result


def mock_data():
    out = []
    for host in HOSTS:
        rnd = random.Random(f"{host}-{int(time.time() // 30)}")
        ports = {}
        for p in PORTS:
            up = rnd.random() < 0.7
            ports[p] = {
                "status": 1 if up else 2,
                "in_bps": rnd.choice([0, 2e3, 4e5, 3e7, 4e8]) if up else 0,
                "out_bps": rnd.choice([0, 2e3, 4e5, 3e7, 4e8]) if up else 0,
            }
        out.append({"host": host, "ports": ports})
    return out


def get_switches():
    now = time.time()
    if _cache["data"] is None or now - _cache["t"] > CACHE_TTL:
        try:
            switches = fetch_zabbix() if ZABBIX_URL else mock_data()
        except Exception as exc:  # o front mantém os últimos dados e mostra o aviso
            raise HTTPException(status_code=502, detail=f"Falha ao consultar o Zabbix: {exc}")
        _cache["data"] = {
            "mock": not ZABBIX_URL,
            "updated": datetime.now(timezone.utc).isoformat(),
            "switches": switches,
        }
        _cache["t"] = now
    return _cache["data"]


# ---------------------------------------------------------------------------
# Hosts: servidores e computadores de usuários
# ---------------------------------------------------------------------------
# Itens dos templates "Linux by Zabbix agent" e "Windows by Zabbix agent".
DISK_RE = re.compile(r"^vfs\.fs\.size\[(.+),(pused|pfree|used|total)\]$")
LOAD_RE = re.compile(r"^system\.cpu\.load\[.*avg1\]$")
ICMP_RE = re.compile(r"^icmpping(\[.*\])?$")
ICMP_LOSS_RE = re.compile(r"^icmppingloss(\[.*\])?$")
ICMP_SEC_RE = re.compile(r"^icmppingsec(\[.*\])?$")
_hosts_cache = {"t": 0.0, "data": None}


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify(groups):
    if any(g in SERVER_GROUPS for g in groups):
        return "server"
    if any(g in WORKSTATION_GROUPS for g in groups):
        return "workstation"
    return "other"


def availability(host, icmp=None):
    """Determina estado: ICMP é prioritário quando existe; agente é fallback."""
    if icmp is not None:
        try:
            return "online" if float(icmp) >= 1 else "offline"
        except (TypeError, ValueError):
            pass
    states = [str(i.get("available")) for i in host.get("interfaces", [])]
    if str(host.get("active_available")) == "1" or "1" in states:
        return "online"
    if str(host.get("active_available")) == "2" or "2" in states:
        return "offline"
    return "unknown"


def fetch_hosts():
    hosts = zbx(
        "host.get",
        {
            "output": ["hostid", "host", "name", "active_available", "snmp_available", "snmp_error"],
            "monitored_hosts": True,
            "selectHostGroups": ["name"],
            "selectInterfaces": ["type", "available"],
            "selectTags": ["tag", "value"],
        },
    )
    hosts = [h for h in hosts if h["host"] not in HOSTS]  # os switches têm painel próprio
    if not hosts:
        return []
    ids = [h["hostid"] for h in hosts]

    # Consultar todos os itens habilitados uma única vez. Não limitar por uma lista
    # de keys fixa: templates Windows/Linux podem publicar as mesmas métricas com
    # keys diferentes (por exemplo vm.memory.size[pavailable] em vez de
    # vm.memory.utilization, ou FS com pfree/used/total em vez de pused).
    # Essa mesma resposta também abastece os filtros de tags dos TOPs.
    item_tag_rows = zbx(
        "item.get",
        {
            "output": ["itemid", "name", "key_", "hostid", "lastvalue", "lastclock", "units", "value_type"],
            "hostids": ids,
            "monitored": True,
            "selectTags": "extend",
            "filter": {"status": 0},
        },
    )
    item_tags_by_host = {hid: [] for hid in ids}
    for item in item_tag_rows:
        item_tags_by_host.setdefault(item["hostid"], []).append({
            "itemid": item.get("itemid"),
            "name": item.get("name") or item.get("key_", ""),
            "key": item.get("key_", ""),
            "lastvalue": item.get("lastvalue"),
            "units": item.get("units") or "",
            "value_type": item.get("value_type"),
            "tags": [
                {"tag": str(tag.get("tag", "")).strip(), "value": str(tag.get("value", "")).strip()}
                for tag in item.get("tags", []) if str(tag.get("tag", "")).strip()
            ],
        })
    metrics = {
        hid: {
            "cpu": None, "mem": None, "mem_pused": None, "mem_pavailable": None,
            "mem_used_bytes": None, "mem_total_bytes": None, "load": None,
            "uptime": None, "mounts": [], "fs_values": {}, "last": 0,
            "icmp": None, "icmp_loss": None, "icmp_sec": None,
            "icmp_lastclock": 0, "icmp_itemid": None,
        }
        for hid in ids
    }
    for it in item_tag_rows:
        m, key, val = metrics.get(it["hostid"]), it.get("key_", ""), num(it.get("lastvalue"))
        if m is None:
            continue
        clock = int(it.get("lastclock") or 0)
        m["last"] = max(m["last"], clock)
        if ICMP_RE.match(key):
            m["icmp"] = val
            m["icmp_lastclock"] = max(m["icmp_lastclock"], clock)
            m["icmp_itemid"] = it["itemid"]
            continue
        if ICMP_LOSS_RE.match(key):
            m["icmp_loss"] = val
            m["icmp_lastclock"] = max(m["icmp_lastclock"], clock)
            continue
        if ICMP_SEC_RE.match(key):
            m["icmp_sec"] = val
            m["icmp_lastclock"] = max(m["icmp_lastclock"], clock)
            continue
        if val is None:
            continue
        if key == "system.cpu.util" or key.startswith("system.cpu.util["):
            # Preferir a key agregada quando disponível; não substituir por
            # user/system individual se já foi encontrada.
            if m["cpu"] is None or key == "system.cpu.util":
                m["cpu"] = val
        elif key == "vm.memory.utilization":
            m["mem"] = val
        elif key.startswith("vm.memory.size[") and key.endswith("]"):
            mode = key[len("vm.memory.size["):-1].split(",")[-1].strip().lower()
            if mode == "pused":
                m["mem_pused"] = val
            elif mode == "pavailable":
                m["mem_pavailable"] = val
            elif mode == "used":
                m["mem_used_bytes"] = val
            elif mode == "total":
                m["mem_total_bytes"] = val
        elif key == "system.uptime":
            m["uptime"] = val
        elif LOAD_RE.match(key):
            m["load"] = val
        else:
            d = DISK_RE.match(key)
            if d:
                mount, mode = d.group(1), d.group(2).lower()
                m["fs_values"].setdefault(mount, {})[mode] = val

    # Normalizar memória e discos para percentual de uso. Preferir os itens
    # percentuais; se o template só fornece bytes, calcular used/total.
    for m in metrics.values():
        if m["mem"] is None:
            if m["mem_pused"] is not None:
                m["mem"] = m["mem_pused"]
            elif m["mem_pavailable"] is not None:
                m["mem"] = 100.0 - m["mem_pavailable"]
            elif m["mem_used_bytes"] is not None and m["mem_total_bytes"]:
                m["mem"] = m["mem_used_bytes"] / m["mem_total_bytes"] * 100.0
        for mount, values in m["fs_values"].items():
            pused = values.get("pused")
            if pused is None and values.get("pfree") is not None:
                pused = 100.0 - values["pfree"]
            if pused is None and values.get("used") is not None and values.get("total"):
                pused = values["used"] / values["total"] * 100.0
            if pused is not None:
                m["mounts"].append({"name": mount, "pused": max(0.0, min(100.0, pused))})

    # Itens não suportados por host (o painel precisa deixar isso visível).
    unsupported = {i: 0 for i in ids}
    for it in zbx("item.get", {"output": ["hostid"], "hostids": ids, "monitored": True, "filter": {"state": 1}}):
        unsupported[it["hostid"]] += 1

    # Disponibilidade na janela AVAIL_HOURS, pela média ponderada das tendências do icmpping.
    availability_pct = {}
    icmp_ids = {m["icmp_itemid"]: hid for hid, m in metrics.items() if m["icmp_itemid"]}
    if icmp_ids:
        acc = {}
        rows = zbx(
            "trend.get",
            {
                "output": ["itemid", "num", "value_avg"],
                "itemids": list(icmp_ids),
                "time_from": int(time.time()) - AVAIL_HOURS * 3600,
            },
        )
        for row in rows:
            tot, cnt = acc.get(row["itemid"], (0.0, 0))
            acc[row["itemid"]] = (tot + float(row["value_avg"]) * int(row["num"]), cnt + int(row["num"]))
        for itemid, (tot, cnt) in acc.items():
            if cnt:
                availability_pct[icmp_ids[itemid]] = tot / cnt * 100

    triggers = zbx(
        "trigger.get",
        {
            "output": ["description", "priority"],
            "hostids": ids,
            "monitored": True,
            "only_true": True,
            "skipDependent": True,
            "min_severity": 2,
            "expandDescription": True,
            "selectHosts": ["hostid"],
        },
    )
    problems = {i: [] for i in ids}
    for t in triggers:
        for th in t.get("hosts", []):
            if th["hostid"] in problems:
                problems[th["hostid"]].append({"name": t["description"], "severity": int(t["priority"])})

    result = []
    for h in hosts:
        m, pr = metrics[h["hostid"]], sorted(problems[h["hostid"]], key=lambda p: -p["severity"])
        mounts = sorted(m["mounts"], key=lambda x: -x["pused"])
        result.append(
            {
                "id": h["hostid"],
                "name": h["name"],
                "kind": classify([g["name"] for g in h.get("hostgroups", [])]),
                "groups": [g["name"] for g in h.get("hostgroups", [])],
                "tags": tags_of(h),
                "item_tags": item_tags_by_host.get(h["hostid"], []),
                "status": availability({**h, "interfaces": h.get("interfaces", [])}, m["icmp"]),
                "cpu": m["cpu"],
                "mem": m["mem"],
                "load": m["load"],
                "uptime": m["uptime"],
                "icmp_ping": m["icmp"],
                "icmp_loss": m["icmp_loss"],
                "icmp_response_ms": (m["icmp_sec"] * 1000 if m["icmp_sec"] is not None else None),
                "icmp_age": (int(time.time()) - m["icmp_lastclock"] if m["icmp_lastclock"] else None),
                "disk": {"worst": mounts[0]["pused"] if mounts else None, "mounts": mounts},
                "availability": availability_pct.get(h["hostid"]),
                "unsupported": unsupported[h["hostid"]],
                "age": int(time.time()) - m["last"] if m["last"] else None,
                "problems": {"count": len(pr), "max": pr[0]["severity"] if pr else 0, "top": pr[:3]},
            }
        )
    return sorted(result, key=lambda x: x["name"].lower())


def mock_hosts():
    t = int(time.time() // 30)
    servers = ["srv-ad01", "srv-arquivos01", "srv-bd01", "srv-web01", "srv-backup01", "srv-zabbix"]
    names = [(n, "server") for n in servers]
    names += [(f"pc-{s}-{n:02d}", "workstation") for s in ("fin", "rh", "ti", "com") for n in range(1, 11)]
    names += [("nobreak-ti", "other"), ("ap-recepcao", "other")]
    issues = [("Uso de disco acima de 90% em /", 3), ("CPU em uso alto há 5 minutos", 2), ("Serviço indisponível", 4)]
    out = []
    for name, kind in names:
        r, fixed = random.Random(f"{name}-{t}"), random.Random(name)
        online = fixed.random() < (0.8 if kind == "workstation" else 0.97)
        host = {
            "id": name, "name": name, "kind": kind, "groups": (["Servidores Windows"] if kind == "server" else ["Usuários Windows"] if kind == "workstation" else ["Rede"]), "status": "online" if online else "offline",
            "cpu": None, "mem": None, "load": None, "uptime": None,
            "icmp_ping": 1 if online else 0, "icmp_loss": 0.0 if online else 100.0,
            "icmp_response_ms": fixed.uniform(0.2, 8.0) if online else None, "icmp_age": 5,
            "disk": {"worst": None, "mounts": []}, "problems": {"count": 0, "max": 0, "top": []},
            "availability": None, "unsupported": 0, "age": None,
            "tags": {
                "unit": fixed.choice(["Matriz", "Filial 1", "Filial 2"]),
                "criticality": {"srv-ad01": "alta", "srv-bd01": "alta", "srv-arquivos01": "alta",
                                "srv-web01": "média", "srv-backup01": "média"}.get(name, "baixa"),
                "all": [],
            },
        }
        host["tags"]["all"] = [
            {"tag": "Unidade", "value": host["tags"]["unit"]},
            {"tag": "Criticidade", "value": host["tags"]["criticality"]},
        ]
        if online:
            busy = fixed.random() < 0.2
            host["cpu"] = r.uniform(70, 98) if busy else r.uniform(2, 60)
            host["mem"] = r.uniform(30, 92)
            host["load"] = host["cpu"] / 25 if kind == "server" else None
            host["uptime"] = fixed.randint(1, 200) * 86400 + (t % 1000) * 30
            host["availability"] = fixed.uniform(97, 100) if kind == "server" else fixed.uniform(80, 100)
            host["unsupported"] = fixed.choice([0, 0, 0, 0, 2, 5])
            host["age"] = fixed.choice([30] * 8 + [4000])  # 4000 s = dados antigos
            base = fixed.uniform(25, 93)
            names_fs = ["/", "/var", "/data"] if kind == "server" else ["C:"]
            mounts = [{"name": fs, "pused": min(99, base + fixed.uniform(-15, 5) + r.uniform(0, 1))} for fs in names_fs]
            mounts.sort(key=lambda x: -x["pused"])
            host["disk"] = {"worst": mounts[0]["pused"], "mounts": mounts}
            if fixed.random() < 0.15:
                pr = [{"name": issues[i][0], "severity": issues[i][1]} for i in fixed.sample(range(3), fixed.randint(1, 2))]
                pr.sort(key=lambda p: -p["severity"])
                host["problems"] = {"count": len(pr), "max": pr[0]["severity"], "top": pr}
        elif kind == "server":
            host["problems"] = {"count": 1, "max": 3, "top": [{"name": "Agente do Zabbix indisponível", "severity": 3}]}
        if not online:
            host["icmp_ping"] = 0
            host["icmp_loss"] = 100.0
            host["icmp_response_ms"] = None
            host["availability"] = fixed.uniform(40, 90)
            host["age"] = 5 * 3600
        out.append(host)
    return out


def get_hosts(kind: str = "all"):
    now = time.time()
    if _hosts_cache["data"] is None or now - _hosts_cache["t"] > CACHE_TTL:
        try:
            hosts = fetch_hosts() if ZABBIX_URL else mock_hosts()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao consultar o Zabbix: {exc}")
        _hosts_cache["data"] = {
            "mock": not ZABBIX_URL,
            "updated": datetime.now(timezone.utc).isoformat(),
            "hosts": hosts,
            "avail_hours": AVAIL_HOURS,
            "stale_seconds": STALE_SECONDS,
        }
        _hosts_cache["t"] = now
    data = _hosts_cache["data"]
    if kind in ("server", "workstation", "other"):
        return {**data, "hosts": [h for h in data["hosts"] if h["kind"] == kind]}
    return data


# ---------------------------------------------------------------------------
# Rede: switches, roteadores e links WAN
# ---------------------------------------------------------------------------
UTIL_WARN = 80  # % de uso do link a partir do qual a interface conta como saturada

# Itens das interfaces do template "Network Generic Device by SNMP":
#   Interface ether1(alias): Operational status | Bits received | Bits sent | Speed | ...
IF_RE = re.compile(r"^Interface\s+(.+?)\((.*?)\):\s*(.+)$")
IF_RE_NO_ALIAS = re.compile(r"^Interface\s+(.+?):\s*(.+)$")
IF_METRICS = {
    "Operational status": "status",
    "Bits received": "in_bps",
    "Bits sent": "out_bps",
    "Inbound packets with errors": "in_err",
    "Outbound packets with errors": "out_err",
    "Inbound packets discarded": "in_dis",
    "Outbound packets discarded": "out_dis",
    "Speed": "speed",
}
NET_KEYS = ["icmpping", "net.if.", "system.cpu.util", "vm.memory.util", "sensor.temp.value"]
ICMP_LOSS_RE = re.compile(r"^icmppingloss(\[.*\])?$")
ICMP_SEC_RE = re.compile(r"^icmppingsec(\[.*\])?$")
PENDING = [
    "Rota ativa e estado do link secundário (failover WAN): exige script, API ou SNMP específico do MikroTik",
    "PoE: consumo e orçamento por porta",
    "Wi-Fi: clientes, sinal e uso de rádio",
    "Estado dos túneis VPN",
    "Nobreak: bateria, carga e autonomia",
    "Fontes e ventiladores",
]
_net_cache = {"t": 0.0, "data": None}


def _problems_by_host(ids):
    triggers = zbx(
        "trigger.get",
        {
            "output": ["description", "priority"],
            "hostids": ids,
            "monitored": True,
            "only_true": True,
            "skipDependent": True,
            "min_severity": 2,
            "expandDescription": True,
            "selectHosts": ["hostid"],
        },
    )
    out = {i: [] for i in ids}
    for t in triggers:
        for th in t.get("hosts", []):
            if th["hostid"] in out:
                out[th["hostid"]].append({"name": t["description"], "severity": int(t["priority"])})
    return out


def _unsupported_by_host(ids):
    out = {i: 0 for i in ids}
    for it in zbx("item.get", {"output": ["hostid"], "hostids": ids, "monitored": True, "filter": {"state": 1}}):
        out[it["hostid"]] += 1
    return out


def _icmp_availability(icmp_items):
    """icmp_items: {itemid: hostid}. Devolve {hostid: % de disponibilidade na janela AVAIL_HOURS}."""
    if not icmp_items:
        return {}
    rows = zbx(
        "trend.get",
        {
            "output": ["itemid", "num", "value_avg"],
            "itemids": list(icmp_items),
            "time_from": int(time.time()) - AVAIL_HOURS * 3600,
        },
    )
    acc = {}
    for row in rows:
        tot, cnt = acc.get(row["itemid"], (0.0, 0))
        acc[row["itemid"]] = (tot + float(row["value_avg"]) * int(row["num"]), cnt + int(row["num"]))
    return {icmp_items[i]: tot / cnt * 100 for i, (tot, cnt) in acc.items() if cnt}


def _snmp_history_availability(status_items, window_hours=24):
    """Calcula % de disponibilidade SNMP a partir do histórico do item interno.

    status_items: {hostid: {itemid, value_type, lastvalue, lastclock}}.
    No item interno zabbix[host,snmp,available], 0=indisponível,
    1=disponível e 2=desconhecido. Os valores desconhecidos ficam fora do
    denominador. Os valores são considerados válidos até a próxima
    amostra, pois itens internos podem publicar apenas mudanças/heartbeat.
    """
    if not status_items:
        return {}
    now = int(time.time())
    window = max(1, int(window_hours)) * 3600
    start = now - window
    # Busca mais uma janela anterior para encontrar a condição que já valia
    # no início das últimas 24h (ex.: itens configurados com heartbeat de 12h).
    time_from = start - window
    by_item = {}
    item_to_host = {}
    by_type = {}
    for hostid, info in status_items.items():
        itemid = str(info.get("itemid") or "")
        if not itemid:
            continue
        item_to_host[itemid] = hostid
        value_type_raw = info.get("value_type")
        value_type = int(value_type_raw if value_type_raw not in (None, "") else 3)
        by_type.setdefault(value_type, []).append(itemid)
        by_item[itemid] = []
    for value_type, itemids in by_type.items():
        try:
            samples = zbx(
                "history.get",
                {
                    "output": ["itemid", "clock", "value"],
                    "history": value_type,
                    "itemids": itemids,
                    "time_from": time_from,
                    "time_till": now,
                    "sortfield": "clock",
                    "sortorder": "ASC",
                },
            ) or []
        except Exception:
            # Uma falha na leitura do histórico não deve derrubar a página de Rede.
            continue
        for sample in samples:
            itemid = str(sample.get("itemid", ""))
            if itemid in by_item:
                try:
                    by_item[itemid].append((int(sample["clock"]), int(float(sample["value"]))))
                except (TypeError, ValueError, KeyError):
                    pass
    result = {}
    for hostid, info in status_items.items():
        itemid = str(info.get("itemid") or "")
        if not itemid:
            continue
        points = by_item.get(itemid, [])
        # Inclui o último valor retornado por item.get caso history.get não o
        # tenha retornado ainda (ou a retenção do histórico tenha sido alterada).
        last_clock = int(info.get("lastclock") or 0)
        try:
            last_value = int(float(info.get("lastvalue")))
        except (TypeError, ValueError):
            last_value = None
        if last_clock and last_value is not None and not any(c == last_clock for c, _ in points):
            points.append((last_clock, last_value))
        # Ordena as amostras que caem na janela de cálculo ou antes dela.
        # Não exigimos obrigatoriamente uma amostra anterior exata ao início:
        # a regra de cobertura mínima de 80% abaixo decide se o período observado
        # é suficiente para apresentar um percentual.
        points = sorted({clock: value for clock, value in points if clock <= now}.items())
        if not points:
            continue
        up_seconds = known_seconds = 0
        for idx, (clock, value) in enumerate(points):
            next_clock = points[idx + 1][0] if idx + 1 < len(points) else now
            left, right = max(clock, start), min(next_clock, now)
            if right <= left:
                continue
            seconds = right - left
            # Zabbix internal item zabbix[host,snmp,available]:
            # 0=unavailable, 1=available, 2=unknown. Unknown intervals are
            # excluded from the denominator rather than counted as downtime.
            if value in (0, 1):
                known_seconds += seconds
                if value == 1:
                    up_seconds += seconds
        # A history com cobertura muito pequena não deve produzir uma percentagem
        # enganosa. Exige-se pelo menos 80% da janela conhecida.
        if known_seconds >= window * 0.80:
            result[hostid] = up_seconds / known_seconds * 100.0

    # Fallback para itens com histórico curto/compactado, mas que tenham Trends
    # habilitados. Trends é uma aproximação por amostras; só usamos quando houver
    # pelo menos 80% das horas da janela representadas.
    missing = {hid: str(info.get("itemid") or "") for hid, info in status_items.items()
               if hid not in result and info.get("itemid")}
    if missing:
        try:
            trends = zbx(
                "trend.get",
                {
                    "output": ["itemid", "clock", "num", "value_avg"],
                    "itemids": list(missing.values()),
                    "time_from": start,
                },
            ) or []
        except Exception:
            trends = []
        by_trend = {}
        for row in trends:
            iid = str(row.get("itemid", ""))
            try:
                avg_value = float(row.get("value_avg"))
                n = int(row.get("num") or 0)
                clock = int(row.get("clock") or 0)
            except (TypeError, ValueError):
                continue
            # Valores do item interno: 0=indisponível, 1=disponível, 2=desconhecido.
            # Médias entre 0 e 1 permitem estimar a fração disponível. Uma média
            # acima de 1 pode incluir o estado desconhecido e é ignorada.
            if n <= 0 or not 0 <= avg_value <= 1:
                continue
            rec = by_trend.setdefault(iid, {"hours": set(), "available": 0.0, "samples": 0})
            rec["hours"].add(clock // 3600)
            rec["available"] += avg_value * n
            rec["samples"] += n
        item_to_host = {itemid: hid for hid, itemid in missing.items()}
        for itemid, stats in by_trend.items():
            if len(stats["hours"]) >= window_hours * 0.80 and stats["samples"]:
                hostid = item_to_host.get(itemid)
                if hostid:
                    result[hostid] = stats["available"] / stats["samples"] * 100.0
    return result


def _uptime_availability(uptime, sample_clock, now=None, window_hours=None):
    """Estima disponibilidade pela fração da janela transcorrida desde o boot.

    Retorna None se o uptime não for numérico ou o valor do item estiver antigo.
    Esta é uma estimativa operacional; ela não detecta falhas de rede/SNMP sem reboot.
    """
    try:
        uptime_value = float(uptime)
        clock = int(sample_clock or 0)
    except (TypeError, ValueError):
        return None
    current_time = int(time.time()) if now is None else int(now)
    # Uptime costuma ter intervalo de coleta maior que o limite de dados antigos
    # do painel. Aceitamos até 24h de idade para esse item; valores de uptime
    # iguais/superiores à janela indicam 100% da janela desde o último boot.
    if clock <= 0 or clock > current_time or current_time - clock > 24 * 3600:
        return None
    hours = AVAIL_HOURS if window_hours is None else window_hours
    window_seconds = max(1, int(hours)) * 3600
    if uptime_value >= window_seconds:
        return 100.0
    return min(100.0, max(0.0, uptime_value) / window_seconds * 100.0)


def _network_snmp_status(host, item_value=None):
    """Estado atual SNMP. Retorna None se o host não tiver interface SNMP."""
    if item_value is not None:
        try:
            val = int(float(item_value))
        except (TypeError, ValueError):
            val = 2
        # Zabbix internal item: 0=unavailable, 1=available, 2=unknown.
        return {1: "online", 0: "offline", 2: "unknown"}.get(val, "unknown")
    snmp_interfaces = [
        i for i in (host.get("interfaces") or [])
        if str(i.get("type")) == "2"
    ]
    if not snmp_interfaces:
        return None
    # Campo host.snmp_available: 1=available, 2=unavailable, 0=unknown.
    try:
        val = int(host.get("snmp_available") or 0)
    except (TypeError, ValueError):
        val = 0
    return {1: "online", 2: "offline", 0: "unknown"}.get(val, "unknown")


def role_of(host, groups):
    # Os nomes de grupo podem variar entre instalações; normalize antes de comparar.
    normalized_groups = {str(g).strip().casefold() for g in groups}
    switch_groups = {str(g).strip().casefold() for g in SWITCH_GROUPS}
    wan_groups = {str(g).strip().casefold() for g in WAN_GROUPS}
    network_groups = {str(g).strip().casefold() for g in NETWORK_GROUPS}
    if host.get("host") in HOSTS or normalized_groups & switch_groups:
        return "switch"
    if normalized_groups & wan_groups:
        return "wan"

    # Alguns ambientes não colocam MikroTik em um grupo chamado Rede/Router.
    # Reconhecemos então o fabricante/modelo pelo nome e também a tag de host
    # component=network, sem depender apenas do nome do grupo.
    host_names = f"{host.get('host', '')} {host.get('name', '')}"
    if NETWORK_HOST_RE.search(host_names) or any("mikrotik" in g for g in normalized_groups):
        return "device"
    host_tags = host.get("tags", []) or []
    normalized_tags = {
        str(t.get("tag", "")).strip().casefold(): str(t.get("value", "")).strip().casefold()
        for t in host_tags if t.get("tag")
    }
    if normalized_tags.get("component") in {"network", "router", "network device", "roteador"}:
        return "device"
    if normalized_groups & network_groups:
        return "device"
    return None


def assemble(raws):
    """Transforma os dados brutos por host (reais ou de demonstração) na resposta da API."""
    devices, ifaces = [], []
    for r in raws:
        up = down = 0
        worst = err_total = None
        for name, f in r["ifs"].items():
            speed, in_bps, out_bps, status = f.get("speed"), f.get("in_bps"), f.get("out_bps"), f.get("status")
            util = None
            if speed and speed > 0 and (in_bps is not None or out_bps is not None):
                util = max(in_bps or 0.0, out_bps or 0.0) / speed * 100
            errs = [f[k] for k in ("in_err", "out_err", "in_dis", "out_dis") if f.get(k) is not None]
            err = sum(errs) if errs else None
            alias = f.get("alias", "")
            tag_text = f.get("tag_text", "")
            # O PPPoE BRASILNET é a conexão da filial Quero Quero. Em alguns
            # templates do Zabbix, a interface lógica chega sem alias e não
            # contém a palavra WAN; reconhecemos o nome técnico explicitamente.
            pppoe_brasilnet = bool(
                re.search(r"pppoe[-_\s]*brasilnet", f"{name} {alias} {tag_text}", re.I)
            )
            if pppoe_brasilnet:
                alias = "Filial Quero Quero — BRASILNET"
            ifaces.append(
                {
                    "host": r["name"], "name": name, "alias": alias, "status": status,
                    "in_bps": in_bps, "out_bps": out_bps, "speed": speed, "util": util, "err": err,
                    "wan": bool(
                        pppoe_brasilnet
                        or WAN_IF_RE.search(name)
                        or WAN_IF_RE.search(alias)
                        or WAN_IF_RE.search(tag_text)
                        or re.search(r"\blink\s*(?:[-_:]?\s*)?(?:[A-Z0-9]+)", f"{alias} {tag_text}", re.I)
                    ),
                }
            )
            if r["role"] == "switch" and PORT_RE.match(name) and status is not None:
                if status == 1:
                    up += 1
                else:
                    down += 1
            if status == 1 and util is not None:
                worst = util if worst is None else max(worst, util)
            if err is not None:
                err_total = (err_total or 0.0) + err
        pr = sorted(r["problems"], key=lambda p: -p["severity"])
        devices.append(
            {
                "id": r["id"], "name": r["name"], "role": r["role"], "status": r["status"],
                "tags": r.get("tags") or {"unit": None, "criticality": None},
                "latency_ms": r["sec"] * 1000 if r["sec"] is not None else None,
                "loss_pct": r["loss"],
                "availability": r["availability"],
                "cpu": max(r["cpu"]) if r["cpu"] else None,
                "mem": max(r["mem"]) if r["mem"] else None,
                "temp": max(r["temp"]) if r["temp"] else None,
                "ports": {"up": up, "down": down} if r["role"] == "switch" else None,
                "worst_util": worst,
                "errors": err_total,
                "unsupported": r["unsupported"],
                "age": r["age"],
                "problems": {"count": len(pr), "max": pr[0]["severity"] if pr else 0, "top": pr[:3]},
            }
        )
    active = [i for i in ifaces if i["status"] == 1]
    interfaces = {
        "top_util": sorted([i for i in active if i["util"] is not None], key=lambda i: -i["util"])[:10],
        "top_errors": sorted([i for i in ifaces if i["err"]], key=lambda i: -i["err"])[:10],
        "wan": sorted([i for i in ifaces if i["wan"]], key=lambda i: (i["host"], i["name"])),
        "counts": {
            "saturated": sum(1 for i in active if i["util"] is not None and i["util"] >= UTIL_WARN),
            "errors": sum(1 for i in ifaces if i["err"]),
            "util_warn": UTIL_WARN,
        },
    }
    return {
        "devices": sorted(devices, key=lambda d: d["name"].lower()),
        "interfaces": interfaces,
        "pending": PENDING,
    }


def fetch_network():
    hosts = zbx(
        "host.get",
        {
            "output": ["hostid", "host", "name", "active_available", "snmp_available", "snmp_error"],
            "monitored_hosts": True,
            "selectHostGroups": ["name"],
            "selectInterfaces": ["type", "available"],
            "selectTags": ["tag", "value"],
        },
    )
    nets = []
    for h in hosts:
        role = role_of(h, [g["name"] for g in h.get("hostgroups", [])])
        if role:
            nets.append((h, role))
    if not nets:
        return assemble([])
    ids = [h["hostid"] for h, _ in nets]

    items = zbx(
        "item.get",
        {
            "output": ["itemid", "key_", "name", "lastvalue", "lastclock", "hostid", "value_type"],
            "hostids": ids,
            # API item.get search aceita uma lista de strings em searchByAny,
            # porém alguns ambientes/templates não indexam todas as variantes.
            # Buscamos itens habilitados dos hosts de rede e filtramos localmente.
            "filter": {"status": 0},
            "selectTags": ["tag", "value"],
        },
    )
    data = {i: {"cpu": [], "mem": [], "temp": [], "ping": None, "loss": None, "sec": None,
                "icmp": None, "last": 0, "ifs": {}, "snmp_available": None,
                "snmp_itemid": None, "snmp_value_type": 3, "snmp_clock": 0,
                "uptime": None, "uptime_itemid": None, "uptime_clock": 0} for i in ids}
    for it in items:
        d, key, val = data.get(it["hostid"]), it["key_"], num(it["lastvalue"])
        if d is None:
            continue
        # Disponibilidade do agente SNMP fornecida pelo item interno do Zabbix:
        # 0=indisponível, 1=disponível, 2=desconhecido.
        if key.strip().casefold() == "zabbix[host,snmp,available]":
            d["snmp_available"] = val
            d["snmp_itemid"] = it.get("itemid")
            value_type_raw = it.get("value_type")
            d["snmp_value_type"] = int(value_type_raw if value_type_raw not in (None, "") else 3)
            d["snmp_clock"] = int(it.get("lastclock") or 0)
            d["last"] = max(d["last"], d["snmp_clock"])
            continue
        # Uptime é guardado para diagnóstico/fallback, mas não é usado sozinho
        # como percentagem de disponibilidade: não mede a duração de quedas.
        if key.strip().casefold() in {"system.uptime", "system.hw.uptime", "system.net.uptime"}:
            d["uptime"] = val
            d["uptime_itemid"] = it.get("itemid")
            d["uptime_clock"] = int(it.get("lastclock") or 0)
            d["last"] = max(d["last"], d["uptime_clock"])
            continue
        # Sondas ICMP rodam no servidor; não entram no cálculo de "dados antigos".
        if ICMP_RE.match(key):
            d["icmp"], d["ping"] = it["itemid"], val
            continue
        if ICMP_LOSS_RE.match(key):
            d["loss"] = val
            continue
        if ICMP_SEC_RE.match(key):
            d["sec"] = val
            continue
        # Ignora itens não usados nesta visão antes de calcular idade dos dados.
        relevant = (
            key.startswith("system.cpu.util")
            or key.startswith(("vm.memory.util", "sensor.temp.value", "net.if."))
        )
        if val is None or not relevant:
            continue
        d["last"] = max(d["last"], int(it["lastclock"] or 0))
        if key.startswith("system.cpu.util"):
            d["cpu"].append(val)
        elif key.startswith("vm.memory.util"):
            d["mem"].append(val)
        elif key.startswith("sensor.temp.value"):
            d["temp"].append(val)
        elif key.startswith("net.if."):
            item_name = str(it.get("name", ""))
            m = IF_RE.match(item_name)
            if m:
                iface_name, alias, metric_name = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            else:
                fallback = IF_RE_NO_ALIAS.match(item_name)
                if not fallback:
                    continue
                iface_name, metric_name = fallback.group(1).strip(), fallback.group(2).strip()
                alias = ""
            metric = IF_METRICS.get(metric_name)
            if metric:
                item_tags = it.get("tags", []) or []
                tag_text = " ".join(
                    f"{str(t.get('tag', '')).strip()} {str(t.get('value', '')).strip()}"
                    for t in item_tags
                )
                # O template pode deixar o alias vazio, mas carregar a operadora
                # nas tags de item (ex.: description=Link LIGGA/Link BRASILNET).
                if not alias:
                    for t in item_tags:
                        tag_name = str(t.get("tag", "")).strip().casefold()
                        tag_value = str(t.get("value", "")).strip()
                        if tag_value and tag_name in {"description", "alias", "interface", "name"}:
                            alias = tag_value
                            if WAN_IF_RE.search(tag_value):
                                break
                iface = d["ifs"].setdefault(iface_name, {"alias": alias, "tag_text": tag_text})
                if alias and not iface.get("alias"):
                    iface["alias"] = alias
                if tag_text and not iface.get("tag_text"):
                    iface["tag_text"] = tag_text
                iface[metric] = val

    # Disponibilidade 24h preferencialmente via histórico do estado SNMP do
    # dispositivo; ICMP é fallback somente quando não existe item de estado SNMP.
    snmp_status_items = {
        hid: {
            "itemid": d["snmp_itemid"],
            "value_type": d["snmp_value_type"],
            "lastvalue": d["snmp_available"],
            "lastclock": d["snmp_clock"],
        }
        for hid, d in data.items() if d.get("snmp_itemid")
    }
    avail_snmp = _snmp_history_availability(snmp_status_items, AVAIL_HOURS)
    icmp_avail = _icmp_availability({d["icmp"]: hid for hid, d in data.items() if d["icmp"]})
    avail = {}
    now_for_availability = int(time.time())
    for h, _role in nets:
        hid = h["hostid"]
        d = data[hid]
        uptime_estimate = _uptime_availability(
            d.get("uptime"), d.get("uptime_clock"), now=now_for_availability, window_hours=AVAIL_HOURS
        )
        if uptime_estimate is not None:
            # Estimativa solicitada: uptime atual / janela, limitado a 100%.
            # Não detecta falhas de rede/SNMP sem reinicialização do equipamento.
            avail[hid] = uptime_estimate
        elif hid in avail_snmp:
            avail[hid] = avail_snmp[hid]
        elif hid in icmp_avail:
            avail[hid] = icmp_avail[hid]
    unsupported = _unsupported_by_host(ids)
    problems = _problems_by_host(ids)
    now = int(time.time())
    raws = []
    for h, role in nets:
        d = data[h["hostid"]]
        # Para equipamento SNMP, o estado do agente é a fonte prioritária
        # (1=online, 0=indisponível, 2=desconhecido). ICMP só entra como fallback
        # se não houver estado SNMP disponível/configurado.
        status = _network_snmp_status(h, d.get("snmp_available"))
        if status is None:
            status = "online" if d["ping"] == 1 else "offline" if d["ping"] is not None else availability(h)
        raws.append(
            {
                "id": h["hostid"], "name": h["name"], "role": role, "status": status, "tags": tags_of(h),
                "sec": d["sec"], "loss": d["loss"], "cpu": d["cpu"], "mem": d["mem"], "temp": d["temp"],
                "ifs": d["ifs"], "availability": avail.get(h["hostid"]), "uptime": d.get("uptime"),
                "snmp_available": d.get("snmp_available"),
                "unsupported": unsupported[h["hostid"]], "problems": problems[h["hostid"]],
                "age": now - d["last"] if d["last"] else None,
            }
        )
    return assemble(raws)


def mock_network():
    t = int(time.time() // 30)
    sw_spec = [(f"ether{i}", "", 1e9) for i in range(1, 25)] + [
        (f"sfp-sfpplus{i}", "Uplink core" if i == 1 else "", 1e10) for i in range(1, 5)
    ]
    rt_spec = [("ether1", "WAN-Operadora-A", 1e9), ("ether2", "WAN-Operadora-B", 1e9), ("ether3", "LAN-Core", 1e9)]

    def make_ifs(fixed, r, spec):
        ifs = {}
        for name, alias, speed in spec:
            up = fixed.random() < 0.7 or bool(alias)
            f = {"alias": alias, "status": 1 if up else 2, "speed": speed}
            if up:
                level = fixed.choice([0.88, 0.7, 0.4, 0.1]) if alias else fixed.choice(
                    [0.0001, 0.005, 0.02, 0.1, 0.3, 0.55, 0.85, 0.93])
                f["in_bps"] = speed * level * r.uniform(0.8, 1.0)
                f["out_bps"] = speed * level * r.uniform(0.3, 0.9)
                bad = fixed.random() < 0.08
                for k in ("in_err", "out_err", "in_dis", "out_dis"):
                    f[k] = r.uniform(0.2, 12) if bad and k in ("in_err", "in_dis") else 0.0
            ifs[name] = f
        return ifs

    raws = []
    for name in ["sw-core-01", "sw-rack-02", "sw-andar1", "sw-andar2"]:
        r, fixed = random.Random(f"{name}-{t}"), random.Random(name)
        online = fixed.random() < 0.9
        problems = []
        if not online:
            problems.append({"name": "Switch sem resposta ao ping", "severity": 4})
        elif fixed.random() < 0.25:
            problems.append({"name": "Utilização do link acima de 90%", "severity": 3})
        raws.append(
            {
                "id": name, "name": name, "role": "switch", "status": "online" if online else "offline",
                "sec": r.uniform(0.0005, 0.003) if online else None, "loss": 0.0 if online else None,
                "cpu": [r.uniform(3, 35)] if online else [], "mem": [r.uniform(20, 55)] if online else [],
                "temp": [r.uniform(38, 52)] if online else [],
                "ifs": make_ifs(fixed, r, sw_spec) if online else {},
                "availability": fixed.uniform(99, 100) if online else fixed.uniform(80, 95),
                "unsupported": fixed.choice([0, 0, 0, 2]), "problems": problems,
                "age": 30 if online else 3 * 3600,
            }
        )
    r, fixed = random.Random(f"rt-borda-01-{t}"), random.Random("rt-borda-01")
    raws.append(
        {
            "id": "rt-borda-01", "name": "rt-borda-01", "role": "device", "status": "online",
            "sec": r.uniform(0.0008, 0.002), "loss": 0.0, "cpu": [r.uniform(10, 45)], "mem": [r.uniform(25, 50)],
            "temp": [r.uniform(45, 62)], "ifs": make_ifs(fixed, r, rt_spec), "availability": 99.97,
            "unsupported": 0, "problems": [], "age": 30,
        }
    )
    for name, base_ms, flaky in (("wan-operadora-a", 14, False), ("wan-operadora-b", 28, True)):
        r = random.Random(f"{name}-{t}")
        loss = r.choice([0.0, 0.0, 2.0, 6.0]) if flaky else 0.0
        raws.append(
            {
                "id": name, "name": name, "role": "wan", "status": "online",
                "sec": (base_ms + r.uniform(-3, 8)) / 1000, "loss": loss, "cpu": [], "mem": [], "temp": [], "ifs": {},
                "availability": 98.4 if flaky else 99.9, "unsupported": 0,
                "problems": [{"name": "Perda de pacotes acima de 5% no link", "severity": 4}] if loss >= 5 else [],
                "age": None,
            }
        )
    raws.append(
        {
            "id": "nobreak-ti", "name": "nobreak-ti", "role": "device", "status": "online", "sec": 0.002, "loss": 0.0,
            "cpu": [], "mem": [], "temp": [], "ifs": {}, "availability": 100.0, "unsupported": 0,
            "problems": [], "age": None,
        }
    )
    for i, r in enumerate(raws):
        r["tags"] = {"unit": ["Matriz", "Filial 1", "Filial 2"][i % 3],
                     "criticality": "alta" if r["name"] in ("sw-core-01", "rt-borda-01") or r["role"] == "wan" else "baixa"}
    return assemble(raws)


def get_network():
    now = time.time()
    if _net_cache["data"] is None or now - _net_cache["t"] > CACHE_TTL:
        try:
            result = fetch_network() if ZABBIX_URL else mock_network()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao consultar o Zabbix: {exc}")
        _net_cache["data"] = {
            "mock": not ZABBIX_URL,
            "updated": datetime.now(timezone.utc).isoformat(),
            "avail_hours": AVAIL_HOURS,
            "stale_seconds": STALE_SECONDS,
            **result,
        }
        _net_cache["t"] = now
    return _net_cache["data"]


# ---------------------------------------------------------------------------
# Visão executiva: consolida estações, servidores e rede
# ---------------------------------------------------------------------------
DISK_WARN, DISK_CRIT = 85, 95
DOMAINS = ("workstations", "servers", "network")
_exec_cache = {}


def tags_of(host):
    """Retorna as tags completas e mantém os campos usados pelos filtros executivos."""
    raw_tags = host.get("tags", [])
    normalized = {str(t.get("tag", "")).strip().lower(): t.get("value") for t in raw_tags if t.get("tag")}
    all_tags = [
        {"tag": str(t.get("tag", "")).strip(), "value": str(t.get("value", ""))}
        for t in raw_tags if str(t.get("tag", "")).strip()
    ]
    return {
        "unit": normalized.get(TAG_UNIT) or None,
        "criticality": normalized.get(TAG_CRIT) or None,
        "all": all_tags,
    }
    return {"unit": tags.get(TAG_UNIT) or None, "criticality": tags.get(TAG_CRIT) or None}


def _open_problems():
    triggers = zbx(
        "trigger.get",
        {
            "output": ["description", "priority", "lastchange"],
            "monitored": True,
            "only_true": True,
            "skipDependent": True,
            "min_severity": 2,
            "expandDescription": True,
            "selectHosts": ["hostid", "name"],
        },
    )
    rows = []
    for t in triggers:
        for th in t.get("hosts", []):
            rows.append(
                {"hostid": th["hostid"], "host": th["name"], "name": t["description"],
                 "severity": int(t["priority"]), "since": int(t["lastchange"])}
            )
    return rows


def _open_problems_mock(hosts, net):
    now = int(time.time())
    rows = []
    for x in hosts + net:
        for p in x["problems"]["top"]:
            rnd = random.Random(f'{x["name"]}-{p["name"]}')
            rows.append({"hostid": x["id"], "host": x["name"], "name": p["name"],
                         "severity": p["severity"], "since": now - rnd.randint(300, 9 * 86400)})
    return rows


def _services():
    """Serviços de negócio cadastrados em Serviços do Zabbix. None se não houver acesso."""
    if not ZABBIX_URL:
        return {"total": 4, "affected": [{"name": "ERP", "status": 4}]}
    try:
        rows = zbx("service.get", {"output": ["name", "status"]})
    except Exception:
        return None
    return {
        "total": len(rows),
        "affected": [{"name": r["name"], "status": int(r["status"])} for r in rows if int(r["status"]) >= 0],
    }


def _trend(days, index):
    """Incidentes por dia e disponibilidade (ICMP) por dia e domínio, na janela pedida."""
    dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    if not ZABBIX_URL:
        incidents = []
        for d in dates:
            rnd = random.Random(d)
            count = rnd.randint(2, 18)
            incidents.append({"date": d, "count": count, "high": rnd.randint(0, min(count, 4))})
        base = {"workstations": (88, 97), "servers": (99, 100), "network": (98.5, 100)}
        avail = {dom: [random.Random(f"{d}-{dom}").uniform(*base[dom]) for d in dates] for dom in DOMAINS}
        return dates, incidents, avail

    incidents = {d: {"date": d, "count": 0, "high": 0} for d in dates}
    by_day = {}  # (data, domínio) -> [soma ponderada, amostras]
    ids = list(index)
    if ids:
        since = int(time.time()) - days * 86400
        events = zbx(
            "event.get",
            {"output": ["clock", "severity"], "source": 0, "object": 0, "value": 1,
             "severities": [2, 3, 4, 5], "hostids": ids, "time_from": since},
        )
        for e in events:
            d = datetime.fromtimestamp(int(e["clock"])).date().isoformat()
            if d in incidents:
                incidents[d]["count"] += 1
                if int(e["severity"]) >= 4:
                    incidents[d]["high"] += 1
        items = zbx(
            "item.get",
            {"output": ["itemid", "key_", "hostid"], "hostids": ids, "monitored": True,
             "search": {"key_": "icmpping"}, "filter": {"status": 0}},
        )
        icmp = {it["itemid"]: it["hostid"] for it in items if ICMP_RE.match(it["key_"])}
        if icmp:
            rows = zbx("trend.get", {"output": ["itemid", "clock", "num", "value_avg"],
                                     "itemids": list(icmp), "time_from": since})
            for row in rows:
                dom = index[icmp[row["itemid"]]]["domain"]
                d = datetime.fromtimestamp(int(row["clock"])).date().isoformat()
                acc = by_day.setdefault((d, dom), [0.0, 0])
                acc[0] += float(row["value_avg"]) * int(row["num"])
                acc[1] += int(row["num"])
    avail = {
        dom: [by_day[(d, dom)][0] / by_day[(d, dom)][1] * 100 if (d, dom) in by_day and by_day[(d, dom)][1] else None
              for d in dates]
        for dom in DOMAINS
    }
    return dates, [incidents[d] for d in dates], avail


def _summary(items):
    total = len(items)
    online = sum(1 for i in items if i["status"] == "online")
    av = [i["availability"] for i in items if i.get("availability") is not None]
    return {
        "total": total,
        "online": online,
        "offline": sum(1 for i in items if i["status"] == "offline"),
        "unknown": sum(1 for i in items if i["status"] == "unknown"),
        "online_pct": online / total * 100 if total else None,
        "availability": sum(av) / len(av) if av else None,
        "with_problems": sum(1 for i in items if i["problems"]["count"]),
    }


def build_executive(days, unit, crit):
    hosts = get_hosts("all")["hosts"]
    net_data = get_network()
    net = net_data["devices"]
    net_names = {d["name"] for d in net}
    hosts = [h for h in hosts if not (h["kind"] == "other" and h["name"] in net_names)]

    def tg(x):
        return x.get("tags") or {}

    units = sorted({tg(x).get("unit") for x in hosts + net if tg(x).get("unit")})
    crits = sorted({tg(x).get("criticality") for x in hosts + net if tg(x).get("criticality")})

    def keep(x):
        return (not unit or tg(x).get("unit") == unit) and (not crit or tg(x).get("criticality") == crit)

    hosts = [h for h in hosts if keep(h)]
    net = [d for d in net if keep(d)]
    workstations = [h for h in hosts if h["kind"] == "workstation"]
    servers = [h for h in hosts if h["kind"] == "server"]

    index = {}
    for h in hosts:
        index[h["id"]] = {"name": h["name"], "domain": {"server": "servers", "workstation": "workstations"}.get(h["kind"], "others")}
    for d in net:
        index[d["id"]] = {"name": d["name"], "domain": "network"}

    # Problemas abertos: severidade, idade e os mais graves.
    now = int(time.time())
    rows = _open_problems() if ZABBIX_URL else _open_problems_mock(hosts, net)
    probs = [p for p in rows if p["hostid"] in index]
    ages = [now - p["since"] for p in probs]
    problems = {
        "total": len(probs),
        "by_severity": {str(s): sum(1 for p in probs if p["severity"] == s) for s in (5, 4, 3, 2)},
        "by_age": {
            "lt1h": sum(1 for a in ages if a < 3600),
            "lt24h": sum(1 for a in ages if 3600 <= a < 86400),
            "lt7d": sum(1 for a in ages if 86400 <= a < 7 * 86400),
            "gte7d": sum(1 for a in ages if a >= 7 * 86400),
        },
        "top": [
            {"host": p["host"], "name": p["name"], "severity": p["severity"], "age": now - p["since"],
             "domain": index[p["hostid"]]["domain"]}
            for p in sorted(probs, key=lambda p: (-p["severity"], p["since"]))[:10]
        ],
    }

    dates, incidents, avail = _trend(days, index)

    # Armazenamento: volumes acima dos limites iniciais do projeto (85% e 95%).
    vols = [{"host": h["name"], "mount": m["name"], "pused": m["pused"]} for h in hosts for m in h["disk"]["mounts"]]
    risky = sorted((v for v in vols if v["pused"] >= DISK_WARN), key=lambda v: -v["pused"])
    storage = {
        "warn": sum(1 for v in vols if DISK_WARN <= v["pused"] < DISK_CRIT),
        "crit": sum(1 for v in vols if v["pused"] >= DISK_CRIT),
        "total_volumes": len(vols),
        "volumes": risky[:10],
    }

    # Servidores críticos afetados (exige a tag de criticidade nos hosts).
    tagged = [s for s in servers if tg(s).get("criticality")]
    affected = [
        {"name": s["name"], "unit": tg(s).get("unit"), "status": s["status"],
         "problems": s["problems"]["count"], "max": s["problems"]["max"]}
        for s in tagged
        if tg(s)["criticality"].lower() in CRIT_HIGH and (s["status"] != "online" or s["problems"]["count"])
    ]
    affected.sort(key=lambda s: (s["status"] == "online", -s["max"], s["name"].lower()))

    # Qualidade da coleta: falta de dado nunca é tratada como estado saudável.
    everyone = hosts + net
    issues = []
    for x in everyone:
        found = []
        if x["status"] == "unknown":
            found.append("Sem dados de disponibilidade")
        if x["status"] == "online" and x.get("age") is not None and x["age"] > STALE_SECONDS:
            found.append("Dados antigos")
        if x.get("unsupported"):
            found.append(f'{x["unsupported"]} item(ns) não suportado(s)')
        if found:
            issues.append({"name": x["name"], "issues": found})
    issues.sort(key=lambda i: (-len(i["issues"]), i["name"].lower()))

    def top(key):
        vals = [{"name": h["name"], "value": h[key]} for h in hosts if h.get(key) is not None]
        return sorted(vals, key=lambda v: -v["value"])[:10]

    return {
        "mock": not ZABBIX_URL,
        "updated": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "avail_hours": AVAIL_HOURS,
        "stale_seconds": STALE_SECONDS,
        "filters": {"units": units, "criticalities": crits, "applied": {"unit": unit, "criticality": crit},
                    "tag_names": {"unit": TAG_UNIT, "criticality": TAG_CRIT}},
        "domains": {"workstations": _summary(workstations), "servers": _summary(servers), "network": _summary(net)},
        "problems": problems,
        "trend": {"dates": dates, "incidents": incidents, "availability": avail},
        "wan": [
            {"name": d["name"], "status": d["status"], "latency_ms": d["latency_ms"], "loss_pct": d["loss_pct"],
             "availability": d["availability"], "problems": d["problems"]["count"]}
            for d in net if d["role"] == "wan"
        ],
        "critical_servers": {"list": affected, "tag_missing": not tagged},
        "services": _services(),
        "storage": storage,
        "tops": {
            "cpu": top("cpu"),
            "mem": top("mem"),
            "interfaces": [i for i in net_data["interfaces"]["top_util"] if i["host"] in {d["name"] for d in net}],
        },
        "collection": {
            "unknown": sum(1 for x in everyone if x["status"] == "unknown"),
            "stale": sum(1 for x in everyone if x["status"] == "online" and x.get("age") is not None and x["age"] > STALE_SECONDS),
            "unsupported": sum(x.get("unsupported") or 0 for x in everyone),
            "hosts": issues[:10],
        },
    }


def get_executive(days: int = 7, unit: str = "", criticality: str = ""):
    days = max(1, min(days, 30))
    key = (days, unit, criticality)
    now = time.time()
    cached = _exec_cache.get(key)
    if cached is None or now - cached[0] > CACHE_TTL:
        try:
            data = build_executive(days, unit, criticality)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao consultar o Zabbix: {exc}")
        _exec_cache[key] = (now, data)
        cached = _exec_cache[key]
    return cached[1]
