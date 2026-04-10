import time
import pytest
from tsensor.core.handlers import NTCHandler
from tsensor.core.data_stream import DataStream


@pytest.fixture
def handler():
    """Configura uma instância de NTCHandler para testes."""
    data = DataStream(total_samples=100)
    temporal_data = DataStream(total_samples=100)
    return NTCHandler(
        data=data,
        temporal_data=temporal_data,
        samples=10,
        timeout=1
    )


def test_ntc_handler_initially_is_active(handler):
    """Verifica se o handler inicia como ativo."""
    assert handler.is_active is True


def test_ntc_handler_becomes_inactive_after_timeout():
    """Verifica se o handler fica inativo após o tempo de timeout (0.1s) expirar sem dados."""
    data = DataStream(total_samples=100)
    temporal_data = DataStream(total_samples=100)
    
    # Timeout de 0.1 segundo para o teste ser ultrarrápido
    handler = NTCHandler(
        data=data,
        temporal_data=temporal_data,
        samples=10,
        timeout=0.1
    )

    # Inicialmente ativo
    assert handler.is_active is True

    # Aguarda o timeout (com pequena margem)
    time.sleep(0.15)

    # Deve ficar inativo
    assert handler.is_active is False


def test_ntc_handler_becomes_inactive_after_reaching_samples(handler, mocker):
    """Verifica se o handler fica inativo após atingir o número máximo de amostras."""
    # 1. Setup do Mock para o atributo data
    # Mockando len(self._data) para retornar o limite de samples (10)
    mock_data = mocker.MagicMock(spec=DataStream)
    mock_data.__len__.return_value = 10
    
    # Injetando o mock no handler
    handler._data = mock_data
    
    # 2. Assert: is_active deve ser False agora
    assert handler.is_active is False


def test_ntc_handler_handle_valid_data(handler):
    """Verifica se o método handle processa corretamente a string '2025' resultando em aprox. 25.5°C."""
    # 1. Execução: handle do valor ADC 2025
    handler.handle("2025")

    # 2. Asserts
    assert len(handler.temporal_data) == 1
    assert len(handler.data) == 1
    
    # Valida se houve a inserção da temperatura correta (aprox 25.5)
    _, val_temp = handler.temporal_data.sample[0]
    _, val_data = handler.data.sample[0]
    
    assert val_temp == pytest.approx(25.5, abs=0.1)
    assert val_data == pytest.approx(25.5, abs=0.1)


def test_ntc_handler_handle_limits_adc(handler):
    """Verifica se o método handle ignora os limites de ADC (0 e 4095)."""
    # 1. Execução: envia 0 (inferior) e 4095 (superior)
    handler.handle("0")
    handler.handle("4095")

    # 2. Asserts: o tamanho deve continuar em 0
    assert len(handler.temporal_data) == 0
    assert len(handler.data) == 0


def test_ntc_handler_handle_empty_string(handler):
    """Verifica se o método handle ignora strings vazias."""
    handler.handle("")
    assert len(handler.temporal_data) == 0
    assert len(handler.data) == 0


def test_ntc_handler_handle_invalid_string(handler):
    """Verifica se o método handle ignora strings não numéricas sem quebrar."""
    # Deve ignorar e não levantar exceção (ValueError)
    handler.handle("abc")
    handler.handle("25.5.5")
    
    assert len(handler.temporal_data) == 0
    assert len(handler.data) == 0
