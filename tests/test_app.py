import pytest
from tsensor.app import app
from tsensor.core.data_stream import DataStream


@pytest.fixture
def client():
    """Configura o cliente Flask base para os testes."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_route_index_status_code(client):
    """Verifica se a página principal carrega."""
    response = client.get("/")
    assert response.status_code == 200


def test_api_stats_returns_html_partial_with_mocked_values(client, mocker):
    """
    Testa exclusivamente a rota /api/stats.
    Injeta um DataStream mockado localmente e valida a saída HTML.
    """
    # 1. Setup local do Mock
    test_stream = DataStream(total_samples=5)
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        test_stream.add(val)

    # 2. Patch usando o mocker do pytest
    # O patch deve ser feito onde o objeto é CONSUMIDO pelas rotas
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    # 3. Execução
    response = client.get("/api/stats")

    # 4. Asserts
    assert response.status_code == 200
    html_data = response.data.decode("utf-8")

    assert "Média" in html_data
    assert "Amostras" in html_data
    assert "5" in html_data  # n (Amostras)
    assert "30.0000" in html_data  # Média (x̄)
    assert "10.00" in html_data  # Mínimo
    assert "50.00" in html_data  # Máximo


def test_api_histogram_returns_json_with_mocked_values(client, mocker):
    """
    Testa exclusivamente a rota /api/histogram.
    Injeta um DataStream mockado localmente e valida a estrutura JSON.
    """
    # 1. Setup local do Mock
    test_stream = DataStream(total_samples=5)
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        test_stream.add(val)

    # 2. Patch usando o mocker do pytest
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    # 3. Execução
    response = client.get("/api/histogram")

    # 4. Asserts
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "labels" in data
    assert "values" in data
    assert isinstance(data["labels"], list)
    assert isinstance(data["values"], list)
    assert sum(data["values"]) == 5  # Total de amostras
