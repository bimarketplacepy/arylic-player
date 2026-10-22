"""Rutas sin token: las pide el parlante, que no sabe mandar headers.

/musica/* se monta como archivos estáticos en main.py (soporta pedidos por rangos).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.biblioteca import generar_m3u, listar_canciones

router = APIRouter()


@router.api_route("/lista.m3u", methods=["GET", "HEAD"])
def lista_m3u(request: Request) -> Response:
    """Lista generada en el momento, así refleja siempre lo que hay en la carpeta."""
    servidor = request.app.state.config.servidor
    contenido = generar_m3u(listar_canciones(servidor.carpeta_musica), servidor.url_base)
    return Response(
        contenido,
        media_type="audio/x-mpegurl; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/salud")
def salud() -> dict[str, bool]:
    """Para comprobar desde afuera que el servidor está vivo (no consulta al parlante)."""
    return {"ok": True}
