# Painel Zabbix — posicionamento livre dos TOPs

## Alterações desta versão
- Os cards TOP 10 não usam mais grade com posições fixas.
- Arraste pelo cabeçalho/título do card para posicioná-lo livremente na área dos rankings.
- Arraste o canto inferior direito para ajustar largura e altura com o mouse.
- A posição e as dimensões são salvas no `localStorage` do navegador.
- O botão **Duplicar card** fica dentro do menu `⋮` > configurações.
- O card duplicado aparece deslocado do original para facilitar encontrá-lo.

## Instalação
1. Faça backup da versão em uso.
2. Extraia os arquivos deste ZIP em uma cópia do projeto.
3. Preserve seu arquivo `.env` atual; ele não é incluído neste pacote.
4. Reinicie o FastAPI e atualize a página com `Ctrl+F5`.

## Observação
A posição é livre dentro da área horizontal do painel e verticalmente sem limite fixo. Os cards NÃO se sobrepõem e se reordenam como uma lista Sortable: ao arrastar ou redimensionar um card por cima de outro, os demais abrem espaço (deslizam para baixo em cascata); ao soltar, todos sobem e preenchem os vazios, assumindo a nova ordem visual. Layouts salvos antigos com sobreposição são reorganizados ao abrir a página (lógica em `static/no-overlap.js`). A persistência é local por navegador.

## Todos os cards ajustáveis

A versão inclui movimentação livre e redimensionamento com o mouse nos cards dos switches, KPIs, servidores, links WAN, rankings de rede e painel executivo. Use o pequeno ícone ⠿ no canto superior direito para mover um cartão e o canto inferior direito para redimensionar. As posições e dimensões são salvas no `localStorage` de cada navegador, separadas por área. O primeiro acesso organiza os cards automaticamente; depois disso, o layout escolhido fica salvo.
