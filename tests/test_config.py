from pathlib import Path

import pytest

from app.config import ErrorConfig, cargar_config, config_desde_dict


def test_valores_por_defecto_son_los_del_local(tmp_path: Path) -> None:
    config = cargar_config(tmp_path / "no-existe.toml")
    assert config.arylic.ip == "10.51.85.20"
    assert config.servidor.url_base == "http://10.51.85.12:8080"
    assert config.reproduccion.loopmode == 0


def test_acepta_bom_y_resuelve_carpeta_relativa(tmp_path: Path) -> None:
    ruta = tmp_path / "config.toml"
    ruta.write_text('[servidor]\ncarpeta_musica = "canciones"\n[reproduccion]\nmodo = "Aleatorio"\n', encoding="utf-8-sig")
    config = cargar_config(ruta)
    assert config.servidor.carpeta_musica == (tmp_path / "canciones").resolve()
    assert config.reproduccion.loopmode == 2


def test_toml_mal_escrito(tmp_path: Path) -> None:
    ruta = tmp_path / "config.toml"
    ruta.write_text("[servidor\npuerto = 1\n", encoding="utf-8")
    with pytest.raises(ErrorConfig):
        cargar_config(ruta)


@pytest.mark.parametrize(
    "datos",
    [
        {"arylic": {"protocolo": "ftp"}},
        {"servidor": {"puerto": 0}},
        {"servidor": {"puerto": "abc"}},
        {"servidor": {"token": "  "}},
        {"reproduccion": {"volumen_inicial": 150}},
        {"reproduccion": {"modo": "una"}},
    ],
)
def test_valores_invalidos(datos: dict) -> None:
    with pytest.raises(ErrorConfig):
        config_desde_dict(datos)
