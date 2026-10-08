"""Downloads CVM open-data files into backend/data/cvm/raw (cache). A file is fetched again only when
the server copy is newer (Last-Modified) — CVM re-publishes yearly zips when companies refile."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from app.core.config import BACKEND_DIR

log = logging.getLogger(__name__)
BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
RAW_DIR = BACKEND_DIR / "data" / "cvm" / "raw"
DFP_YEARS = 6  # 5-year averages + the base year of the 5-year CAGR


@dataclass(frozen=True)
class RemoteFile:
    url: str
    name: str
    required: bool = True


def wanted_files(today: date) -> list[RemoteFile]:
    files = [
        RemoteFile(f"{BASE}/DOC/DFP/DADOS/dfp_cia_aberta_{y}.zip", f"dfp_cia_aberta_{y}.zip", y < today.year)
        for y in range(today.year - DFP_YEARS, today.year + 1)
    ]
    files += [
        RemoteFile(f"{BASE}/DOC/ITR/DADOS/itr_cia_aberta_{y}.zip", f"itr_cia_aberta_{y}.zip")
        for y in (today.year - 1, today.year)
    ]
    files += [
        RemoteFile(f"{BASE}/DOC/FCA/DADOS/fca_cia_aberta_{y}.zip", f"fca_cia_aberta_{y}.zip", False)
        for y in (today.year - 1, today.year)
    ]
    files.append(RemoteFile(f"{BASE}/CAD/DADOS/cad_cia_aberta.csv", "cad_cia_aberta.csv"))
    return files


def download_all(today: date, client: httpx.Client | None = None, raw_dir: Path = RAW_DIR) -> list[str]:
    """Returns the errors (empty when everything is up to date)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = client or httpx.Client(timeout=600, follow_redirects=True)
    errors = []
    for remote in wanted_files(today):
        target = raw_dir / remote.name
        try:
            head = client.head(remote.url)
            if head.status_code == 404:
                if remote.required:
                    errors.append(f"{remote.name}: não encontrado na CVM")
                continue
            modified = head.headers.get("last-modified")
            remote_time = parsedate_to_datetime(modified) if modified else None
            if target.exists() and remote_time is not None:
                local_time = datetime.fromtimestamp(target.stat().st_mtime, UTC)
                if local_time >= remote_time:
                    continue
            log.info("downloading %s", remote.url)
            tmp = target.with_suffix(target.suffix + ".part")
            with client.stream("GET", remote.url) as response:
                response.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in response.iter_bytes():
                        fh.write(chunk)
            tmp.replace(target)
        except httpx.HTTPError as err:
            errors.append(f"{remote.name}: {err}")
    return errors
