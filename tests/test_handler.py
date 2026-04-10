import time
import pytest
from tsensor.core.handlers import NTCHandler, LM35Handler
from tsensor.core.data_stream import DataStream


@pytest.fixture
def handler():
    """Configura uma instância de NTCHandler para testes (ADC 12-bit, 3.3V)."""
    data = DataStream(total_samples=100)
    temporal_data = DataStream(total_samples=100)
    return NTCHandler(
        data=data,
        temporal_data=temporal_data,
        samples=10,
        timeout=1,
        adc_max=4095,
        v_ref=3.3,
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
        timeout=0.1,
        adc_max=4095,
        v_ref=3.3,
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
    # 1. Execução: handle do valor ADC 2025 (Ref 3.3V, 12-bit)
    handler.handle("2025")

    # 2. Asserts
    assert len(handler.temporal_data) == 1
    assert len(handler.data) == 1

    # Valida se houve a inserção da temperatura correta (aprox 25.5)
    _, val_temp = handler.temporal_data.sample[0]
    _, val_data = handler.data.sample[0]

    assert val_temp == pytest.approx(25.5, abs=0.5)
    assert val_data == pytest.approx(25.5, abs=0.5)


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


# --- TESTES PARA LM35Handler ---


@pytest.fixture
def lm35_handler():
    """Configura uma instância de LM35Handler para testes (Arduino 10-bit, 1.1V)."""
    data = DataStream(total_samples=100)
    temporal_data = DataStream(total_samples=100)
    return LM35Handler(
        data=data,
        temporal_data=temporal_data,
        samples=10,
        timeout=1,
        adc_max=1023,
        v_ref=1.1,
    )


def test_lm35_handler_conversion(lm35_handler):
    """
    Verifica a conversão de ADC para temperatura no LM35 (1.1V/10bits).
    205 ADC -> (205/1023)*1.1 = 0.2204V -> 22.04°C
    51 ADC -> (51/1023)*1.1 = 0.0548V -> 5.48°C
    """
    lm35_handler.handle("205")
    lm35_handler.handle("51")

    assert len(lm35_handler.data) == 2

    _, temp1 = lm35_handler.data.sample[0]
    _, temp2 = lm35_handler.data.sample[1]

    assert temp1 == pytest.approx(22.04, abs=0.1)
    assert temp2 == pytest.approx(5.48, abs=0.1)


def test_lm35_handler_limits_adc(lm35_handler):
    """Verifica se o LM35Handler ignora os limites de ADC (0 e 1023)."""
    lm35_handler.handle("0")
    lm35_handler.handle("1023")
    lm35_handler.handle("-1")
    lm35_handler.handle("1024")

    assert len(lm35_handler.data) == 0


def test_lm35_handler_invalid_input(lm35_handler):
    """Verifica se o LM35Handler ignora entradas inválidas."""
    lm35_handler.handle("temperatura")
    lm35_handler.handle("")

    assert len(lm35_handler.data) == 0


def test_lm35_handler_is_active_by_samples(lm35_handler, mocker):
    """Verifica se o LM35Handler fica inativo após atingir o número máximo de amostras."""
    mock_data = mocker.MagicMock(spec=DataStream)
    mock_data.__len__.return_value = 10
    lm35_handler._data = mock_data

    assert lm35_handler.is_active is False
