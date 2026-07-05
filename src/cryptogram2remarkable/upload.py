"""Stap 5: upload de PDF naar de reMarkable via rmapi.

Vereist eenmalige setup buiten dit script: installeer rmapi en registreer het
apparaat (`rmapi` vraagt een one-time code van my.remarkable.com; het device-token
komt in de rmapi-config te staan — niet in deze repo of logs).

Idempotent: als een bestand met dezelfde naam al in de doelmap staat, slaan we de
upload over (een dubbele run stuurt dus niet twee keer dezelfde pagina).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import UploadError


def _rmapi() -> str:
    exe = shutil.which("rmapi")
    if not exe:
        raise UploadError("rmapi niet gevonden op PATH. Installeer en registreer rmapi eerst.")
    return exe


def _env(rmapi_config: str) -> dict:
    env = os.environ.copy()
    if rmapi_config:
        env["RMAPI_CONFIG"] = rmapi_config
    return env


def _run(rmapi_config: str, *args: str) -> subprocess.CompletedProcess:
    try:
        # stdin dicht: als rmapi niet geregistreerd is, faalt het snel i.p.v. te
        # blijven wachten op de interactieve one-time code.
        return subprocess.run(
            [_rmapi(), *args],
            capture_output=True, text=True, timeout=120,
            stdin=subprocess.DEVNULL, env=_env(rmapi_config),
        )
    except subprocess.TimeoutExpired as e:
        raise UploadError(
            f"rmapi '{' '.join(args)}' liep vast (timeout). Waarschijnlijk is rmapi "
            f"niet geregistreerd op de gebruikte config. Controleer: "
            f"RMAPI_CONFIG={rmapi_config or '(standaard)'} en draai 'rmapi' handmatig."
        ) from e


def _remote_has(rmapi_config: str, folder: str, filename_stem: str) -> bool:
    res = _run(rmapi_config, "ls", folder)
    if res.returncode != 0:
        return False  # map bestaat (nog) niet
    return any(line.strip().endswith(filename_stem) for line in res.stdout.splitlines())


def upload(pdf_path: str | Path, folder: str, rmapi_config: str = "") -> bool:
    """Upload pdf naar `folder`. Retourneert True bij upload, False bij skip (al aanwezig)."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise UploadError(f"PDF bestaat niet: {pdf_path}")

    stem = pdf_path.stem  # rmapi toont bestanden zonder .pdf-extensie
    if _remote_has(rmapi_config, folder, stem):
        return False

    _run(rmapi_config, "mkdir", folder)  # idempotent; negeer 'bestaat al'
    res = _run(rmapi_config, "put", str(pdf_path), folder)
    if res.returncode != 0:
        raise UploadError(f"rmapi put faalde: {res.stderr.strip() or res.stdout.strip()}")
    return True
