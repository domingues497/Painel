# KPIs ICMP dos hosts

Itens considerados:
- `icmpping`: determina Online (1) ou Offline (0), quando há um valor coletado.
- `icmppingloss`: percentual de perda de pacotes.
- `icmppingsec`: tempo de resposta em segundos, convertido para milissegundos na interface.
- `system.uptime`: tempo desde a inicialização do sistema, quando o agente coleta esse item.

O ICMP tem prioridade para o estado Online/Offline; sem item ICMP, a disponibilidade do agente é usada como fallback. Ausência de item não é tratada como zero.

KPIs adicionados: hosts online/offline, percentual online, disponibilidade histórica da janela configurada, hosts com perda ICMP, hosts com latência acima de 100 ms, perda e latência por host.

Limitação: `Ligado há` usa `system.uptime`, pois ICMP não informa quando o sistema foi inicializado. Para hosts apenas com ICMP, o uptime fica indisponível em vez de inventar um valor.
