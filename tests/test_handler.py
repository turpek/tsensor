import time
import pytest
from tsensor.core.handlers import NTCHandler, LM35Handler, StreamManager
from tsensor.core.data_stream import DataStream

# --- FIXTURES ---


@pytest.fixture
def data_streams():
    # Agora o tamanho do buffer é definido apenas aqui, na criação do DataStream
    return DataStream(total_samples=100), DataStream(total_samples=100)


@pytest.fixture
def ntc_handler(data_streams):
    data, data_buffer = data_streams
    return NTCHandler(
        data=data,
        data_buffer=data_buffer,
        adc_max=4095,
        v_ref=3.3,
    )


@pytest.fixture
def lm35_handler(data_streams):
    data, data_buffer = data_streams
    return LM35Handler(
        data=data,
        data_buffer=data_buffer,
        adc_max=1023,
        v_ref=1.1,
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
    d1, b1 = DataStream(10), DataStream(10)
    h1 = LM35Handler(d1, b1, 1023, 1.1)  # Sem o parâmetro samples

    d2, b2 = DataStream(10), DataStream(10)
    h2 = LM35Handler(d2, b2, 1023, 1.1)

    stream_manager.add_handler("s1", h1)
    stream_manager.add_handler("s2", h2)

    stream_manager.dispatch("T=512")
    assert len(d1) == 1
    assert len(d2) == 1


def test_stream_manager_is_active_with_total_samples_limit():
    limit = 5
    manager = StreamManager()
    manager.configure(timeout=10, total_samples=limit)

    d, b = DataStream(10), DataStream(10)
    h = LM35Handler(d, b, 1023, 1.1)
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
    d1, b1 = DataStream(20), DataStream(20)
    h1 = LM35Handler(d1, b1, 1023, 1.1)

    # Sensor 2
    d2, b2 = DataStream(20), DataStream(20)
    h2 = LM35Handler(d2, b2, 1023, 1.1)

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
