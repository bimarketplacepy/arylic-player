"""API de control del parlante (requiere header X-Token).

Si el parlante no responde, el manejador de main.py devuelve 503 con {"conectado": false}.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.arylic import ClienteArylic
from app.reproductor import SinCanciones, iniciar_album
from app.seguridad import verificar_token

router = APIRouter(prefix="/api", dependencies=[Depends(verificar_token)])

OK = {"ok": True}


class Volumen(BaseModel):
    valor: int = Field(ge=0, le=100)


class InicioAlbum(BaseModel):
    # Si no se indica, se respeta el volumen que tenga el parlante.
    volumen: int | None = Field(default=None, ge=0, le=100)


def _cliente(request: Request) -> ClienteArylic:
    return request.app.state.arylic


@router.get("/estado")
async def estado(request: Request) -> dict[str, Any]:
    cliente = _cliente(request)
    actual = await cliente.estado()
    return {"conectado": True, "base": cliente.base, **actual.a_dict()}


@router.post("/album/iniciar")
async def album_iniciar(request: Request, datos: InicioAlbum | None = None) -> dict[str, Any]:
    config = request.app.state.config
    try:
        cantidad = await iniciar_album(_cliente(request), config, datos.volumen if datos else None)
    except SinCanciones as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return {"ok": True, "canciones": cantidad, "modo": config.reproduccion.modo}


@router.post("/pausa")
async def pausa(request: Request) -> dict[str, bool]:
    await _cliente(request).pausa()
    return OK


@router.post("/reanudar")
async def reanudar(request: Request) -> dict[str, bool]:
    await _cliente(request).reanudar()
    return OK


@router.post("/siguiente")
async def siguiente(request: Request) -> dict[str, bool]:
    await _cliente(request).siguiente()
    return OK


@router.post("/anterior")
async def anterior(request: Request) -> dict[str, bool]:
    await _cliente(request).anterior()
    return OK


@router.post("/volumen")
async def volumen(request: Request, datos: Volumen) -> dict[str, Any]:
    await _cliente(request).volumen(datos.valor)
    return {"ok": True, "volumen": datos.valor}
