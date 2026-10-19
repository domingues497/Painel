# Configuração de alertas do Painel Executivo

O módulo de alertas permite notificar destinatários por e-mail e/ou grupos/chats do Telegram quando surge um problema ativo no Zabbix cuja severidade foi selecionada.

## Configurar

1. Inicie o Painel e abra `http://localhost:8000/executivo.html`.
2. Na seção **Central de alertas**, selecione o tipo de host que pode gerar notificações (todos, switches, servidores, computadores ou rede) e as severidades (Alta e Desastre vêm marcadas por padrão).
3. Configure um ou ambos os canais, informe os destinatários e os dados SMTP/Telegram.
4. Clique em **Salvar configuração**. Depois, use **Salvar e enviar teste** para validar a entrega.
5. Marque **Ativar monitoramento e envio automático** e salve.

### E-mail

Informe o hostname SMTP (não o endereço de e-mail), porta, segurança (STARTTLS, SSL/TLS ou sem criptografia), endereço remetente e destinatários. Usuário e senha SMTP são opcionais se o servidor aceitar envio sem autenticação. Para contas no Microsoft 365 Exchange Online, use `smtp.office365.com`, porta `587` e `STARTTLS`. `mail.witmarsum.coop.br` é o hostname de recebimento (MX) e não deve ser usado como endpoint SMTP autenticado do Microsoft 365. O painel conserva o hostname SMTP que você preencher; se houver erro de certificado, confirme se o hostname corresponde ao certificado apresentado pelo servidor. Não desative a validação de certificados para contornar hostname incorreto.

### Telegram

Crie um bot pelo `@BotFather`, informe o token do bot e um ou mais `chat_id`s. Adicione o bot ao grupo e confirme que ele pode enviar mensagens. Os IDs podem ser separados por vírgula ou quebra de linha.

## Comportamento

- O monitor consulta os problemas ativos com `problem.get` e resolve os hosts associados usando `trigger.get` com `selectHosts`, conforme a API do Zabbix 7.x. O parâmetro `selectHosts` não é válido diretamente em `problem.get`. O usuário/token configurado no painel precisa ter permissão de leitura dos problemas, triggers e hosts.
- O intervalo padrão é de 60 segundos (mínimo 15 segundos).
- O serviço notifica eventos cuja severidade esteja marcada e que correspondam ao filtro **Tipo de host**. As opções são todos os hosts, switches, servidores, computadores ou rede; em um evento associado a vários hosts, o alerta inclui somente os hosts que correspondem ao tipo escolhido. A configuração padrão seleciona todos os hosts e as severidades **Alta** e **Desastre**. Ao salvar, a API relê o arquivo e confirma os campos críticos antes de informar sucesso; o formulário não deve substituir os valores informados por valores padrão.
- O mesmo `eventid` não é reenviado para um mesmo destinatário após uma entrega confirmada. Se um canal falhar, o sistema tenta novamente na próxima consulta.
- Na primeira consulta depois de ativar, os problemas que já estiverem ativos e corresponderem aos filtros também podem ser notificados. Tenha isso em mente para evitar uma carga inicial de mensagens inesperada.
- Este módulo envia notificações de abertura/estado ativo; não envia mensagens de recuperação quando o problema fecha.
- A configuração e o histórico ficam em um diretório persistente do perfil do usuário, separado da pasta do projeto: no Windows, `%LOCALAPPDATA%\PainelZabbix\alert_config.json` e `alert_state.json`; no Linux, `~/.local/share/PainelZabbix/`. Também é possível definir `PANEL_DATA_DIR` para escolher um diretório específico. Ao iniciar a nova versão, o painel migra uma única vez os arquivos antigos da pasta do projeto. A configuração contém senha SMTP e token do bot; não compartilhe esses arquivos. As permissões são restringidas quando o sistema operacional permite.
- O formulário não revela os segredos já salvos. Deixar o campo de senha/token em branco mantém o valor guardado.

## Verificação

A seção de status mostra o horário da última consulta, quantidade de problemas ativos, última notificação e eventual erro de entrega. O botão de teste envia uma mensagem de validação aos canais habilitados, usando os dados salvos.


## Segurança

As rotas de configuração ficam disponíveis na API do painel, que nesta versão não implementa autenticação própria. Mantenha o painel em rede confiável ou atrás do mecanismo de autenticação/firewall usado pela organização. Não exponha esta aplicação diretamente à internet.

### Card visual no corpo do e-mail

Os alertas de problemas ativos são enviados como `multipart/alternative`: uma versão HTML com card visual (compatível com clientes como Outlook por usar tabelas e estilos inline) e uma versão em texto simples para clientes sem HTML. O card inclui nome do host, severidade, descrição do problema/trigger, status do servidor, uptime, disponibilidade das últimas 24 h, quantidade de itens não suportados, horário de início e ID do evento. Os dados adicionais são enriquecidos a partir do resumo de hosts do dashboard em cache; se essa consulta não estiver disponível, o alerta continua sendo enviado com os dados do problema e do host que o Zabbix retornou.


### Diagnóstico de alertas que não foram enviados

A linha de status na Central de alertas agora exibe, a cada consulta, a quantidade de problemas ativos encontrada pelo Zabbix, quantos passaram pelos filtros, quantos foram ignorados por severidade ou tipo de host, e quantos envios de e-mail/Telegram foram tentados, aceitos ou falharam. O campo **Diagnóstico** registra o motivo observado para o problema mais recente: por exemplo, severidade não selecionada, host fora das categorias escolhidas, destino já notificado (deduplicação), falha SMTP/Telegram ou nenhum problema ativo retornado. Uma falha de envio não marca o destino como notificado; o monitor tenta novamente no próximo ciclo.

Se o Zabbix tiver um problema ativo com severidade diferente das escolhidas, ele não será enviado. Se o status indicar zero problemas ativos, confira no Zabbix se o evento está na lista de problemas ativos (não apenas em Histórico), e se o trigger realmente entrou em estado PROBLEM.
