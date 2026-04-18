from tsensor.app import app
import pytest
from unittest import mock

# --- MOCK GLOBAL DE SEGURANÇA NO IMPORT TIME ---
# tsensor.extensions instancia o SheetsManager globalmente
from tsensor.core.sheets import SheetsManager
original_sheets_setup = SheetsManager.setup
SheetsManager.setup = mock.MagicMock()


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
