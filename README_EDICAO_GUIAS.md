# Modo de edição e guias de alinhamento

- O botão **Editar painel**, ao lado do horário de atualização, libera o arraste, redimensionamento e configuração de itens Zabbix. Ao clicar em **Concluir edição**, esses controles voltam a ficar ocultos.
- Durante o arraste, linhas guias verticais e horizontais aparecem quando as bordas ou centros do cartão chegam perto dos cartões vizinhos. O cartão encaixa na linha, facilitando alinhar bordas e centros.
- O mesmo alinhamento está aplicado aos TOPs configuráveis. Ao redimensionar pelo canto inferior direito, as bordas também encaixam perto das linhas dos demais cards.
- Layout, posição e tamanho continuam salvos no navegador. O modo de edição inicia desligado para evitar movimentações acidentais.

Teste em uma cópia antes de substituir seu projeto e preserve o `.env`.

## Pausa das atualizações durante edição

Ao ativar **Editar painel**, as páginas de switches, hosts, rede e Executivo pausam as atualizações automáticas de dados na interface. Respostas que já estavam em andamento são descartadas para não redesenhar os cards no meio do ajuste. Ao clicar em **Concluir edição**, o painel faz uma atualização imediata e retoma a periodicidade normal. O monitor de alertas no backend continua ativo independentemente do modo de edição.

## Renomear cards

No modo **Editar painel**, clique no ícone ✎ do card (ou dê duplo clique no título), digite o novo nome e tecle Enter (Esc cancela; vazio restaura o nome original). Nos TOPs de Hosts o campo fica no menu ⋮ > *Nome do card*. O nome é salvo no navegador e não altera a posição, o tamanho nem o que o card monitora.

## Experiência do modo de edição

- Cada card ganha uma barra única (✎ renomear · ⠿ arrastar · × excluir), visível só ao editar.
- Ao arrastar/redimensionar, um contorno tracejado mostra onde o card vai assentar ao soltar.
- Excluir não pede confirmação do navegador: o card some, os demais sobem e aparece o aviso **Desfazer** (7 s). Também dá para usar *Restaurar cards excluídos*.
- Barra fixa no rodapé com os gestos e o botão **Concluir**; o canto de redimensionar fica marcado.

## Assistente de padronização

Ao terminar de redimensionar um card, aparece uma sugestão para o grupo (container) inteiro: **Mesmo tamanho** (usa o tamanho que você acabou de definir) ou **cards por linha** (1 a N, conforme a largura disponível), que alinha todos em grade, na ordem visual atual, com largura que preenche a linha. Em cada linha, todos os cards assumem a altura do mais alto dela (bordas alinhadas). O resultado pode ser desfeito pelo aviso **Desfazer**; *Agora não* ou Esc dispensam.

O seletor *cards por linha* oferece de 1 até o total de cards do grupo. Opções com borda tracejada deixam os cards mais estreitos que o mínimo padrão (o mínimo do grupo é reduzido e guardado); opções que resultariam em menos de 80 px por card ficam desabilitadas.

## Cálculos dos TOP 10 (botão Σ)

Cada TOP tem um botão **Σ** no cabeçalho (sempre visível, não só na edição). Ele abre um painel com quantidade, soma, média, mediana, P95, máximo e mínimo (com o nome do host), amplitude e desvio padrão amostral. A **base** pode ser o *TOP 10 exibido* ou *todos os hosts com dado* para a combinação grupo/tag/item. A soma é omitida em métricas percentuais (somar % de hosts diferentes não faz sentido) e há aviso quando os itens têm unidades diferentes. **Copiar tabela e cálculos** gera texto separado por TAB para colar no Excel/Planilhas. O estado do painel (aberto, base) fica guardado no card. Lógica pura em `static/rank-calc.js`.
