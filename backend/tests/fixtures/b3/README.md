# Fixtures B3 (sintéticas)

Geradas por `make_b3_fixtures.py`. Reproduzem **exatamente o layout** dos extratos reais da Área do Investidor B3
(validado em 08/10/2026 com os arquivos do usuário, que foram apagados depois), com uma **carteira fictícia**.

## Layout real observado

Comum aos dois arquivos: `.xlsx`, uma única aba, linha 1 = cabeçalho, ordem **mais recente primeiro**.
Datas são **texto** `dd/mm/aaaa` (formato de célula `dd/MM/yyyy`). Números são células numéricas `int`/`float`
(formato `R$`); campo vazio = texto `"-"`.
O XML da planilha declara `<dimension ref="A1"/>` mesmo com centenas de linhas: no modo `read_only` do
openpyxl é preciso chamar `reset_dimensions()`, senão só a primeira célula é lida.

### Negociação (aba `Negociação`)
`Data do Negócio | Tipo de Movimentação | Mercado | Prazo/Vencimento | Instituição | Código de Negociação | Quantidade | Preço | Valor`

- `Tipo de Movimentação`: `Compra` / `Venda`.
- `Mercado`: `Mercado à Vista`, `Mercado Fracionário`, `Futuro`.
  **`Futuro` (WDO, WIN…) deve ser ignorado** — trades de futuros não fazem parte da carteira.
- `Código de Negociação`: fracionário vem com sufixo `F` (`BBAS3F`) → normalizar.
- `Prazo/Vencimento`: `-`, ou data (futuros; às vezes aparece também em linha de ação — ignorar).
- Duas linhas idênticas no mesmo dia são negócios legítimos distintos (hash precisa de índice de ocorrência).

### Movimentação (aba `Movimentação`)
`Entrada/Saída | Data | Movimentação | Produto | Instituição | Quantidade | Preço unitário | Valor da Operação`

- `Entrada/Saída`: `Credito` / `Debito` (sem acento).
- `Produto`: `"TICKER - NOME DA EMPRESA"`; futuros vêm como `"Futuro - WDOV25"`; renda fixa como `"CDB - …"`.
- O nome da corretora varia (`XP INVESTIMENTOS CCTVM S/A` e `… S/A.`; `AGORA CTVM S/A` e `AGORA CORRETORA …`).

| Movimentação | Tratamento |
|---|---|
| `Compra` / `Venda` | **Ignorar** — no arquivo real eram 100% futuros (`Produto` = `Futuro - …`, qtd 0, valor `-`) |
| `Transferência - Liquidação` | **Ignorar** — liquidação de negócio que já vem na Negociação (D+2, agregado por dia) |
| `Transferência` | Ignorar — custódia entre corretoras (não muda a posição) |
| `Dividendo` | `DIVIDEND`; valor = líquido (= bruto) |
| `Juros Sobre Capital Próprio` | `JCP`; **`Valor da Operação` é LÍQUIDO** (após IRRF); `Preço unitário` é o bruto por ação, arredondado |
| `Rendimento` | `INCOME` (em ações, é atualização monetária de provento) |
| `… - Transferido` (JCP/Dividendo) | Ignorar — provisão migrando entre corretoras (par débito/crédito) |
| `Bonificação em Ativos` | `BONUS`; quantidade pode ser fracionária; **sem custo atribuído** (fica pendente) |
| `Fração em Ativos` | Ignorar (débito da fração que vai a leilão) |
| `Leilão de Fração` | `FRACTION_AUCTION` (qtd, preço unitário, valor creditado) |
| `Desdobro` | `SPLIT`; quantidade = **ações novas creditadas** (fator vem da fonte de eventos) |
| `Grupamento` | `REVERSE_SPLIT`; quantidade = **posição resultante** |
| `Atualização` | Ignorar (informativo, quantidade = posição total) |
| `Direito de Subscrição`, `Cessão de Direitos(- Solicitada)`, `Direitos de Subscrição - Não Exercido` | Ignorar enquanto não houver exercício (não houve no histórico real) |
| `RESGATE ANTECIPADO/` (CDB) | Ignorar — renda fixa fora do escopo |

Conferência feita com os dados reais: posições reconstruídas (Negociação + eventos da Movimentação) bateram com o
Investidor10, e a soma de Dividendo + JCP + Rendimento bateu com o total de proventos (diferença de centavos).

## Carteira fictícia das fixtures — posição final esperada
| Ticker | Qtd | Observação |
|---|---|---|
| ITSA4 | 52 | 50 compradas + bonificação 2,5 − fração 0,5 leiloada |
| BBAS3 | 10 | 5 compradas + desdobro 1:2 (5 novas) |
| TAEE4 | 20 | duas compras idênticas de 10 no mesmo dia |
| WEGE3 | 80 | 100 compradas − 20 vendidas |
| MGLU3 | 0 | 120 → grupamento 10:1 → 12 → vendidas |
