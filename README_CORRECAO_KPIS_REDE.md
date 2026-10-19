# Correção dos indicadores da página Rede

## Links WAN online

O resumo agora prioriza as interfaces classificadas como WAN (`data.interfaces.wan`), que é o formato usado pelo MikroTik quando cada operadora é representada por uma interface física/lógica (por exemplo, `sfp-sfpplus1-WAN1`, `sfp-sfpplus2-WAN2` e `pppoe-BRASILNET`). O indicador mostra `interfaces online / total de interfaces WAN` quando existem estados conhecidos. Se não houver interfaces identificadas, mantém o fallback para hosts de sonda WAN individuais.

## Disponibilidade nas últimas 24 horas

- Corrigido o tratamento de `value_type=0` ao consultar o histórico SNMP.
- A disponibilidade usa o histórico do item `zabbix[host,snmp,available]` e pondera os estados pela duração entre amostras.
- A cobertura observada deve representar pelo menos 80% da janela; não é mais obrigatório haver uma amostra antes exata do início das 24 horas.
- Se o histórico não for suficiente, o painel tenta usar `trend.get` para o item SNMP, quando há cobertura de pelo menos 80% das horas.
- Se o histórico SNMP continuar insuficiente, a disponibilidade histórica ICMP pode ser usada como fallback mesmo quando o item SNMP existe, desde que o Zabbix tenha Trends ICMP disponíveis.
- Se não houver histórico suficiente em nenhum dos métodos, o painel exibe `—` em vez de inventar um percentual.

## Validação

A lógica foi testada com cenários simulados: estados constantes, transição de disponível para indisponível, janela sem amostra antes do início mas com cobertura suficiente e fallback por Trends. O indicador WAN foi ajustado para as interfaces que aparecem na tabela de Links WAN.
