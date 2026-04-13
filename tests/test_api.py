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
    handler.time_series = DataStream(total_samples=100)

    # Registra o handler no manager real para o loop do endpoint funcionar
    mocker.patch.dict(manager._handlers, {"Sensor Teste": handler})

    # Mock da configuração correspondente
    mock_sensor_config = [{"name": "Sensor Teste",
                           "calibration": {"v_ref": 3.3, "adc_max": 4095}}]
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
    # Primeiro p.text-2xl é a contagem n
    assert sel.css("p.text-2xl::text").get() == "5"


def test_api_stats_empty_stream(client, mock_handler):
    """Verifica o comportamento da rota de estatísticas com stream vazio."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    sel = Selector(response.data.decode("utf-8"))

    assert sel.css("p.text-2xl::text").get() == "0"


def test_api_histogram_returns_json_with_mocked_values(client, mock_handler):
    """Testa a rota /api/histogram com valores mockados e série temporal."""
    # Adiciona dados ao stream principal
    for val in [10.0, 20.0, 30.0, 40.0, 50.0]:
        mock_handler.data.add(val, timestamp="10:00:00:000")

    # Simula dados na série temporal (decimada)
    mock_handler.time_series.add(30.0, timestamp="10:00:05")

    response = client.get("/api/histogram")

    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    sensor_data = data["Sensor Teste"]

    # Valida Histograma
    assert "histogram" in sensor_data
    assert "labels" in sensor_data["histogram"]
    assert sum(sensor_data["histogram"]["values"]) == 5

    # Valida Série Temporal (Campos labels e values no topo do objeto do sensor)
    assert "labels" in sensor_data
    assert "values" in sensor_data
    assert sensor_data["labels"][0] == "10:00:05"
    assert sensor_data["values"][0] == 30.0


def test_api_histogram_empty_stream(client, mock_handler):
    """Verifica o comportamento da rota de histograma com stream vazio."""
    response = client.get("/api/histogram")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert "Sensor Teste" in data
    assert "histogram" in data["Sensor Teste"]
    assert sum(data["Sensor Teste"]["histogram"]["values"]) == 0


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
    """Verifica se /api/export chama o exportador CSV com colunas paralelas (Wide Format)."""
    # Adiciona dados reais ao handler registrado no manager
    mock_handler.data.add(25.0, timestamp="10:00:01")

    mock_exporter_cls = mocker.patch("tsensor.routes.api.CSVExporter")
    mock_exporter_inst = mock_exporter_cls.return_value
    mock_exporter_inst.export.return_value = True

    response = client.post("/api/export")

    assert response.status_code == 200
    assert response.json["success"] is True
    assert "lado a lado" in response.json["message"]

    # Verifica o cabeçalho dinâmico (no mock_handler o tipo padrão no config mockado é omitido, cai no 'valor')
    # No mock_handler definido no topo do arquivo, o config['sensors'] tem type não definido explicitamente (cai no default 'valor')
    # Mas vamos ver o que o config mockado na fixture mock_handler tem:
    # mock_sensor_config = [{"name": "Sensor Teste", ...}] -> não tem 'type'
    expected_header = ["timestamp", "valor"]

    mock_exporter_cls.assert_called_once_with(
        directory="exports",
        header=expected_header
    )

    mock_exporter_inst.setup.assert_called_once()

    # Verifica se os dados foram alinhados lado a lado
    # Como só temos 1 sensor no manager do mock, teremos [ts, val]
    expected_rows = [["10:00:01", 25.0]]
    mock_exporter_inst.export.assert_called_once()
    args, kwargs = mock_exporter_inst.export.call_args
    assert args[0] == expected_rows
    assert kwargs["sep"] == ";"
    assert "Sensor Teste" in kwargs["comment"]


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


def test_api_download_charts_zip_success(client, mock_handler, mocker):
    """Verifica se /api/download-charts-zip gera um arquivo ZIP com os gráficos."""
    import io
    import zipfile

    # Popula o handler com dados fictícios para gerar gráficos
    for i in range(5):
        mock_handler.data.add(20.0 + i, timestamp=f"10:00:0{i}")
        mock_handler.time_series.add(20.0 + i, timestamp=f"10:00:0{i}")

    response = client.get("/api/download-charts-zip")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/zip"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "tsensor_charts" in response.headers["Content-Disposition"]

    # Valida o conteúdo do ZIP
    with zipfile.ZipFile(io.BytesIO(response.data)) as zf:
        file_list = zf.namelist()
        # Deve conter pelo menos a série temporal, histograma e resíduos para o sensor testado
        assert any("serie_temporal_Sensor_Teste" in f for f in file_list)
        assert any("histograma_Sensor_Teste" in f for f in file_list)
        assert any("residuos_Sensor_Teste" in f for f in file_list)


def test_api_download_charts_zip_no_sensors(client, mocker):
    """Verifica se a rota retorna erro quando não há handlers registrados."""
    mocker.patch("tsensor.routes.api.manager", [])

    response = client.get("/api/download-charts-zip")
    assert response.status_code == 400
    assert "Nenhum sensor configurado" in response.get_json()["error"]
