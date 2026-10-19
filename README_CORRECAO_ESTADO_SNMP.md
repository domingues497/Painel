# Ajuste da disponibilidade por uptime

A disponibilidade exibida no resumo da página Rede prioriza um item de uptime recente, conforme a regra solicitada: `min(uptime / duração da janela, 100%)`. Para uma janela de 24 horas, uptime de 140 dias resulta em 100%; uptime de 12 horas resulta em 50%.

O estado atual do dispositivo continua usando a disponibilidade do agente SNMP. Quando não há uptime atual, o painel usa o histórico SNMP e depois ICMP como fallback.

Importante: uptime estima tempo desde a inicialização; não detecta indisponibilidade de rede/SNMP que não reinicie o dispositivo. Para medir falhas de conectividade com precisão, mantenha histórico SNMP ou ICMP adequado.
