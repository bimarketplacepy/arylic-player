from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi.testclient import TestClient

from app.arylic import ClienteArylic
from app.main import crear_app
from simulador.arylic_falso import EstadoSimulado
from tests.conftest import TOKEN, conectar, hacer_config

Entorno = tuple[TestClient, EstadoSimulado]


def test_salud_y_lista_sin_token(entorno: Entorno) -> None:
    http, _ = entorno
    sin_token = {"X-Token": ""}
    assert http.get("/salud", headers=sin_token).json() == {"ok": True}
    respuesta = http.get("/lista.m3u", headers=sin_token)
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("audio/x-mpegurl")
    lineas = respuesta.text.splitlines()
    assert lineas[0] == "#EXTM3U"
    assert len(lineas) == 1 + 2 * 3
    assert lineas[2].startswith("http://10.51.85.12:8080/musica/")


def test_cada_url_de_la_lista_descarga_el_mp3(entorno: Entorno, carpeta_musica: Path) -> None:
    http, _ = entorno
    urls = [l for l in http.get("/lista.m3u").text.splitlines() if not l.startswith("#")]
    for url in urls:
        respuesta = http.get(urlsplit(url).path, headers={"X-Token": ""})
        assert respuesta.status_code == 200, url
        assert respuesta.headers["content-type"] == "audio/mpeg"
        assert respuesta.content.startswith(b"ID3")


def test_musica_no_permite_salir_de_la_carpeta(entorno: Entorno) -> None:
    http, _ = entorno
    assert http.get("/musica/..%2F..%2Fconfig.toml").status_code == 404


def test_api_exige_token(entorno: Entorno) -> None:
    http, _ = entorno
    assert http.get("/api/estado", headers={"X-Token": ""}).status_code == 401
    assert http.get("/api/estado", headers={"X-Token": "otro"}).status_code == 401
    assert http.post("/api/pausa", headers={"X-Token": "otro"}).status_code == 401


def test_estado_inicial(entorno: Entorno) -> None:
    http, _ = entorno
    datos = http.get("/api/estado").json()
    assert datos["conectado"] is True
    assert datos["status"] == "none"
    assert datos["volumen"] == 74


def test_iniciar_album_carga_la_lista_y_fija_repeticion(entorno: Entorno) -> None:
    http, sim = entorno
    respuesta = http.post("/api/album/iniciar")
    assert respuesta.json() == {"ok": True, "canciones": 3, "modo": "secuencial"}
    # El simulador descargó la lista desde el servidor de verdad.
    assert [titulo for titulo, _ in sim.pistas] == ["A Tema (1)", "b canción", "c ñandú #2 & más"]
    assert sim.loop == 0  # el parlante venía en 4 (sin repetición)
    assert sim.vol == 74  # sin volumen pedido, no se toca

    datos = http.get("/api/estado").json()
    assert datos["status"] == "play"
    assert datos["titulo"] == "A Tema (1)"
    assert (datos["pista_actual"], datos["total_pistas"]) == (1, 3)


def test_iniciar_album_con_volumen_y_modo_aleatorio(carpeta_musica: Path) -> None:
    http, sim = conectar(hacer_config(carpeta_musica, modo="aleatorio"))
    with http:
        assert http.post("/api/album/iniciar", json={"volumen": 30}).status_code == 200
    assert (sim.loop, sim.vol) == (2, 30)


def test_iniciar_album_sin_canciones(tmp_path: Path) -> None:
    http, _ = conectar(hacer_config(tmp_path / "vacia"))
    with http:
        respuesta = http.post("/api/album/iniciar")
    assert respuesta.status_code == 409


def test_pausa_reanudar_siguiente_anterior(entorno: Entorno) -> None:
    http, sim = entorno
    http.post("/api/album/iniciar")
    assert http.post("/api/pausa").json() == {"ok": True}
    assert sim.status == "pause"
    http.post("/api/reanudar")
    assert sim.status == "play"
    http.post("/api/siguiente")
    assert sim.indice == 1
    http.post("/api/anterior")
    http.post("/api/anterior")
    assert sim.indice == 2  # desde la primera, "anterior" va a la última


def test_volumen(entorno: Entorno) -> None:
    http, sim = entorno
    assert http.post("/api/volumen", json={"valor": 55}).json() == {"ok": True, "volumen": 55}
    assert sim.vol == 55
    assert http.post("/api/volumen", json={"valor": 101}).status_code == 422
    assert http.post("/api/volumen", json={"valor": -1}).status_code == 422


def test_parlante_caido_da_503_y_no_tumba_el_servidor(config) -> None:
    def caido(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta al host", request=request)

    cliente = ClienteArylic("10.51.85.20", "auto", transport=httpx.MockTransport(caido))
    with TestClient(crear_app(config, cliente), headers={"X-Token": TOKEN}) as http:
        for ruta in ("/api/pausa", "/api/album/iniciar", "/api/siguiente"):
            respuesta = http.post(ruta)
            assert respuesta.status_code == 503
            assert respuesta.json()["conectado"] is False
        assert http.get("/api/estado").status_code == 503
        assert http.get("/salud").status_code == 200
