import pytest
from parsel import Selector
from tsensor.core.data_stream import DataStream


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


def test_api_status_returns_connection_state(client, mocker):
    """Verifica se a rota /api/status retorna o estado global da aplicação."""
    mock_status = {
        "connected": True,
        "port": "/dev/ttyUSB0",
        "mcu": "esp32",
        "error": None,
    }
    mocker.patch("tsensor.routes.api.app_status", mock_status)

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == mock_status


def test_api_config_updates_values_and_calls_save(client, mocker):
    """Verifica se a rota /api/config processa o POST e chama save_config."""
    # Mock do config global e da função de salvar
    mock_config = {
        "hardware": {"port": "/old/port", "mcu": "arduino_uno", "baudrate": 9600},
        "sensor": {"adc_max": 1023, "v_ref": 1.1},
    }
    mocker.patch("tsensor.routes.api.config", mock_config)
    mock_save = mocker.patch("tsensor.routes.api.save_config")

    payload = {"port": "/dev/ttyACM0", "mcu": "esp32", "baudrate": "115200"}

    response = client.post("/api/config", json=payload)

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    # Verifica se o dicionário interno foi atualizado
    assert mock_config["hardware"]["port"] == "/dev/ttyACM0"
    assert mock_config["hardware"]["mcu"] == "esp32"
    assert mock_config["hardware"]["baudrate"] == 115200

    # Garante que a persistência foi chamada
    mock_save.assert_called_once_with(mock_config)
