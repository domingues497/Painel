"""Cliente JSON-RPC do Zabbix com token de API ou usuário/senha."""
import requests
from config import ZABBIX_URL, ZABBIX_TOKEN, ZABBIX_AUTH_TYPE, ZABBIX_USERNAME, ZABBIX_PASSWORD, VERIFY_TLS


def _post(url, payload, headers, verify):
    response = requests.post(url, json=payload, headers=headers, timeout=15, verify=verify)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        error = body["error"]
        raise RuntimeError(error.get("data") or error.get("message") or "Erro na API do Zabbix")
    return body.get("result")


def call_zabbix(method, params, *, url, auth_type, token="", username="", password="", verify_tls=True):
    """Executa JSON-RPC usando Bearer token no cabeçalho HTTP.

    O Zabbix 7.x não aceita o parâmetro JSON-RPC legado `auth` no corpo.
    Para autenticação por usuário/senha, o token retornado por user.login é
    enviado no cabeçalho Authorization: Bearer nas chamadas seguintes.
    """
    headers = {"Content-Type": "application/json-rpc"}
    auth_type = (auth_type or "token").lower()

    if auth_type == "token":
        if not token:
            raise RuntimeError("Informe o token da API do Zabbix.")
        headers["Authorization"] = f"Bearer {token}"
        return _post(
            url,
            {"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            headers,
            verify_tls,
        )

    if auth_type == "password":
        if not username or not password:
            raise RuntimeError("Informe usuário e senha do Zabbix.")

        session_token = _post(
            url,
            {
                "jsonrpc": "2.0",
                "method": "user.login",
                "params": {"username": username, "password": password},
                "id": 1,
            },
            headers,
            verify_tls,
        )
        if not session_token:
            raise RuntimeError("O login no Zabbix não retornou um token de sessão.")

        authenticated_headers = {
            **headers,
            "Authorization": f"Bearer {session_token}",
        }

        if method == "user.login":
            return session_token

        try:
            return _post(
                url,
                {"jsonrpc": "2.0", "method": method, "params": params, "id": 2},
                authenticated_headers,
                verify_tls,
            )
        finally:
            # Best-effort logout. Authentication is in the HTTP header, not JSON body.
            try:
                _post(
                    url,
                    {"jsonrpc": "2.0", "method": "user.logout", "params": [], "id": 3},
                    authenticated_headers,
                    verify_tls,
                )
            except Exception:
                pass

    raise RuntimeError("Tipo de autenticação não reconhecido.")


def zbx(method, params):
    if not ZABBIX_URL:
        raise RuntimeError("ZABBIX_URL não está configurada. Acesse Configuração para conectar o Zabbix.")
    return call_zabbix(method, params, url=ZABBIX_URL, auth_type=ZABBIX_AUTH_TYPE,
                       token=ZABBIX_TOKEN, username=ZABBIX_USERNAME,
                       password=ZABBIX_PASSWORD, verify_tls=VERIFY_TLS)


def test_connection(*, url, auth_type, token="", username="", password="", verify_tls=True):
    # apiinfo.version must be called without authentication headers in Zabbix.
    version = _post(
        url,
        {"jsonrpc": "2.0", "method": "apiinfo.version", "params": {}, "id": 1},
        {"Content-Type": "application/json-rpc"},
        verify_tls,
    )
    # Then validate that the supplied credentials can access an authenticated method.
    hosts = call_zabbix(
        "host.get", {"output": ["hostid"], "limit": 1},
        url=url, auth_type=auth_type, token=token,
        username=username, password=password, verify_tls=verify_tls,
    )
    return {"success": True, "version": version, "host_count_sample": len(hosts or [])}
