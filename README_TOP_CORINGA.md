# TOP 10 — busca dinâmica e curinga em itens do Zabbix

O campo **Item a medir** agora filtra sugestões enquanto você digita.

- Texto sem `*`: filtra por trecho do nome ou da chave do item.
- `*` em qualquer posição: funciona como curinga. Exemplo: `*Space: Used, in %` pode corresponder aos itens de C:, D: e R:.
- Clique em uma sugestão para selecionar somente aquele item/chave.
- Pressione **Enter** para aplicar a consulta inteira e medir todos os itens correspondentes.
- O filtro continua respeitando o grupo, a tag do item e o valor da tag.
- Quando vários itens correspondem dentro do mesmo host, o card mantém o host uma única vez e usa o maior valor numérico encontrado. O nome do item responsável pelo valor aparece ao passar o mouse sobre o valor do ranking.
- A seleção e a consulta usada ficam salvas com a configuração do card.

O painel mostra até 40 sugestões de cada vez para evitar uma lista excessivamente longa; o contador informa o total de itens correspondentes.
