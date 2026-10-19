# Correção das métricas de memória e disco

O painel agora consulta os itens habilitados dos hosts sem limitar a consulta a uma lista fixa de `key_`, para não perder variações entre templates Windows/Linux.

## Memória
A métrica é identificada, por prioridade, por `vm.memory.utilization`, `vm.memory.size[pused]`, `vm.memory.size[pavailable]` ou pela razão entre `vm.memory.size[used]` e `vm.memory.size[total]`. Quando o item traz memória disponível em percentual, o painel converte para percentual utilizado (`100 - disponível`).

## Disco
O painel reconhece `vfs.fs.size[<volume>,pused]`, `pfree`, `used` e `total`. Para cada volume, prioriza o percentual usado; se ele não existir, converte percentual livre para usado, ou calcula `used / total * 100` quando os itens retornam bytes.

## Validação
A lógica foi validada com itens simulados, incluindo `vm.memory.size[pavailable]` e as variantes de disco por percentual e por bytes. É necessário confirmar os valores do ambiente real, pois a disponibilidade de cada métrica depende dos itens habilitados e suportados nos hosts do Zabbix.
