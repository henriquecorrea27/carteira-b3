# Fixtures — eventos corporativos da B3

Respostas **reais e públicas** (08/10/2026) do endpoint usado pelo pacote `rb3`:

`GET https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{base64}`
com `{"issuingCompany":"CMIG","language":"pt-br"}` em base64.

| Campo | Observado |
|---|---|
| `cashDividends` | só os **últimos ~12 meses**; `label` ∈ `DIVIDENDO`, `JRS CAP PROPRIO`, `RENDIMENTO`; `lastDatePrior` = data-com; `rate` = valor por ação (`"0,47156696000"`); parcelas aparecem como linhas separadas, uma por `paymentDate` |
| `stockDividends` | histórico longo (mas incompleto: bonificações da ITSA de 2023/2024 não aparecem); `DESDOBRAMENTO` e `BONIFICACAO` com `factor` = **% de ações novas** (100 = 1:2); `GRUPAMENTO` com `factor` = **razão nova/antiga** (0,1 = 10:1); números às vezes com ruído (`30,00000002726`) |
| `subscriptions` | direitos de subscrição (informativo) |
| Custo atribuído da bonificação | **não vem** → bonificação fica pendente de custo |
| Ticker | não vem; derivado do ISIN: `BR` + emissor + `ACNOR`→3, `ACNPR`→4, `ACNPA`→5, `ACNPB`→6, `CDAM`→11 (unit), `CTF`→11 (FII) |
| Cobertura | ações e FIIs (HGLG) cobertos; ETF (BOVA) vem vazio |
| Empresa deslistada | (ex.: MRFG após fusão) a resposta não é JSON |
