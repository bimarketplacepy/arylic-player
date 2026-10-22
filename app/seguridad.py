"""Protección de la API con un token compartido (header X-Token)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status


def verificar_token(request: Request, x_token: Annotated[str | None, Header()] = None) -> None:
    esperado: str = request.app.state.config.servidor.token
    # compare_digest evita filtrar el token midiendo cuánto tarda la comparación.
    if not x_token or not secrets.compare_digest(x_token.encode(), esperado.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o ausente (header X-Token)")
