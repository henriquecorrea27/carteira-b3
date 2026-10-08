"""Cuts REAL public CVM files (backend/data/cvm/raw, downloaded by the ingestion) down to a few
companies, keeping the exact layout. Public data only — no personal information.

Run: uv run python tests/fixtures/cvm/make_cvm_fixtures.py
"""

import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RAW = HERE.parents[2] / "data" / "cvm" / "raw"
OUT = HERE / "raw"
COMPANIES = {
    "17.155.730/0001-64",  # CEMIG — utility, consolidated
    "00.000.000/0001-91",  # Banco do Brasil — bank template
    "92.690.783/0001-09",  # Metalúrgica Gerdau — holding with large minority interest
}
FILES = [f"dfp_cia_aberta_{y}.zip" for y in range(2020, 2026)] + [
    "itr_cia_aberta_2025.zip",
    "itr_cia_aberta_2026.zip",
    "fca_cia_aberta_2026.zip",
]


def cut(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("CNPJ_CIA", "CNPJ_Companhia"):
        if col in df.columns:
            return df[df[col].isin(COMPANIES)]
    return df.iloc[0:0]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name in FILES:
        with (
            zipfile.ZipFile(RAW / name) as src,
            zipfile.ZipFile(OUT / name, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for member in src.namelist():
                if "parecer" in member or "DMPL" in member or "DVA" in member or "DRA" in member:
                    continue
                if name.startswith("fca") and "valor_mobiliario" not in member:
                    continue
                with src.open(member) as fh:
                    df = pd.read_csv(fh, sep=";", encoding="latin1", dtype=str)
                dst.writestr(member, cut(df).to_csv(sep=";", index=False).encode("latin1"))
    cad = pd.read_csv(RAW / "cad_cia_aberta.csv", sep=";", encoding="latin1", dtype=str)
    cut(cad).to_csv(OUT / "cad_cia_aberta.csv", sep=";", index=False, encoding="latin1")


if __name__ == "__main__":
    main()
