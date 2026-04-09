import pytest
from tsensor.data_stream import DataStream


@pytest.fixture
def stream_vazia():
    return DataStream(total_samples=3)


@pytest.fixture
def stream_preenchida():
    # Instancia e preenche com 3 amostras (limite da janela)
    stream = DataStream(total_samples=3)
    for temp in [25.0, 25.1, 25.2]:
        stream.add(temp)
    return stream


def test_datastream_inicialmente_vazio(stream_vazia):
    assert len(stream_vazia) == 0


def test_datastream_adicionar_amostra(stream_vazia):
    stream_vazia.add(25.5)
    assert len(stream_vazia) == 1


def test_datastream_mantem_tamanho_maximo_ao_exceder(stream_preenchida):
    stream_preenchida.add(25.3)
    assert len(stream_preenchida) == 3


def test_datastream_moving_average_inicial(stream_preenchida):
    assert stream_preenchida.moving_average == pytest.approx(25.1)


def test_datastream_moving_average_apos_deslocamento(stream_preenchida):
    stream_preenchida.add(25.3)
    assert stream_preenchida.moving_average == pytest.approx(25.2)


def test_datastream_mean_acumulada(stream_preenchida):
    assert stream_preenchida.mean == pytest.approx(25.1)
    stream_preenchida.add(26.1)
    assert stream_preenchida.mean == pytest.approx(25.35)


def test_datastream_std_acumulado(stream_preenchida):
    assert stream_preenchida.std == pytest.approx(0.1)


def test_datastream_std_apos_insercao(stream_preenchida):
    stream_preenchida.add(26.1)
    assert stream_preenchida.std == pytest.approx(0.50662, abs=1e-5)


def test_datastream_max_acumulado(stream_preenchida):
    assert stream_preenchida.max == 25.2
    stream_preenchida.add(26.5)
    assert stream_preenchida.max == 26.5


def test_datastream_min_acumulado(stream_preenchida):
    assert stream_preenchida.min == 25.0
    stream_preenchida.add(23.5)
    assert stream_preenchida.min == 23.5


def test_datastream_histogram_labels_lineares():
    # Criamos uma janela de 10 para garantir que todas as 10 fiquem na memória
    stream = DataStream(total_samples=10)
    for t in range(20, 30):
        stream.add(float(t))

    # Especificação para n=10:
    # 1. k = clamp(sqrt(10), 5, 30) = 5
    # 2. xmin=20.0, xmax=29.0 -> h = 9.0 / 5 = 1.8
    # 3. Labels: 20.0, 21.8, 23.6, 25.4, 27.2

    hist = stream.histogram()
    expected_labels = ["20.0", "21.8", "23.6", "25.4", "27.2"]

    assert list(hist.keys()) == expected_labels
    assert list(hist.values()) == [2, 2, 2, 2, 2]


def test_datastream_histogram_decimal_customizado():
    stream = DataStream(total_samples=10)
    # n=2 -> k=5 (min)
    # xmin=20.123, xmax=20.456
    stream.add(20.123)
    stream.add(20.456)

    hist = stream.histogram(decimal_label=2)
    label_inicial = list(hist.keys())[0]
    assert label_inicial == "20.12"


def test_datastream_histogram_amostras_iguais():
    # Cenário onde amplitude é 0. O sistema deve tratar sem divisão por zero.
    stream = DataStream(total_samples=10)
    for _ in range(5):
        stream.add(25.0)

    # Com amplitude 0, h vira 0. O código deve prever isso.
    hist = stream.histogram()
    # Espera-se que todos os 5 dados caiam no primeiro bin (25.0)
    assert "25.0" in hist
    assert hist["25.0"] == 5


def test_datastream_histogram_idx_limite_superior():
    # n=2, k=5, xmin=20.0, xmax=30.0, h=2.0
    stream = DataStream(total_samples=10)
    stream.add(20.0)
    stream.add(30.0)

    hist = stream.histogram()
    # O valor 30.0 cairia no índice 5 (fora do range 0-4), deve ser forçado para o bin 4
    last_label = list(hist.keys())[-1]
    assert hist[last_label] == 1


def test_datastream_histogram_idx_negativo(mocker):
    # Força o floor a retornar um valor negativo para testar o max(0, idx)
    stream = DataStream(total_samples=10)
    stream.add(20.0)
    stream.add(30.0)

    mocker.patch("tsensor.data_stream.floor", return_value=-1)

    hist = stream.histogram()
    # Se floor é -1, o max(0, -1) deve jogar os dados para o primeiro bin
    first_label = list(hist.keys())[0]
    assert hist[first_label] == 2
