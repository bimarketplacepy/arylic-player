from pathlib import Path

from app.biblioteca import generar_m3u, listar_canciones, parsear_m3u, url_cancion


def test_lista_solo_mp3_ordenados_sin_importar_mayusculas(carpeta_musica: Path) -> None:
    assert listar_canciones(carpeta_musica) == ["A Tema (1).mp3", "b canción.mp3", "c ñandú #2 & más.MP3"]


def test_carpeta_inexistente_da_lista_vacia(tmp_path: Path) -> None:
    assert listar_canciones(tmp_path / "no-existe") == []


def test_url_codifica_caracteres_especiales() -> None:
    assert (
        url_cancion("http://10.51.85.12:8080", "c ñandú #2 & más.MP3")
        == "http://10.51.85.12:8080/musica/c%20%C3%B1and%C3%BA%20%232%20%26%20m%C3%A1s.MP3"
    )


def test_formato_m3u() -> None:
    texto = generar_m3u(["A Tema (1).mp3", "b canción.mp3"], "http://pc:8080")
    assert texto.splitlines() == [
        "#EXTM3U",
        "#EXTINF:-1,A Tema (1)",
        "http://pc:8080/musica/A%20Tema%20%281%29.mp3",
        "#EXTINF:-1,b canción",
        "http://pc:8080/musica/b%20canci%C3%B3n.mp3",
    ]


def test_m3u_vacia_tiene_cabecera() -> None:
    assert generar_m3u([], "http://pc:8080") == "#EXTM3U\n"


def test_parsear_m3u_con_urls_relativas() -> None:
    texto = "#EXTM3U\n#EXTINF:-1,Uno, con coma\nhttp://pc/musica/1.mp3\n\nmusica/2.mp3\n"
    assert parsear_m3u(texto, "http://pc:8080/lista.m3u") == [
        ("Uno, con coma", "http://pc/musica/1.mp3"),
        ("2.mp3", "http://pc:8080/musica/2.mp3"),
    ]


def test_parsear_lo_que_genera() -> None:
    texto = generar_m3u(["c ñandú #2 & más.MP3"], "http://pc:8080")
    assert parsear_m3u(texto, "http://pc:8080/lista.m3u") == [
        ("c ñandú #2 & más", "http://pc:8080/musica/c%20%C3%B1and%C3%BA%20%232%20%26%20m%C3%A1s.MP3")
    ]
