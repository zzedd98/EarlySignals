"""
Chargement des proxies depuis un fichier (format host:port:user:password).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


def proxy_line_to_url(line: str) -> str:
    """
    Convertit une ligne host:port:user:password en URL HTTP proxy.

    Le mot de passe peut contenir des ':' (tout après le 3e ':' est le password).
    """
    raw = line.strip()
    if not raw or raw.startswith("#"):
        raise ValueError("ligne vide ou commentaire")

    parts = raw.split(":")
    if len(parts) < 4:
        raise ValueError(
            f"format invalide (attendu host:port:user:password): {raw[:80]!r}"
        )

    host = parts[0].strip()
    port = parts[1].strip()
    user = parts[2].strip()
    password = ":".join(parts[3:]).strip()

    if not host or not port or not user:
        raise ValueError(f"host/port/user manquant: {raw[:80]!r}")

    user_q = quote(user, safe="")
    pass_q = quote(password, safe="")
    return f"http://{user_q}:{pass_q}@{host}:{port}"


def load_proxies_from_file(path: str | Path) -> list[str]:
    """Charge les URLs proxy depuis un fichier texte (une ligne par proxy)."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Fichier proxy introuvable: {file_path}")

    proxies: list[str] = []
    for line_no, line in enumerate(
        file_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            proxies.append(proxy_line_to_url(stripped))
        except ValueError as e:
            raise ValueError(f"{file_path}:{line_no}: {e}") from e

    if not proxies:
        raise ValueError(f"Aucun proxy valide dans {file_path}")
    return proxies
