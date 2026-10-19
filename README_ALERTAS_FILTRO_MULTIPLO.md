# Alertas por múltiplos tipos de host

Na área Executivo > Central de alertas, o filtro de tipo de host agora usa caixas de seleção (flags):

- Todos os hosts
- Switches
- Servidores
- Computadores
- Rede

É possível marcar mais de uma categoria, por exemplo **Servidores + Rede**. A opção **Todos os hosts** é exclusiva: ao marcá-la, as demais categorias são desmarcadas; ao marcar uma categoria específica, a opção Todos é desmarcada.

A seleção é persistida em `host_type_filters` e aplicada ao monitor de alertas para e-mail e Telegram. Configurações antigas que continham `host_type_filter` singular são migradas automaticamente quando carregadas.
