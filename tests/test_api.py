import pytest
from parsel import Selector
from tsensor.core.data_stream import DataStream
from tsensor.extensions import data_stream, buffer_stream, config
from tsensor.core.utils import MCU_PRESETS


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


def test_api_stats_returns_html_partial_with_mocked_values(client, mocker):
    """Testa a rota /api/stats com valores mockados."""
    test_stream = DataStream(total_samples=5)
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        test_stream.add(val, timestamp="10:00:00:000")

    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    response = client.get("/api/stats")

    assert response.status_code == 200
    sel = Selector(response.data.decode("utf-8"))

    assert sel.css("#stats-n::text").get() == "5"
    assert sel.css("#stats-mean::text").get() == "30.0000"
    assert sel.css("#stats-min::text").get() == "10.00"
    assert sel.css("#stats-max::text").get() == "50.00"


def test_api_stats_empty_stream(client, mocker):
    """Verifica o comportamento da rota de estatísticas com stream vazio."""
    test_stream = DataStream(total_samples=100)
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    response = client.get("/api/stats")
    assert response.status_code == 200
    sel = Selector(response.data.decode("utf-8"))

    assert sel.css("#stats-n::text").get() == "0"
    assert sel.css("#stats-mean::text").get() == "0.0000"
    assert sel.css("#stats-std::text").get() == "0.0000"
    assert sel.css("#stats-min::text").get() == "0.00"
    assert sel.css("#stats-max::text").get() == "0.00"


def test_api_histogram_returns_json_with_mocked_values(client, mocker):
    """Testa a rota /api/histogram com valores mockados."""
    test_stream = DataStream(total_samples=5)
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        test_stream.add(val, timestamp="10:00:00:000")

    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    response = client.get("/api/histogram")

    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "labels" in data
    assert "values" in data
    assert sum(data["values"]) == 5


def test_api_histogram_empty_stream(client, mocker):
    """Verifica o comportamento da rota de histograma com stream vazio."""
    test_stream = DataStream(total_samples=100)
    mocker.patch("tsensor.routes.api.data_stream", test_stream)

    response = client.get("/api/histogram")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert sum(data["values"]) == 0


def test_api_config_updates_values_and_calls_save(client, mocker):
    """Verifica se a rota /api/config processa o POST e chama save_config."""
    mock_config = {
        "hardware": {"port": "/old/port", "mcu": "arduino_uno", "baudrate": 9600},
        "sensor": {"adc_max": 1023, "v_ref": 1.1},
        "acquisition": {"total_samples": 1000},
        "presentation": {"update_interval_ms": 500, "decimal_places": 2},
    }
    mocker.patch("tsensor.routes.api.config", mock_config)
    mock_save = mocker.patch("tsensor.routes.api.save_config")

    payload = {"port": "/dev/ttyACM0", "mcu": "esp32", "baudrate": "115200"}

    response = client.post("/api/config", json=payload)

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    assert mock_config["hardware"]["port"] == "/dev/ttyACM0"
    assert mock_config["hardware"]["mcu"] == "esp32"
    assert mock_config["hardware"]["baudrate"] == 115200

    mock_save.assert_called_once_with(mock_config)


def test_api_config_saves_and_applies_presets(mocker, client):
    """Valida se a rota /api/config aplica presets de hardware ao trocar MCU."""
    mock_save = mocker.patch("tsensor.routes.api.save_config")

    # Mock do config atual para garantir transição
    mock_config = {
        "hardware": {"port": "/dev/ttyUSB0", "mcu": "arduino_uno", "baudrate": 9600},
        "sensor": {"adc_max": 1023, "v_ref": 1.1},
        "acquisition": {"total_samples": 1000},
        "presentation": {"update_interval_ms": 500, "decimal_places": 2},
    }
    mocker.patch("tsensor.routes.api.config", mock_config)

    payload = {"port": "/dev/ttyUSB1", "mcu": "esp32", "baudrate": "115200"}

    response = client.post("/api/config", json=payload)

    assert response.status_code == 200
    assert response.json["success"] is True

    args, _ = mock_save.call_args
    saved_config = args[0]

    assert saved_config["hardware"]["mcu"] == "esp32"
    assert saved_config["sensor"]["adc_max"] == MCU_PRESETS["esp32"]["adc_max"]
    assert saved_config["sensor"]["v_ref"] == MCU_PRESETS["esp32"]["v_ref"]


def test_api_restart_clears_data_and_restarts_acquisition(client, mocker):
    """Verifica se /api/restart para a aquisição, limpa dados com novo tamanho e reinicia."""
    # Mock do clear para capturar argumentos
    mock_data_clear = mocker.patch.object(data_stream, "clear")
    mock_buffer_clear = mocker.patch.object(buffer_stream, "clear")

    mocker.patch("tsensor.routes.api.stop_acquisition")
    mocker.patch("tsensor.routes.api.start_acquisition")

    response = client.post("/api/restart")

    assert response.status_code == 200
    assert response.json["success"] is True

    # Verifica se o clear foi chamado com os valores da config
    mock_data_clear.assert_called_once_with(
        total_samples=config["acquisition"]["total_samples"])
    mock_buffer_clear.assert_called_once_with(
        total_samples=config["acquisition"]["buffer_samples"])


@pytest.fixture
def mock_export_config(mocker):
    """Fixture para mockar a configuração de exportação."""
    mock_cfg = {
        "exporter": {
            "google_drive": {
                "credentials_file": "c.json",
                "token_file": "t.json",
                "scopes": ["s"],
                "file_name": "f"
            }
        }
    }
    mocker.patch("tsensor.routes.api.config", mock_cfg)
    return mock_cfg


def test_api_export_success(client, mocker, mock_export_config):
    """Verifica se /api/export chama o exportador CSV corretamente com sucesso."""
    mock_stream = mocker.patch("tsensor.routes.api.data_stream")
    type(mock_stream).sample = mocker.PropertyMock(
        return_value=[("10:00:01", 25.0)])

    mock_exporter_cls = mocker.patch("tsensor.routes.api.CSVExporter")
    mock_exporter_inst = mock_exporter_cls.return_value
    mock_exporter_inst.export.return_value = True

    response = client.post("/api/export")

    assert response.status_code == 200
    assert response.json["success"] is True
    assert "Dados salvos" in response.json["message"]
    mock_exporter_inst.setup.assert_called_once()
    mock_exporter_inst.export.assert_called_once()


def test_api_export_no_data_fails(client, mocker, mock_export_config):
    """Verifica se /api/export falha quando não há dados no stream."""
    mock_stream = mocker.patch("tsensor.routes.api.data_stream")
    type(mock_stream).sample = mocker.PropertyMock(return_value=[])

    # Mock do exportador para evitar execução de código real
    mocker.patch("tsensor.routes.api.CSVExporter")

    response = client.post("/api/export")

    assert response.status_code == 400
    assert "Não há dados" in response.json["error"]


def test_api_export_service_failure(client, mocker, mock_export_config):
    """Verifica se /api/export retorna erro quando o exportador CSV falha."""
    mock_stream = mocker.patch("tsensor.routes.api.data_stream")
    type(mock_stream).sample = mocker.PropertyMock(
        return_value=[("10:00:01", 25.0)])

    mock_exporter_cls = mocker.patch("tsensor.routes.api.CSVExporter")
    mock_exporter_inst = mock_exporter_cls.return_value
    mock_exporter_inst.export.return_value = False

    response = client.post("/api/export")

    assert response.status_code == 500
    assert "Falha ao salvar" in response.json["error"]


def test_api_residual_analysis_success(client, mocker):
    """Testa se a rota /api/residual-analysis retorna histograma e estatísticas dos resíduos."""
    # Mock do stream com uma tendência linear clara [10, 11, 12, 13, 14]
    # Resíduos esperados aproximados de 0 após detrend
    test_data = [("10:00:01", 10.0), ("10:00:02", 11.0), ("10:00:03", 12.0),
                 ("10:00:04", 13.0), ("10:00:05", 14.0)]

    mock_stream = mocker.patch("tsensor.routes.api.data_stream")
    type(mock_stream).data = mocker.PropertyMock(
        return_value=[d[1] for d in test_data])

    response = client.get("/api/residual-analysis")

    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "labels" in data
    assert "values" in data
    assert "stats" in data
    assert data["stats"]["n"] == 5
    # A média dos resíduos de uma regressão linear deve ser muito próxima de zero
    assert abs(data["stats"]["mean"]) < 1e-10


def test_api_residual_analysis_no_data(client, mocker):
    """Verifica se /api/residual-analysis retorna erro quando não há dados."""
    mock_stream = mocker.patch("tsensor.routes.api.data_stream")
    type(mock_stream).data = mocker.PropertyMock(return_value=[])

    response = client.get("/api/residual-analysis")

    assert response.status_code == 400
    assert "error" in response.get_json()
