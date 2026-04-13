import pytest
from parsel import Selector
from tsensor.core.data_stream import DataStream
from tsensor.extensions import manager, config
from tsensor.core.utils import MCU_PRESETS


@pytest.fixture
def mock_handler(mocker):
    """Fixture para mockar um handler e registrar no manager global."""
    handler = mocker.Mock()
    handler.data = DataStream(total_samples=100)
    handler.data_buffer = DataStream(total_samples=100)
    
    # Registra o handler no manager real para o loop do endpoint funcionar
    mocker.patch.dict(manager._handlers, {"Sensor Teste": handler})
    
    # Mock da configuração correspondente
    mock_sensor_config = [{"name": "Sensor Teste", "calibration": {"v_ref": 3.3, "adc_max": 4095}}]
    mocker.patch.dict(config, {"sensors": mock_sensor_config})
    
    mocker.patch("tsensor.routes.api._get_main_handler", return_value=handler)
    return handler


def test_api_status_returns_connection_state(client, mocker):
    """Verifica se a rota /api/status retorna o estado global da aplicação."""
    mock_status = {
        "connected": True,
        "port": "/dev/ttyACM0",
        "mcu": "esp32",
        "error": None,
    }
    mocker.patch("tsensor.routes.api.app_status", mock_status)

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == mock_status


def test_api_stats_returns_html_partial_with_mocked_values(client, mock_handler):
    """Testa a rota /api/stats com valores mockados."""
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        mock_handler.data.add(val, timestamp="10:00:00:000")

    response = client.get("/api/stats")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    sel = Selector(html)

    # Verifica se o nome do sensor aparece no HTML
    assert "Sensor Teste" in html
    # Primeiro p.text-xl é a contagem n
    assert sel.css("p.text-xl::text").get() == "5"


def test_api_stats_empty_stream(client, mock_handler):
    """Verifica o comportamento da rota de estatísticas com stream vazio."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    sel = Selector(response.data.decode("utf-8"))

    assert sel.css("p.text-xl::text").get() == "0"


def test_api_histogram_returns_json_with_mocked_values(client, mock_handler):
    """Testa a rota /api/histogram com valores mockados."""
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        mock_handler.data.add(val, timestamp="10:00:00:000")

    response = client.get("/api/histogram")

    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "Sensor Teste" in data
    assert "labels" in data["Sensor Teste"]
    assert sum(data["Sensor Teste"]["values"]) == 5


def test_api_histogram_empty_stream(client, mock_handler):
    """Verifica o comportamento da rota de histograma com stream vazio."""
    response = client.get("/api/histogram")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "Sensor Teste" in data
    assert sum(data["Sensor Teste"]["values"]) == 0


def test_api_config_updates_values_and_calls_save(client, mocker):
    """Verifica se a rota /api/config processa o POST e chama save_config."""
    mock_config = {
        "hardware": {"port": "/old/port", "mcu": "arduino_uno", "baudrate": 9600},
        "sensors": [{"name": "Sensor 1", "type": "temperature", "model": "LM35", "calibration": {"adc_max": 1023, "v_ref": 1.1}}],
        "acquisition": {"total_samples": 1000},
        "presentation": {
            "update_interval_ms": 500,
            "decimal_places": 2,
            "log_level": "INFO",
            "debug_mode": False
        },
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
        "sensors": [{"name": "Sensor 1", "type": "temperature", "model": "LM35", "calibration": {"adc_max": 1023, "v_ref": 1.1}}],
        "acquisition": {"total_samples": 1000},
        "presentation": {
            "update_interval_ms": 500,
            "decimal_places": 2,
            "log_level": "INFO",
            "debug_mode": False
        },
    }

    mocker.patch("tsensor.routes.api.config", mock_config)

    payload = {
        "port": "/dev/ttyUSB1",
        "mcu": "esp32",
        "baudrate": "115200",
        "sensors": [{"name": "Sensor 1", "type": "temperature", "model": "LM35", "calibration": {"adc_max": 4095, "v_ref": 3.3}}]
    }

    response = client.post("/api/config", json=payload)

    assert response.status_code == 200
    assert response.json["success"] is True

    args, _ = mock_save.call_args
    saved_config = args[0]

    assert saved_config["hardware"]["mcu"] == "esp32"
    # Como passamos 'sensors' no payload, ele sobrescreve os valores
    assert saved_config["sensors"][0]["calibration"]["adc_max"] == 4095
    assert saved_config["sensors"][0]["calibration"]["v_ref"] == 3.3


def test_api_restart_restarts_acquisition(client, mocker):
    """Verifica se /api/restart para a aquisição e reinicia."""
    mocker.patch("tsensor.routes.api.stop_acquisition")
    mocker.patch("tsensor.routes.api.start_acquisition")

    response = client.post("/api/restart")

    assert response.status_code == 200
    assert response.json["success"] is True


def test_api_export_success(client, mock_handler, mocker):
    """Verifica se /api/export chama o exportador CSV corretamente com sucesso."""
    # Simula dados no sample (propriedade do DataStream)
    mocker.patch.object(DataStream, "sample",
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


def test_api_export_no_data_fails(client, mock_handler, mocker):
    """Verifica se /api/export falha quando não há dados no stream."""
    # Garante que o stream associado ao handler está vazio
    mock_handler.data = mocker.Mock(spec=DataStream)
    type(mock_handler.data).sample = mocker.PropertyMock(return_value=[])

    # Mock do exportador para evitar execução de código real
    mocker.patch("tsensor.routes.api.CSVExporter")

    response = client.post("/api/export")

    assert response.status_code == 400
    assert "Não há dados" in response.json["error"]


def test_api_residual_analysis_success(client, mock_handler):
    """Testa se a rota /api/residual-analysis retorna histograma e estatísticas dos resíduos."""
    test_data = [10.0, 11.0, 12.0, 13.0, 14.0]

    for val in test_data:
        mock_handler.data.add(val, timestamp="10:00:00:000")

    response = client.get("/api/residual-analysis")

    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "labels" in data
    assert "values" in data
    assert "stats" in data
    assert data["stats"]["n"] == 5
    assert abs(data["stats"]["mean"]) < 1e-10


def test_api_residual_analysis_no_data(client, mock_handler):
    """Verifica se /api/residual-analysis retorna erro quando não há dados."""
    response = client.get("/api/residual-analysis")

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_api_update_config_advanced_and_debug(client, mocker):
    """Valida o salvamento de configurações de debug e limites opcionais."""
    mocker.patch("tsensor.routes.api.save_config")

    payload = {
        "mcu": "esp32",
        "port": "/dev/ttyUSB1",
        "baudrate": "9600",
        "enable_limit_samples": "on",
        "total_samples": "5000",
        "enable_limit_time": False,
        "update_interval_ms": "2000",
        "decimal_places": "3",
        "debug_mode": "on",
        "log_level": "DEBUG"
    }

    response = client.post("/api/config", json=payload)
    assert response.status_code == 200

    # Verifica se os valores foram aplicados no dicionário global de config
    assert config["acquisition"]["total_samples"] == 5000
    assert "max_runtime_sec" not in config["acquisition"]
    assert config["presentation"]["debug_mode"] is True
    assert config["presentation"]["log_level"] == "DEBUG"
    assert config["presentation"]["decimal_places"] == 3


def test_api_config_rejects_empty_sensors_list(client, mocker):
    """Valida que a API rejeita um payload onde a lista de sensores está vazia."""
    mocker.patch("tsensor.routes.api.save_config")

    payload = {
        "port": "/dev/ttyACM0",
        "mcu": "esp32",
        "baudrate": 115200,
        "sensors": []
    }

    response = client.post("/api/config", json=payload)

    assert response.status_code == 400
    assert "pelo menos um sensor" in response.get_json()["error"]
