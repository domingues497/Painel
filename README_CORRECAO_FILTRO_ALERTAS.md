# Correção — persistência do filtro de tipos de host

Esta versão corrige o salvamento e a releitura de `host_type_filters` em Executivo > Central de alertas.

- A API distingue o campo de seleção múltipla do campo singular legado.
- A seleção enviada pelo formulário é normalizada: `Todos os hosts` é exclusivo; se nenhuma categoria específica estiver marcada, salva `all`.
- O backend normaliza o filtro na camada de persistência.
- Depois de salvar, a interface compara as categorias enviadas com as categorias devolvidas pela API e informa erro explícito caso haja divergência.

Categorias aceitas: `all`, `switches`, `servers`, `computers`, `network`.

## Teste recomendado

1. Em `executivo.html`, marque `Servidores` e `Rede`.
2. Clique em **Salvar configuração** e confirme a mensagem de sucesso.
3. Atualize a página e verifique se somente essas duas opções continuam marcadas.
4. Repita com outra combinação para confirmar a persistência.

A configuração continua no diretório persistente do usuário definido por `services/alert_manager.py` (`%LOCALAPPDATA%\\PainelZabbix` no Windows, salvo se `PANEL_DATA_DIR` estiver definido).
