import time
import pytest
from tsensor.core.handlers import NTCHandler, LM35Handler, MPS20Handler, StreamManager
from tsensor.core.data_stream import DataStream

# --- FIXTURES ---


@pytest.fixture
def data_streams():
    # Agora retorna 3 DataStreams: global, buffer e time_series
    return DataStream(total_samples=100), DataStream(total_samples=100), DataStream(total_samples=100)


@pytest.fixture
def ntc_handler(data_streams):
    data, data_buffer, time_series = data_streams
    return NTCHandler(
        data=data,
        data_buffer=data_buffer,
        time_series=time_series,
        adc_max=4095,
        v_ref=3.3,
    )


@pytest.fixture
def lm35_handler(data_streams):
    data, data_buffer, time_series = data_streams
    return LM35Handler(
        data=data,
        data_buffer=data_buffer,
        time_series=time_series,
        adc_max=1023,
        v_ref=1.1,
    )


@pytest.fixture
def mps20_handler(data_streams):
    data, data_buffer, time_series = data_streams
    return MPS20Handler(
        data=data,
        data_buffer=data_buffer,
        time_series=time_series,
        adc_max=4095,
        v_ref=3.3,
        offset=22.6,
        sensitivity=1.6949
    )


@pytest.fixture
def stream_manager():
    manager = StreamManager()
    # Configure agora lida apenas com limites de tempo e contagem global
    manager.configure(timeout=1)
    return manager

# --- TESTES PARA STREAMMANAGER (FOCO: ORQUESTRAÇÃO E TAMANHO) ---


def test_stream_manager_len_initially_zero():
    manager = StreamManager()
    assert len(manager) == 0


def test_stream_manager_len_after_adding_handlers(stream_manager, lm35_handler, ntc_handler):
    stream_manager.add_handler("sensor1", lm35_handler)
    assert len(stream_manager) == 1

    stream_manager.add_handler("sensor2", ntc_handler)
    assert len(stream_manager) == 2


def test_stream_manager_len_resets_on_configure():
    manager = StreamManager()
    manager.configure()
    manager.add_handler("s1", None)
    assert len(manager) == 1

    manager.configure()
    assert len(manager) == 0


def test_stream_manager_add_and_get_handler(stream_manager, lm35_handler):
    stream_manager.add_handler("temp_sensor", lm35_handler)
    handler = stream_manager.get_handler("temp_sensor")
    assert handler == lm35_handler


def test_stream_manager_dispatch_to_multiple_handlers(stream_manager):
    d1, b1, t1 = DataStream(10), DataStream(10), DataStream(10)
    h1 = LM35Handler(d1, b1, t1, 1023, 1.1)

    d2, b2, t2 = DataStream(10), DataStream(10), DataStream(10)
    h2 = LM35Handler(d2, b2, t2, 1023, 1.1)

    stream_manager.add_handler("s1", h1)
    stream_manager.add_handler("s2", h2)

    stream_manager.dispatch("T=512")
    assert len(d1) == 1
    assert len(d2) == 1


def test_stream_manager_is_active_with_total_samples_limit():
    limit = 5
    manager = StreamManager()
    manager.configure(timeout=10, total_samples=limit)

    d, b, t = DataStream(10), DataStream(10), DataStream(10)
    h = LM35Handler(d, b, t, 1023, 1.1)
    manager.add_handler("s1", h)

    for i in range(limit):
        assert manager.is_active is True
        manager.dispatch("T=100")

    assert manager.is_active is False


def test_stream_manager_is_active_based_on_max_samples_per_sensor(stream_manager):
    """
    Testa se o manager continua ativo enquanto nenhum sensor individualmente 
    atingiu o limite, mesmo que a soma de amostras de todos os sensores 
    ultrapasse o total_samples.
    """
    limit = 10
    # Timeout alto para não interferir
    stream_manager.configure(timeout=60, total_samples=limit)

    # Sensor 1
    d1, b1, t1 = DataStream(20), DataStream(20), DataStream(20)
    h1 = LM35Handler(d1, b1, t1, 1023, 1.1)

    # Sensor 2
    d2, b2, t2 = DataStream(20), DataStream(20), DataStream(20)
    h2 = LM35Handler(d2, b2, t2, 1023, 1.1)

    stream_manager.add_handler("s1", h1)
    stream_manager.add_handler("s2", h2)

    # Envia 6 mensagens. Como ambos processam, o contador global atual chegaria a 12.
    # Pela regra nova, o manager deve ver que o máximo de amostras em um stream é 6.
    for _ in range(6):
        stream_manager.dispatch("T=100")

    # Se falhar aqui (is_active == False), a inconsistência foi capturada.
    assert stream_manager.is_active is True
    assert stream_manager.count_samples == 6

    # Completa até o limite de 10
    for _ in range(4):
        stream_manager.dispatch("T=100")

    assert stream_manager.is_active is False
    assert stream_manager.count_samples == 10


# --- TESTES PARA MPS20HANDLER ---


def test_mps20_conversion_logic(mps20_handler):
    """Valida a fórmula matemática de conversão de pressão."""
    # Sem offset, ADC 0 deve resultar em 0 kPa
    adc_value = 0
    assert mps20_handler._convert(adc_value) == pytest.approx(0, abs=1e-2)

    # Verifica o alvo de 93556 (ESP32 @ 3.3V, ganho 128, sens 1.6949)
    assert mps20_handler._convert(93556) == pytest.approx(0.0848, abs=1e-2)


def test_mps20_handle_valid_prefix(mps20_handler):
    """Verifica se o handler processa corretamente o prefixo P= com 24 bits."""
    line = "P=93556"
    success = mps20_handler.handle(line)
    assert success is True
    assert len(mps20_handler.data) == 1
    # Pressão ~ 0.0848
    assert mps20_handler.data.samples[0] == pytest.approx(0.0848, abs=1e-2)


def test_mps20_handle_ignores_wrong_prefix(mps20_handler):
    """Garante que o handler de pressão ignora dados de temperatura (T=)."""
    line = "T=2500"
    success = mps20_handler.handle(line)
    assert success is False
    assert len(mps20_handler.data) == 0


def test_mps20_custom_calibration():
    """Valida se o handler respeita offsets e sensibilidades customizadas."""
    # Usando valores realistas para 24 bits
    v_ref = 5.0
    offset = 0.0  # offset não é mais usado
    sensitivity = 2.0

    custom_handler = MPS20Handler(
        data=DataStream(10),
        data_buffer=DataStream(10),
        time_series=DataStream(10),
        adc_max=4095,  # Não usado na fórmula fixa de 24 bits
        v_ref=v_ref,
        offset=offset,
        sensitivity=sensitivity
    )

    # Simula um valor de ADC que resultaria em 15.0 mV no sensor
    # v_sensor_mv = 15.0 -> v_no_adc_mv = 15.0 * 128 = 1920.0
    # adc = (1920.0 * 2**24) / (v_ref * 1000)
    adc_target = int((1920.0 * (2**24)) / (v_ref * 1000))

    # Esperado com a nova fórmula: 15.0 / 2.0 = 7.5 kPa
    assert custom_handler._convert(adc_target) == pytest.approx(7.5, abs=1e-2)
