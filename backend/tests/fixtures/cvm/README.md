# Fixtures — CVM (dados abertos)

Recortes **reais e públicos** (CEMIG, Banco do Brasil, Metalúrgica Gerdau) dos arquivos de
`dados.cvm.gov.br/dados/CIA_ABERTA`, gerados por `make_cvm_fixtures.py` a partir do cache da ingestão.

## Layout observado (out/2026)
- Zips anuais `dfp_cia_aberta_{ano}.zip` e `itr_cia_aberta_{ano}.zip`: índice + `BPA`, `BPP`, `DRE`, `DFC_MI`,
  `DFC_MD`, `DMPL`, `DVA`, `DRA`, `composicao_capital`, `parecer`, cada um em `_con` (consolidado) e `_ind`.
- CSV `;`, latin-1. Colunas: `CNPJ_CIA, DT_REFER, VERSAO, ESCALA_MOEDA (MIL|UNIDADE), ORDEM_EXERC
  (ÚLTIMO|PENÚLTIMO), DT_INI_EXERC (só fluxos), DT_FIM_EXERC, CD_CONTA, DS_CONTA, VL_CONTA`.
- Refazimentos = mais de uma `VERSAO` para o mesmo `CNPJ_CIA + DT_REFER` → usar a maior.
- ITR: DRE traz o trimestre isolado **e** o acumulado do ano; DFC só o acumulado. A coluna `PENÚLTIMO` traz o
  mesmo acumulado do ano anterior (base do TTM).
- Códigos variam por modelo: lucro 3.11 (empresas e bancos) ou 3.13 (seguradoras); PL 2.03 ou 2.07 (bancos);
  bancos não têm ativo/passivo circulante. Por isso as contas são localizadas por nível + descrição.
- `3.99.*` (lucro por ação) vem em R$/ação mesmo quando `ESCALA_MOEDA = MIL`; há arquivos com lixo nesse campo.
- `composicao_capital` **não tem coluna de escala**: algumas empresas informam unidades (PETR, BBAS, GOAU),
  outras milhares (ITSA, TAEE, CMIG). Por isso o número de ações vem da B3.
- D&A não tem código padronizado: fica em `6.01.01.xx` com descrições variadas ("Depreciação e Amortização",
  "Depreciação, amortização e exaustão"…); ~10% das empresas não a informam (ex.: DFC método direto).
- FCA `valor_mobiliario`: `Codigo_Negociacao` ↔ `CNPJ_Companhia`, `Valor_Mobiliario` (Ações Ordinárias /
  Preferenciais / Units), `Composicao_BDR_Unit` ("1 ON / 2 PN").
- `cad_cia_aberta.csv`: `SETOR_ATIV`, `SIT` (ATIVO…), uma linha por mercado.
