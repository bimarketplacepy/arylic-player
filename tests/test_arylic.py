import json

import httpx
import pytest

from app.arylic import (
    ArylicNoDisponible,
    ClienteArylic,
    EstadoReproductor,
    RespuestaInvalida,
    decodificar_hex,
    ms_a_mmss,
)

# Respuesta real del Arylic del local.
ESTADO_REAL = {
    "type": "0", "ch": "0", "mode": "10", "loop": "4", "eq": "0", "status": "none", "curpos": "0",
    "offset_pts": "0", "totlen": "0", "Title": "4D61726B657453756E6F",
    "Artist": "6D61726B6574706C616365", "Album": "4E6F7420537065636966696564",
    "alarmflag": "0", "plicount": "1", "plicurr": "1", "vol": "74", "mute": "0",
}


def test_decodificar_hex_respuesta_real() -> None:
    assert decodificar_hex("4D61726B657453756E6F") == "MarketSuno"
    assert decodificar_hex("6D61726B6574706C616365") == "marketplace"
    assert decodificar_hex("4E6F7420537065636966696564") == "Not Specified"


def test_decodificar_hex_utf8_vacio_e_invalido() -> None:
    assert decodificar_hex("Canción ñ".encode().hex()) == "Canción ñ"
    assert decodificar_hex("") == ""
    assert decodificar_hex(None) == ""
    assert decodificar_hex("no es hex") == "no es hex"


def test_ms_a_mmss() -> None:
    assert ms_a_mmss(0) == "00:00"
    assert ms_a_mmss(185_999) == "03:05"
    assert ms_a_mmss(3_725_000) == "62:05"
    assert ms_a_mmss(-5) == "00:00"


def test_estado_desde_respuesta_real() -> None:
    estado = EstadoReproductor.desde_json(ESTADO_REAL)
    assert estado.status == "none"
    assert estado.volumen == 74
    assert estado.silencio is False
    assert estado.titulo == "MarketSuno"
    assert estado.album == "Not Specified"
    assert (estado.pista_actual, estado.total_pistas, estado.loop, estado.modo_fuente) == (1, 1, 4, 10)
    datos = estado.a_dict()
    assert datos["posicion"] == "00:00"
    assert datos["fuente"] == "red (URL / lista)"


def test_estado_tolera_valores_raros() -> None:
    estado = EstadoReproductor.desde_json({"vol": "", "curpos": None, "status": "PLAY"})
    assert (estado.volumen, estado.posicion_ms, estado.status) == (0, 0, "play")


def _cliente(manejador, protocolo: str = "http") -> ClienteArylic:
    return ClienteArylic("10.51.85.20", protocolo, transport=httpx.MockTransport(manejador))


@pytest.mark.anyio
async def test_auto_detecta_https_si_http_falla() -> None:
    def manejador(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "http":
            raise httpx.ConnectError("rechazado", request=request)
        return httpx.Response(200, text=json.dumps(ESTADO_REAL))

    cliente = _cliente(manejador, "auto")
    estado = await cliente.estado()
    assert cliente.base == "https://10.51.85.20"
    assert estado.volumen == 74
    await cliente.cerrar()


@pytest.mark.anyio
async def test_auto_olvida_la_base_cuando_deja_de_responder() -> None:
    caido = False

    def manejador(request: httpx.Request) -> httpx.Response:
        if caido:
            raise httpx.ConnectTimeout("timeout", request=request)
        return httpx.Response(200, text=json.dumps(ESTADO_REAL))

    cliente = _cliente(manejador, "auto")
    await cliente.estado()
    assert cliente.base == "http://10.51.85.20"
    caido = True
    with pytest.raises(ArylicNoDisponible):
        await cliente.estado()
    assert cliente.base is None
    with pytest.raises(ArylicNoDisponible):  # tampoco detecta: sigue sin responder
        await cliente.estado()
    await cliente.cerrar()


@pytest.mark.anyio
async def test_comando_lleva_la_url_sin_codificar() -> None:
    pedidos: list[str] = []

    def manejador(request: httpx.Request) -> httpx.Response:
        pedidos.append(str(request.url))
        return httpx.Response(200, text="OK")

    cliente = _cliente(manejador)
    await cliente.reproducir_lista("http://10.51.85.12:8080/lista.m3u")
    await cliente.modo_bucle(0)
    assert pedidos == [
        "http://10.51.85.20/httpapi.asp?command=setPlayerCmd:m3u:play:http://10.51.85.12:8080/lista.m3u",
        "http://10.51.85.20/httpapi.asp?command=setPlayerCmd:loopmode:0",
    ]
    await cliente.cerrar()


@pytest.mark.anyio
async def test_error_http_y_respuesta_invalida() -> None:
    respuestas = iter([httpx.Response(500), httpx.Response(200, text="no es json")])
    cliente = _cliente(lambda request: next(respuestas))
    with pytest.raises(ArylicNoDisponible):
        await cliente.estado()
    with pytest.raises(RespuestaInvalida):
        await cliente.estado()
    await cliente.cerrar()


@pytest.mark.anyio
async def test_valida_rangos_antes_de_enviar() -> None:
    cliente = _cliente(lambda request: httpx.Response(200, text="OK"))
    with pytest.raises(ValueError):
        await cliente.volumen(101)
    with pytest.raises(ValueError):
        await cliente.modo_bucle(5)
    with pytest.raises(ValueError):
        await cliente.reproducir_indice(0)
    await cliente.cerrar()
