import pytest
from tsensor.core.utils import load_config, DEFAULT_CONFIG, MCU_PRESETS


def test_load_config_returns_default_when_file_missing(mocker):
    """Valida se load_config retorna o template padrão via mock de os.path.exists."""
    mocker.patch("os.path.exists", return_value=False)

    config = load_config()

    # Deve ser uma cópia profunda do template
    assert config == DEFAULT_CONFIG
    assert config is not DEFAULT_CONFIG
    assert config["hardware"]["mcu"] == "esp32"


def test_load_config_applies_mcu_presets_from_file(mocker):
    """Valida se os presets do MCU são aplicados ao carregar arquivo parcial."""
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", mocker.mock_open(read_data=""))
    # Simula arquivo TOML que contém apenas a definição do MCU
    mocker.patch("toml.load", return_value={"hardware": {"mcu": "arduino_uno"}})

    config = load_config()

    # Deve carregar o MCU do mock e aplicar os presets do Arduino Uno
    assert config["hardware"]["mcu"] == "arduino_uno"
    assert config["sensor"]["adc_max"] == MCU_PRESETS["arduino_uno"]["adc_max"]
    assert config["sensor"]["v_ref"] == MCU_PRESETS["arduino_uno"]["v_ref"]


def test_api_config_saves_and_applies_presets(mocker, client):
    """Valida se a rota /api/config salva o arquivo e aplica presets de hardware."""
    # Mock das dependências que causam efeitos colaterais
    mock_save = mocker.patch("tsensor.routes.api.save_config")

    # Payload para trocar para ESP32
    payload = {"port": "/dev/ttyUSB1", "mcu": "esp32", "baudrate": "115200"}

    response = client.post("/api/config", json=payload)

    assert response.status_code == 200
    assert response.json["success"] is True

    # Verifica se save_config foi chamado com os presets automáticos do ESP32
    args, _ = mock_save.call_args
    saved_config = args[0]

    assert saved_config["hardware"]["mcu"] == "esp32"
    assert saved_config["sensor"]["adc_max"] == MCU_PRESETS["esp32"]["adc_max"]
    assert saved_config["sensor"]["v_ref"] == MCU_PRESETS["esp32"]["v_ref"]
