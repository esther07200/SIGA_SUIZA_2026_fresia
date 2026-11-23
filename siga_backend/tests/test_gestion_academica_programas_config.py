import importlib.util
from pathlib import Path


def test_railway_programas_url_takes_precedence(monkeypatch):
    monkeypatch.setenv("SIGA_MODULE_PROGRAMAS_ESTUDIO_URL", "http://127.0.0.1:8005")
    monkeypatch.setenv("PROGRAMAS_MODULE_URL", "http://mod-programas-estudio:8005")

    config_path = (
        Path(__file__).resolve().parents[1]
        / "modules"
        / "mod-gestion-academica"
        / "config.py"
    )
    spec = importlib.util.spec_from_file_location("gestion_academica_config_test", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    settings = config_module.EnrollmentSettings()

    assert settings.programas_url == "http://127.0.0.1:8005"
