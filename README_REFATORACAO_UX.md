# Refatoração UX do front-end

- Novo design system único em `static/ui.css` (já servido pelo `app.py`, que monta `/static` quando a pasta existe).
- As 5 páginas deixaram de ter CSS duplicado e paletas divergentes; cada uma mantém só um bloco mínimo específico.
- JS, IDs, classes, rotas e estrutura de cards intactos (verificado por hash do `<script>` de cada página).
- Navegação idêntica em todas as páginas (Executivo e Configuração ganharam o menu); cabeçalho fixo com indicação da página atual.
- Tabelas com cabeçalho fixo, hover e rolagem própria; foco visível por teclado; `prefers-reduced-motion`; menu rolável no celular.
- Modo de edição com contorno tracejado nos cards editáveis.
Para reverter uma página: restaure o HTML original e remova o link para `/static/ui.css`.
