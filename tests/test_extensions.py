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
    assert isinstance(serial_manager.get_handler(
        "timestamp"), TimestampHandler)
    assert handler_names[1] == "Temp"


def test_setup_manager_adds_multiple_handlers_correctly(mocker):
    """
    Valida se o setup_manager cria e adiciona múltiplos handlers ao manager
    global baseando-se no dicionário de configuração.
    """
    # 1. Mock do SheetsHandler que agora é usado por padrão
    mock_handler_cls = MagicMock()
    mocker.patch("tsensor.extensions.SheetsHandler", mock_handler_cls)

    # 2. Mock do load_config não é necessário pois passamos o config via parâmetro
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

    # 3. Execução
    # O manager é global, então o setup_manager vai alterar o estado dele
    result_manager = setup_manager(test_config)

    # 4. Verificações
    # Agora o len é 3 (2 sensores + 1 timestamp)
    assert len(result_manager) == 3
    assert result_manager.get_handler("timestamp") is not None
    assert result_manager.get_handler("Ambiente") is not None
    assert result_manager.get_handler("Motor") is not None

    # Verifica se as classes de handler foram instanciadas 2 vezes (sensores)
    # mais a do timestamp (que também usa o mock do SheetsHandler no teste)
    assert mock_handler_cls.call_count == 3


def test_setup_manager_raises_error_with_no_valid_sensors(mocker):
    """Garante que um erro é lançado se nenhum sensor válido (além do timestamp) for encontrado."""
    mocker.patch("tsensor.extensions.HANDLERS",
                 {})  # Nenhum handler disponível

    test_config = {
        "acquisition": {},
        "sensors": [{"name": "Erro", "type": "temp", "model": "INVALIDO"}]
    }

    # O manager terá apenas o handler de timestamp, então deve falhar se não houver sensores úteis
    with pytest.raises(RuntimeError, match="Nenhum sensor válido"):
        setup_manager(test_config)
