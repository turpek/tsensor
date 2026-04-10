import pytest
from parsel import Selector
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
    Injeta um DataStream mockado localmente e valida a saída HTML com Seletores CSS.
    """
    # 1. Setup local do Mock
    test_stream = DataStream(total_samples=5)
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        test_stream.add(val, timestamp="10:00:00:000")

    # 2. Patch usando o mocker do pytest
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    # 3. Execução
    response = client.get("/api/stats")

    # 4. Asserts com Parsel
    assert response.status_code == 200
    sel = Selector(response.data.decode("utf-8"))

    assert sel.css("#stats-n::text").get() == "5"
    assert sel.css("#stats-mean::text").get() == "30.0000"
    assert sel.css("#stats-min::text").get() == "10.00"
    assert sel.css("#stats-max::text").get() == "50.00"


def test_api_histogram_returns_json_with_mocked_values(client, mocker):
    """
    Testa exclusivamente a rota /api/histogram.
    Injeta um DataStream mockado localmente e valida a estrutura JSON.
    """
    # 1. Setup local do Mock
    test_stream = DataStream(total_samples=5)
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        test_stream.add(val, timestamp="10:00:00:000")

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


def test_api_stats_empty_stream(client, mocker):
    """Verifica o comportamento da rota de estatísticas com stream vazio."""
    test_stream = DataStream(total_samples=100)
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    response = client.get("/api/stats")
    assert response.status_code == 200
    sel = Selector(response.data.decode("utf-8"))

    # n deve ser 0
    assert sel.css("#stats-n::text").get() == "0"
    # Média e DP devem ser 0.0000
    assert sel.css("#stats-mean::text").get() == "0.0000"
    assert sel.css("#stats-std::text").get() == "0.0000"
    # Mínimo e Máximo devem ser 0.00
    assert sel.css("#stats-min::text").get() == "0.00"
    assert sel.css("#stats-max::text").get() == "0.00"


def test_api_histogram_empty_stream(client, mocker):
    """Verifica o comportamento da rota de histograma com stream vazio."""
    test_stream = DataStream(total_samples=100)
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    response = client.get("/api/histogram")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "labels" in data
    assert "values" in data
    # Com 0 amostras, a soma das frequências deve ser 0
    assert sum(data["values"]) == 0
