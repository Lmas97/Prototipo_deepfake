import pytest


def pytest_addoption(parser):
    parser.addoption("--run-model", action="store_true", default=False,
                     help="Ejecutar inferencia real; requiere descargar pesos y videos.")


def pytest_configure(config):
    config.addinivalue_line("markers", "model: inferencia real opcional sobre muestras públicas")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-model"):
        for item in items:
            if "model" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Usa --run-model para la inferencia real."))
