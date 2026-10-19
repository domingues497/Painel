# Detecção de WAN em MikroTik / Zabbix

Esta versão considera o padrão de nomes exibido no host `WITMARSUM-RB-001`, por exemplo:

- `Interface sfp-sfpplus1-WAN1(Link LIGGA): Bits received`
- `Interface sfp-sfpplus1-WAN1(Link LIGGA): Bits sent`
- `Interface sfp-sfpplus2-WAN2(Link BRASILNET): Bits received`
- `Interface sfp-sfpplus2-WAN2(Link BRASILNET): Bits sent`
- `Interface pppoe-BRASILNET(): Bits received`

## O que foi ajustado

- Hosts cujo nome inclui `MikroTik`, `RouterBOARD` ou o padrão `RB-001` são identificados como dispositivos de rede mesmo que estejam em um grupo com outro nome.
- A consulta inclui tags dos itens (`selectTags`), para recuperar descrições de operadora quando elas não aparecem no campo de alias.
- Os itens de interface habilitados dos hosts de rede são obtidos e filtrados localmente; isso evita que variações no índice de busca de `item.get` omitam itens `net.if.*`.
- A detecção WAN considera `WAN`, `Operadora`, `ISP` e descrições como `Link LIGGA` / `Link BRASILNET`.

- A interface lógica `pppoe-BRASILNET` também é reconhecida como WAN e identificada como **Filial Quero Quero — BRASILNET**, mesmo se o item vier sem alias. Ela aparece na tabela de Links WAN e nos rankings de uso/erros quando houver dados correspondentes.
- O padrão do campo `WAN_IF_PATTERN` é aplicado ao nome, alias e tags do item.

## Se o host ainda não aparecer

1. Confirme que o host está habilitado/monitorado no Zabbix.
2. Em **Dados recentes**, confirme que os itens `Bits received`, `Bits sent` e `Operational status` estão habilitados e recebendo dados.
3. Se seu host não tem `MikroTik`, `RouterBOARD` ou `RB-001` no nome e não está num grupo de rede conhecido, adicione seu grupo em `NETWORK_GROUPS` no `.env`, por exemplo:

```env
NETWORK_GROUPS=Rede,Network,Roteadores,Routers,Firewalls,Wireless,Energia,MikroTik,Equipamentos de Rede
```

4. O nome/alias da interface deve conter `WAN`, `Operadora` ou `ISP`; com o template do exemplo, `WAN1` e `WAN2` serão reconhecidos.
5. Reinicie o FastAPI depois de alterar o `.env`.

Não é necessário criar uma sonda ICMP por operadora para que as interfaces físicas WAN1/WAN2 sejam listadas. Sondas ICMP são outro recurso e servem para medir conectividade até um destino externo por operadora.
