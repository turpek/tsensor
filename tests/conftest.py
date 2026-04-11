import pytest
from tsensor.app import app


@pytest.fixture(autouse=True)
def disable_real_acquisition(mocker):
    """
    Mock global que impede o início de threads de hardware reais durante os testes.
    """
    # Mocka na origem do core e na rota que a utiliza
    mocker.patch("tsensor.core.acquisition.start_acquisition")
    return mocker.patch("tsensor.routes.api.start_acquisition")


@pytest.fixture
def client():
    """Configura o cliente Flask base para todos os testes do projeto."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
