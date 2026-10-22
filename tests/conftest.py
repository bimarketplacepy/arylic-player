"""Fixtures compartidas: servidor y simulador conectados en memoria, sin red ni puertos."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.arylic import ClienteArylic
from app.config import Config, config_desde_dict
from app.main import crear_app
from simulador.arylic_falso import EstadoSimulado, crear_simulador

TOKEN = "token-de-prueba"

# Nombres al estilo de las descargas de Suno, con caracteres que hay que codificar.
CANCIONES = ["b canción.mp3", "A Tema (1).mp3", "c ñandú #2 & más.MP3"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def carpeta_musica(tmp_path: Path) -> Path:
    carpeta = tmp_path / "musica"
    carpeta.mkdir()
    for nombre in CANCIONES:
        (carpeta / nombre).write_bytes(b"ID3" + nombre.encode())
    (carpeta / "notas.txt").write_text("no es música")
    return carpeta


def hacer_config(carpeta: Path, **reproduccion: object) -> Config:
    return config_desde_dict(
        {
            "arylic": {"ip": "arylic.test", "protocolo": "http"},
            "servidor": {"carpeta_musica": str(carpeta), "token": TOKEN},
            "reproduccion": reproduccion,
        }
    )


@pytest.fixture
def config(carpeta_musica: Path) -> Config:
    return hacer_config(carpeta_musica)


def conectar(config: Config) -> tuple[TestClient, EstadoSimulado]:
    """Servidor cuyo cliente habla con el simulador, y simulador que descarga del servidor."""
    simulador = crear_simulador()
    cliente = ClienteArylic(config.arylic.ip, "http", transport=httpx.ASGITransport(app=simulador))
    app = crear_app(config, cliente)
    simulador.state.transporte_descarga = httpx.ASGITransport(app=app)
    return TestClient(app, headers={"X-Token": TOKEN}), simulador.state.sim


@pytest.fixture
def entorno(config: Config) -> Iterator[tuple[TestClient, EstadoSimulado]]:
    http, sim = conectar(config)
    with http:
        yield http, sim
