import pytest
from tsensor.core.data_stream import DataStream


@pytest.fixture
def stream_vazia():
    return DataStream(total_samples=3)


@pytest.fixture
def stream_preenchida():
    # Instancia e preenche com 3 amostras (limite da janela)
    stream = DataStream(total_samples=3)
    # Agora o add exige timestamp!
    for temp in [25.0, 25.1, 25.2]:
        stream.add(temp, timestamp="10:00:00:000")
    return stream


def test_datastream_inicialmente_vazio(stream_vazia):
    assert len(stream_vazia) == 0


def test_datastream_adicionar_amostra(stream_vazia):
    stream_vazia.add(25.5, timestamp="10:00:00:000")
    assert len(stream_vazia) == 1


def test_datastream_respeita_timestamp_manual(stream_vazia):
    """Verifica se o timestamp injetado é exatamente o salvo."""
    ts = "12:34:56:789"
    stream_vazia.add(25.5, timestamp=ts)

    ts_gravado, val = stream_vazia.sample[0]
    assert ts_gravado == ts
    assert val == 25.5


def test_datastream_moving_average_vazio(stream_vazia):
    """Verifica se moving_average retorna 0.0 em vez de erro quando vazio."""
    assert stream_vazia.moving_average == 0.0


def test_datastream_mantem_tamanho_maximo_ao_exceder(stream_preenchida):
    stream_preenchida.add(25.3, timestamp="10:00:00:000")
    assert len(stream_preenchida) == 3


def test_datastream_moving_average_inicial(stream_preenchida):
    assert stream_preenchida.moving_average == pytest.approx(25.1)


def test_datastream_moving_average_apos_deslocamento(stream_preenchida):
    stream_preenchida.add(25.3, timestamp="10:00:00:000")
    assert stream_preenchida.moving_average == pytest.approx(25.2)


def test_datastream_mean_acumulada(stream_preenchida):
    assert stream_preenchida.mean == pytest.approx(25.1)
    stream_preenchida.add(26.1, timestamp="10:00:00:000")
    assert stream_preenchida.mean == pytest.approx(25.35)


def test_datastream_std_acumulado(stream_preenchida):
    assert stream_preenchida.std == pytest.approx(0.1)


def test_datastream_std_apos_insercao(stream_preenchida):
    stream_preenchida.add(26.1, timestamp="10:00:00:000")
    assert stream_preenchida.std == pytest.approx(0.50662, abs=1e-5)


def test_datastream_max_acumulado(stream_preenchida):
    assert stream_preenchida.max == 25.2
    stream_preenchida.add(26.5, timestamp="10:00:00:000")
    assert stream_preenchida.max == 26.5


def test_datastream_min_acumulado(stream_preenchida):
    assert stream_preenchida.min == 25.0
    stream_preenchida.add(23.5, timestamp="10:00:00:000")
    assert stream_preenchida.min == 23.5


def test_datastream_is_full_false_quando_vazio(stream_vazia):
    """Verifica se is_full é falso quando o stream não atingiu o limite."""
    assert stream_vazia.is_full is False
    stream_vazia.add(25.0, timestamp="10:00:00:000")
    assert stream_vazia.is_full is False


def test_datastream_is_full_true_quando_cheio(stream_preenchida):
    """Verifica se is_full é verdadeiro quando o stream atinge total_samples."""
    assert stream_preenchida.is_full is True


def test_datastream_clear_reseta_estado(stream_preenchida):
    """Verifica se o método clear limpa todos os dados e reseta estatísticas."""
    stream_preenchida.clear()

    assert len(stream_preenchida) == 0
    assert stream_preenchida.is_full is False
    assert stream_preenchida.mean == 0.0
    assert stream_preenchida.moving_average == 0.0
    assert stream_preenchida.max == -float("inf")
    assert stream_preenchida.min == float("inf")
    assert stream_preenchida.std == 0.0


def test_datastream_histogram_labels_lineares():
    # Criamos uma janela de 10 para garantir que todas as 10 fiquem na memória
    stream = DataStream(total_samples=10)
    for t in range(20, 30):
        stream.add(float(t), timestamp="10:00:00:000")

    hist = stream.histogram(resolucao_adc=0.1)
    expected_labels = ["20.0", "21.8", "23.6", "25.4", "27.2"]

    assert list(hist.keys()) == expected_labels
    assert list(hist.values()) == [2, 2, 2, 2, 2]


def test_datastream_histogram_decimal_customizado():
    stream = DataStream(total_samples=10)
    stream.add(20.123, timestamp="10:00:00:000")
    stream.add(20.456, timestamp="10:00:00:000")

    hist = stream.histogram(resolucao_adc=0.1, decimal_label=2)
    label_inicial = list(hist.keys())[0]
    assert label_inicial == "20.12"


def test_datastream_histogram_colisao_labels():
    stream = DataStream(total_samples=10)
    stream.add(25.0, timestamp="10:00:00:000")
    stream.add(25.5, timestamp="10:00:00:000")

    # Com decimal_label=0, as labels colidem em "25", resultando em apenas 1 bin
    hist = stream.histogram(resolucao_adc=0.1, decimal_label=0)
    assert len(hist) == 1
    assert "25" in hist


def test_datastream_histogram_garante_bins_minimos_sem_colisao():
    stream = DataStream(total_samples=100)
    # Amplitude grande para evitar colisão de labels
    stream.add(20.0, timestamp="10:00:00:000")
    stream.add(30.0, timestamp="10:00:00:000")

    hist = stream.histogram(resolucao_adc=0.1, decimal_label=1)

    assert len(hist) >= 5


def test_datastream_histogram_amostras_iguais():
    stream = DataStream(total_samples=10)
    for _ in range(5):
        stream.add(25.0, timestamp="10:00:00:000")

    hist = stream.histogram(resolucao_adc=0.1, decimal_label=1)
    # Espera que retorne a média como chave e o total de amostras como valor
    assert hist == {"25.0": 5}


def test_datastream_histogram_idx_limite_superior():
    stream = DataStream(total_samples=10)
    stream.add(20.0, timestamp="10:00:00:000")
    stream.add(30.0, timestamp="10:00:00:000")

    hist = stream.histogram(resolucao_adc=0.1)
    last_label = list(hist.keys())[-1]
    # O valor máximo deve estar no último bin
    assert hist[last_label] >= 1
