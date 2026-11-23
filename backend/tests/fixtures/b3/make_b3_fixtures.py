"""Generates SYNTHETIC B3 'Área do Investidor' exports with the exact layout of the real files
(sheet names, headers, cell types, number formats, '-' placeholders, newest-first order).
All tickers/values describe a fictitious portfolio — never put real user data here.

Run: uv run python tests/fixtures/b3/make_b3_fixtures.py
"""

import re
import zipfile
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent
MONEY_FMT = "_-R$* #,##0.00######_-;-R$* #,##0.00######_-;_ -;_-@_-"
DATE_FMT = "dd/MM/yyyy"
BROKER_A = "CORRETORA A DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA"
BROKER_B = "CORRETORA B CCTVM S/A"
BROKER_B_DOT = "CORRETORA B CCTVM S/A."  # the same broker appears with and without the trailing dot
BROKER_C = "CORRETORA C CTVM SA"
BROKER_D = "CORRETORA D DE TITULOS E VALORES MOBILIARIOS S/A"
BANK = "BANCO A S/A"

NEG_HEADER = [
    "Data do Negócio",
    "Tipo de Movimentação",
    "Mercado",
    "Prazo/Vencimento",
    "Instituição",
    "Código de Negociação",
    "Quantidade",
    "Preço",
    "Valor",
]
# (date, side, market, due, broker, code, qty, price, value) — newest first, like the real export
NEGOTIATION = [
    ("11/08/2025", "Venda", "Mercado Fracionário", "11/08/2025", BROKER_A, "WEGE3F", 20, 55, 1100),
    ("10/07/2025", "Compra", "Mercado à Vista", "-", BROKER_B, "WEGE3", 100, 52.3, 5230),
    ("10/12/2024", "Compra", "Futuro", "02/01/2025", BROKER_A, "WDOF25", 1, 6077, 60770),
    ("10/12/2024", "Venda", "Futuro", "02/01/2025", BROKER_A, "WDOF25", 1, 6070, 60700),
    ("04/12/2024", "Compra", "Futuro", "18/12/2024", BROKER_A, "WINZ24", 1, 126635, 25327),
    ("28/08/2024", "Venda", "Mercado Fracionário", "-", BROKER_A, "MGLU3F", 12, 13.25, 159),
    ("20/03/2024", "Compra", "Mercado Fracionário", "-", BROKER_A, "BBAS3F", 5, 55.7, 278.5),
    # Two identical trades on the same day are legitimate and must both be imported
    ("01/06/2023", "Compra", "Mercado Fracionário", "-", BROKER_A, "TAEE4F", 10, 11.2, 112),
    ("01/06/2023", "Compra", "Mercado Fracionário", "-", BROKER_A, "TAEE4F", 10, 11.2, 112),
    ("15/03/2023", "Compra", "Mercado Fracionário", "-", BROKER_A, "MGLU3F", 90, 3.1, 279),
    ("15/03/2023", "Compra", "Mercado Fracionário", "-", BROKER_A, "MGLU3F", 30, 3, 90),
    ("10/02/2023", "Compra", "Mercado Fracionário", "-", BROKER_A, "ITSA4F", 50, 8.5, 425),
]

MOV_HEADER = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]
WEGE = "WEGE3 - WEG S.A."
ITSA = "ITSA4 - ITAUSA S/A"
BBAS = "BBAS3 - BANCO DO BRASIL S/A"
MGLU = "MGLU3 - MAGAZINE LUIZA S/A"
TAEE = "TAEE4 - TRANSMISSORA ALIANCA DE ENERGIA ELETRICA S/A"
# (in/out, date, kind, product, broker, qty, unit price, value) — newest first
MOVEMENT = [
    ("Credito", "01/10/2025", "Juros Sobre Capital Próprio", ITSA, BROKER_B_DOT, 52, 0.024, 1.03),
    ("Credito", "11/09/2025", "Rendimento", BBAS, BROKER_B_DOT, 10, 0.003, 0.03),
    ("Credito", "11/09/2025", "Juros Sobre Capital Próprio", BBAS, BROKER_B_DOT, 10, 0.102, 0.84),
    ("Debito", "13/08/2025", "Transferência - Liquidação", WEGE, BROKER_A, 20, 55, 1100),
    ("Debito", "13/08/2025", "Transferência", ITSA, BROKER_D, 52, "-", "-"),
    ("Credito", "13/08/2025", "Transferência", ITSA, BROKER_B_DOT, 52, "-", "-"),
    ("Debito", "13/08/2025", "Juros Sobre Capital Próprio - Transferido", ITSA, BROKER_D, 52, 0.11, 4.72),
    (
        "Credito",
        "13/08/2025",
        "Juros Sobre Capital Próprio - Transferido",
        ITSA,
        BROKER_B_DOT,
        52,
        0.11,
        4.72,
    ),
    ("Debito", "13/08/2025", "Dividendo - Transferido", TAEE, BROKER_D, 20, 0.5, 10),
    ("Credito", "13/08/2025", "Dividendo - Transferido", TAEE, BROKER_B_DOT, 20, 0.5, 10),
    ("Credito", "13/08/2025", "Atualização", BBAS, BROKER_A, 10, "-", "-"),
    ("Credito", "14/07/2025", "Transferência - Liquidação", WEGE, BROKER_B, 100, 52.3, 5230),
    (
        "Debito",
        "11/07/2025",
        "RESGATE ANTECIPADO/",
        "CDB - CDBX0000TEST - BANCO A S/A",
        BANK,
        1000,
        0.01067034,
        10.67,
    ),
    ("Credito", "11/09/2025", "Compra", "Futuro - WDOV25", BROKER_C, 0, 5424, "-"),
    ("Debito", "11/09/2025", "Venda", "Futuro - WDOV25", BROKER_C, 0, 5418, "-"),
    ("Credito", "08/09/2025", "Compra", "Futuro - WINV25", BROKER_C, 0, 143610, "-"),
    ("Debito", "08/09/2025", "Venda", "Futuro - WINV25", BROKER_C, 0, 143810, "-"),
    ("Credito", "25/02/2025", "Leilão de Fração", ITSA, BROKER_A, 0.5, 10.031, 5.01),
    ("Debito", "30/01/2025", "Fração em Ativos", ITSA, BROKER_A, 0.5, "-", "-"),
    ("Credito", "04/12/2024", "Bonificação em Ativos", ITSA, BROKER_A, 2.5, "-", "-"),
    ("Credito", "30/08/2024", "Dividendo", TAEE, BROKER_A, 20, 0.5, 10),
    ("Credito", "30/08/2024", "Transferência - Liquidação", MGLU, BROKER_A, 12, 13.25, 159),
    ("Credito", "28/05/2024", "Grupamento", MGLU, BROKER_A, 12, "-", "-"),
    ("Credito", "17/04/2024", "Desdobro", BBAS, BROKER_A, 5, "-", "-"),
    ("Credito", "22/03/2024", "Transferência - Liquidação", BBAS, BROKER_A, 5, 55.7, 278.5),
    (
        "Debito",
        "01/03/2024",
        "Direitos de Subscrição - Não Exercido",
        "MGLU1 - MAGAZINE LUIZA S/A",
        BROKER_A,
        0,
        "-",
        "-",
    ),
    ("Credito", "29/02/2024", "Cessão de Direitos", "MGLU1 - MAGAZINE LUIZA S/A", BROKER_A, 11, "-", "-"),
    (
        "Debito",
        "29/02/2024",
        "Cessão de Direitos - Solicitada",
        "MGLU1 - MAGAZINE LUIZA S/A",
        BROKER_A,
        11,
        "-",
        "-",
    ),
    ("Credito", "02/02/2024", "Direito de Subscrição", "MGLU1 - MAGAZINE LUIZA S/A", BROKER_A, 11, "-", "-"),
    ("Credito", "10/01/2024", "Atualização", MGLU, BROKER_A, 120, "-", "-"),
    ("Credito", "20/12/2023", "Juros Sobre Capital Próprio", ITSA, BROKER_A, 50, 0.2, 8.5),
    ("Credito", "05/06/2023", "Transferência - Liquidação", TAEE, BROKER_A, 20, 11.2, 224),
    ("Credito", "17/03/2023", "Transferência - Liquidação", MGLU, BROKER_A, 120, 3.075, 369),
    ("Credito", "14/02/2023", "Transferência - Liquidação", ITSA, BROKER_A, 50, 8.5, 425),
]


def _write(
    path: Path, sheet: str, header: list[str], rows: list[tuple], date_cols: set[int], money_cols: set[int]
):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header)
    for row in rows:
        ws.append(list(row))
    for r in range(2, ws.max_row + 1):
        for c in date_cols:
            ws.cell(r, c).number_format = DATE_FMT
        for c in money_cols:
            ws.cell(r, c).number_format = MONEY_FMT
    wb.save(path)
    _fake_b3_dimension(path)


def _fake_b3_dimension(path: Path) -> None:
    """Real B3 files declare <dimension ref="A1"/> regardless of size; reproduce that quirk."""
    with zipfile.ZipFile(path) as src:
        items = [(info, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info, data in items:
            if info.filename.startswith("xl/worksheets/"):
                data = re.sub(rb'<dimension ref="[^"]*"/>', b'<dimension ref="A1"/>', data)
            dst.writestr(info, data)


def main() -> None:
    _write(HERE / "negociacao_sample.xlsx", "Negociação", NEG_HEADER, NEGOTIATION, {1, 4}, {8, 9})
    _write(HERE / "movimentacao_sample.xlsx", "Movimentação", MOV_HEADER, MOVEMENT, {2}, {7, 8})


if __name__ == "__main__":
    main()
