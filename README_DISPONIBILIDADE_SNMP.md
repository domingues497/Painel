# Estado e disponibilidade de equipamentos de rede

A página Rede utiliza o estado atual do agente SNMP como fonte prioritária.

- Item interno `zabbix[host,snmp,available]`: `1` = online/disponível; `0` = offline/indisponível; `2` = estado desconhecido.
- Se esse item não existir, o painel usa o campo de disponibilidade SNMP da API `host.get`, quando o host tem interface SNMP configurada.
- ICMP continua como fallback para hosts sem estado SNMP disponível.

## Disponibilidade na janela de 24 horas

Quando existe o item `zabbix[host,snmp,available]`, o painel calcula a disponibilidade usando o histórico de estados ao longo da janela configurada (`AVAIL_HOURS`, padrão 24). Os estados são ponderados pela duração até a amostra seguinte; `1` é tempo disponível, `0` é tempo indisponível e `2` é desconhecido e não entra no denominador. Para evitar percentagens enganosas, o painel só apresenta o valor quando há cobertura conhecida de pelo menos 80% da janela.

Se o item de estado SNMP não existir, a disponibilidade histórica por ICMP permanece como alternativa quando há histórico de `icmpping`.

**Nota:** itens `system.hw.uptime`, `system.net.uptime` e `system.uptime` indicam tempo desde a inicialização/reinicialização; sozinhos não medem o tempo total indisponível nas últimas 24 horas. Por isso, a porcentagem histórica é calculada a partir do histórico de disponibilidade, que representa diretamente as transições disponível/indisponível.
