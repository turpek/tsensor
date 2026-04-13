from tsensor.core.utils import load_config, DEFAULT_CONFIG, MCU_PRESETS


def test_load_config_returns_default_when_file_missing(mocker):
    """Valida se load_config retorna o template padrão via mock de os.path.exists."""
    mocker.patch("os.path.exists", return_value=False)
    config = load_config()
    assert config == DEFAULT_CONFIG
    assert config is not DEFAULT_CONFIG
    # O default no template agora é esp32
    assert config["hardware"]["mcu"] == "esp32"


def test_load_config_applies_mcu_presets_from_file(mocker):
    """Valida se os presets do MCU são aplicados à lista de sensores ao carregar arquivo parcial."""
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", mocker.mock_open(read_data=""))
    mocker.patch(
        "toml.load", return_value={
            "hardware": {"mcu": "arduino_uno"},
            "sensors": [
                {"name": "s1", "type": "temperature",
                    "model": "LM35"}  # Sem calibração
            ]
        }
    )
    config = load_config()
    assert config["hardware"]["mcu"] == "arduino_uno"
    assert len(config["sensors"]) == 1

    # Verifica se os presets foram aplicados aos sensores existentes
    sensor = config["sensors"][0]
    assert sensor["calibration"]["adc_max"] == MCU_PRESETS["arduino_uno"]["adc_max"]
    assert sensor["calibration"]["v_ref"] == MCU_PRESETS["arduino_uno"]["v_ref"]
