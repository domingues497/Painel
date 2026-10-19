# Configuração da conexão Zabbix

Abra `http://localhost:8000/configuracao.html`.

- URL completa da API JSON-RPC.
- Autenticação por token (recomendada) ou usuário/senha.
- Testar conexão sem salvar.
- Testar e salvar: só grava no `.env` após teste bem-sucedido.
- Reinicie o Uvicorn depois de salvar para aplicar as variáveis carregadas pelos módulos.

Segurança: prefira um token de uma conta de serviço somente leitura. Credenciais de usuário/senha ficam no `.env` local; restrinja as permissões do arquivo. Não exponha o painel sem autenticação administrativa. Mantenha a validação TLS ativa em produção.


## Correção de autenticação JSON-RPC
O cliente foi ajustado para não enviar o parâmetro JSON-RPC legado `auth`.
Tanto o token de API quanto o token de sessão retornado por `user.login` são
enviados no cabeçalho HTTP `Authorization: Bearer ...`, compatível com o fluxo
de autenticação das versões recentes do Zabbix. Após substituir os arquivos,
reinicie o Uvicorn e teste a conexão novamente.
