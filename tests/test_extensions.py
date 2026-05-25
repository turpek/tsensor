import pytest
from unittest.mock import MagicMock
from tsensor.extensions import setup_manager, setup_serial_manager, manager
from tsensor.core.handlers import TimestampHandler


def test_setup_serial_manager_adds_timestamp_as_first_handler(mocker):
    """Verifica se o setup_serial_manager adiciona o TimestampHandler como o primeiro."""
    test_config = {
        "acquisition": {
            "serial_batch_size": 100,
            "max_runtime_sec": 60
        },
        "sensors": [
            {
                "name": "Temp",
                "model": "LM35",
                "calibration": {"adc_max": 4095, "v_ref": 3.3}
            }
        ]
    }

    # Execução
    serial_manager = setup_serial_manager(test_config)

    # Verificações
    assert len(serial_manager) == 2

    # O primeiro handler deve ser o timestamp
    handler_names = list(serial_manager._handlers.keys())
    assert handler_names[0] == "timestamp"
    assert isinstance(serial_manager._handlers.get(
        "timestamp"), TimestampHandler)
    assert handler_names[1] == "Temp"


def test_setup_manager_adds_multiple_handlers_correctly(mocker):
    """
    Valida se o setup_manager cria e adiciona múltiplos handlers ao manager
    global baseando-se no dicionário de configuração.
    """
    # 1. Mock do load_config não é necessário pois passamos o config via parâmetro
    test_config = {
        "acquisition": {
            "total_samples": 5000,
            "max_runtime_sec": 3600,
            "buffer_samples": 500
        },
        "sensors": [
            {
                "name": "Ambiente",
                "type": "temperature",
                "model": "LM35",
                "calibration": {"adc_max": 4095, "v_ref": 3.3}
            },
            {
                "name": "Motor",
                "type": "temperature",
                "model": "NTC",
                "calibration": {"adc_max": 1023, "v_ref": 1.1}
            }
        ]
    }

    # 2. Execução
    # O manager é global, então o setup_manager vai alterar o estado dele
    result_manager = setup_manager(test_config)

    # 3. Verificações
    # Agora o len é 3 (2 sensores + 1 timestamp)
    assert len(result_manager) == 3
    assert result_manager.get_handler("timestamp") is not None
    assert result_manager.get_handler("Ambiente") is not None
    assert result_manager.get_handler("Motor") is not None


def test_setup_manager_configures_only_timestamp_with_no_valid_sensors(mocker):
    """Garante que se nenhum sensor válido for encontrado, apenas o timestamp é configurado."""
    mocker.patch("tsensor.extensions.HANDLERS",
                 {})  # Nenhum handler disponível

    test_config = {
        "acquisition": {},
        "sensors": [{"name": "Erro", "type": "temp", "model": "INVALIDO"}]
    }

    result_manager = setup_manager(test_config)
    assert len(result_manager) == 1
    assert list(result_manager._handlers.keys()) == ["timestamp"]
