import time
import pytest
from tsensor.core.handlers import NTCHandler, LM35Handler, StreamManager
from tsensor.core.data_stream import DataStream

# --- FIXTURES ---


@pytest.fixture
def data_streams():
    return DataStream(total_samples=100), DataStream(total_samples=100)


@pytest.fixture
def ntc_handler(data_streams):
    data, temporal_data = data_streams
    return NTCHandler(
        data=data,
        temporal_data=temporal_data,
        samples=10,
        adc_max=4095,
        v_ref=3.3,
    )

@pytest.fixture
def lm35_handler(data_streams):
    data, temporal_data = data_streams
    return LM35Handler(
        data=data,
        temporal_data=temporal_data,
        samples=10,
        adc_max=1023,
        v_ref=1.1,
    )


@pytest.fixture
def stream_manager():
    return StreamManager(samples=10, timeout=1, adc_max=4095, v_ref=3.3)


# --- TESTES PARA HANDLERS (FOCO: PARSING E CONVERSÃO) ---


def test_ntc_handler_handle_valid_data_with_prefix(ntc_handler):
    """Verifica se o NTCHandler processa corretamente a string 'T=2025'."""
    ntc_handler.handle("T=2025")
    assert len(ntc_handler.data) == 1
    _, val = ntc_handler.data.sample[0]
    assert val == pytest.approx(25.5, abs=0.5)


def test_ntc_handler_ignores_noise_without_prefix(ntc_handler):
    """Verifica se o handler ignora strings que não seguem o padrão 'T='."""
    ntc_handler.handle("2025")  # Sem prefixo
    ntc_handler.handle("X=2025")  # Prefixo errado
    assert len(ntc_handler.data) == 0


def test_ntc_handler_limits_adc(ntc_handler):
    """Verifica se o handler ignora limites de ADC."""
    ntc_handler.handle("T=0")
    ntc_handler.handle("T=4095")
    assert len(ntc_handler.data) == 0


def test_lm35_handler_conversion_with_prefix(lm35_handler):
    """Verifica conversão do LM35 com o prefixo 'T='."""
    lm35_handler.handle("T=205")  # (205/1023)*1.1*100 = 22.04
    _, val = lm35_handler.data.sample[0]
    assert val == pytest.approx(22.04, abs=0.1)


# --- TESTES PARA STREAMMANAGER (FOCO: ORQUESTRAÇÃO) ---


def test_stream_manager_initially_active(stream_manager):
    assert stream_manager.is_active is True


def test_stream_manager_stop(stream_manager):
    stream_manager.stop()
    assert stream_manager.is_active is False


def test_stream_manager_timeout():
    manager = StreamManager(samples=10, timeout=0.1, adc_max=1023, v_ref=1.1)
    assert manager.is_active is True
    time.sleep(0.15)
    assert manager.is_active is False


def test_stream_manager_add_and_get_handler(stream_manager, data_streams):
    data, temp = data_streams
    stream_manager.add_handler("temp_sensor", LM35Handler, data, temp)

    handler = stream_manager.get_handler("temp_sensor")
    assert isinstance(handler, LM35Handler)
    assert handler.data == data


def test_stream_manager_dispatch_to_multiple_handlers(stream_manager, data_streams):
    """Verifica se o dispatch entrega a linha para todos os handlers registrados."""
    data1, temp1 = DataStream(10), DataStream(10)
    data2, temp2 = DataStream(10), DataStream(10)

    # Registra dois handlers (mesmo que sejam do mesmo tipo, para teste de dispatch)
    stream_manager.add_handler("s1", LM35Handler, data1, temp1)
    stream_manager.add_handler("s2", LM35Handler, data2, temp2)

    # Dispatch de um valor válido para LM35 (ADC 10-bit, VRef 3.3v no manager)
    # Nota: No StreamManager o v_ref é 3.3, então (512/1023)*3.3*100 = 165.1
    stream_manager.dispatch("T=512")

    assert len(data1) == 1
    assert len(data2) == 1
    _, v1 = data1.sample[0]
    _, v2 = data2.sample[0]
    assert v1 == v2


def test_stream_manager_is_active_with_total_samples_limit():
    """Verifica se o manager desativa após atingir o limite de amostras."""
    limit = 5
    manager = StreamManager(
        samples=10, timeout=10, adc_max=4095, v_ref=3.3, total_samples=limit
    )

    # Adiciona um handler para podermos chamar o dispatch
    data, temp = DataStream(10), DataStream(10)
    manager.add_handler("s1", LM35Handler, data, temp)

    # Estado inicial deve ser ativo
    assert manager.is_active is True

    # Simula o recebimento de amostras válidas
    for i in range(limit):
        assert manager.is_active is True, f"Deveria estar ativo na amostra {i}"
        manager.dispatch("T=100")

    # Após o limite, deve estar inativo
    assert manager.is_active is False


def test_stream_manager_is_active_without_total_samples():
    """Verifica se o manager ignora o limite se total_samples for None."""
    manager = StreamManager(
        samples=10, timeout=10, adc_max=4095, v_ref=3.3, total_samples=None
    )

    for _ in range(100):
        manager.dispatch("T=100")
        assert manager.is_active is True
