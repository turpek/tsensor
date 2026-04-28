import numpy as np
from tsensor.core.utils import detrend, histogram, Stat, numpy_histogram, hybrid_histogram, AcquisitionGate


def test_acquisition_gate_default_returns_true():
    """Sem chamar enable(), wait() deve retornar True (comportamento padrão)."""
    gate = AcquisitionGate()
    assert gate.wait() is True


def test_acquisition_gate_synced_behavior():
    """Com enable() ativo, wait() deve retornar o valor enviado por signal()."""
    gate = AcquisitionGate()
    gate.enable()
    
    gate.signal(True)
    assert gate.wait() is True
    
    gate.signal(False)
    assert gate.wait() is False


def test_acquisition_gate_handles_empty_queue():
    """Com enable() ativo mas sem sinal, wait() deve retornar False após timeout (evita travar)."""
    gate = AcquisitionGate()
    gate.enable()
    
    # Não sinalizamos nada. O timeout curto garante que o teste não fique preso.
    assert gate.wait(timeout=0.1) is False


def test_stat_initialization():
    """Verifica se a classe Stat inicia com valores zerados ou neutros."""
    s = Stat(total_samples=10)
    assert s.mean == 0.0
    assert s.moving_average == 0.0
    assert s.std == 0.0
    assert s.min == float("inf")
    assert s.max == float("-inf")
    assert s.is_full is False
    assert s.amplitude == 0.0


def test_stat_initialization_with_data():
    """Verifica a inicialização atômica da Stat com um ndarray de dados."""
    data = np.array([10.0, 20.0, 30.0])
    s = Stat(total_samples=10, initial_data=data)

    assert s.mean == 20.0
    assert s.moving_average == 20.0
    assert s.min == 10.0
    assert s.max == 30.0
    assert np.isclose(s.std, 10.0)  # DP de [10, 20, 30] é 10
    assert len(s) == 3
    assert s.is_full is False


def test_stat_initialization_with_data_overflow():
    """Verifica se a inicialização com dados maiores que o limite descarta os mais antigos para a janela."""
    # Janela de 3 amostras, dados de entrada: 5 amostras
    data = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    s = Stat(total_samples=3, initial_data=data)

    # Média global de todos os 5 dados: (10+20+30+40+50)/5 = 30
    assert s.mean == 30.0
    # Média da janela (últimos 3): (30+40+50)/3 = 40
    assert s.moving_average == 40.0
    # Min/Max globais
    assert s.min == 10.0
    assert s.max == 50.0
    # Tamanho da janela preenchida
    assert len(s) == 3
    assert s.is_full is True
    # DP global de [10, 20, 30, 40, 50] -> sqrt(1000/4) = 15.811...
    assert np.isclose(s.std, np.std(data, ddof=1))


def test_stat_add_incremental():
    """Verifica estatísticas simples adicionando dados sem atingir o limite."""
    s = Stat(total_samples=10)
    s.update(10.0)
    s.update(20.0)

    assert s.mean == 15.0
    assert s.moving_average == 15.0
    assert s.min == 10.0
    assert s.max == 20.0
    assert s.amplitude == 10.0
    assert s.is_full is False


def test_stat_moving_average_and_std():
    """Valida o cálculo de média móvel e desvio padrão com algoritmo online."""
    s = Stat(total_samples=3)
    # Dados: 2, 4, 6 -> Média 4, Variância 4, DP 2
    s.update(2.0)
    s.update(4.0)
    s.update(6.0)

    assert s.mean == 4.0
    assert s.moving_average == 4.0
    assert np.isclose(s.std, 2.0)
    assert s.is_full is True


def test_stat_sliding_window_replacement():
    """Verifica se a estatística se ajusta corretamente ao remover dados antigos (sliding window)."""
    s = Stat(total_samples=2)
    s.update(10.0)  # [10]
    s.update(20.0)  # [10, 20] -> Mean 15, Mvg 15

    assert s.mean == 15.0
    assert s.moving_average == 15.0

    # Simula a saída do 10 e entrada do 30
    # Global: [10, 20, 30] (Mean 20) | Janela: [20, 30] (Mvg 25)
    s.update(30.0, old_date=10.0)

    assert s.mean == 20.0  # Média global acumulada
    assert s.moving_average == 25.0  # Média da janela
    assert s.max == 30.0
    assert s.min == 10.0  # Min global (10 ainda é o menor valor visto)


def test_stat_clear():
    """Verifica se o método clear reseta as estatísticas e permite mudar o tamanho."""
    s = Stat(total_samples=5)
    s.update(100.0)
    s.clear(total_samples=2)

    assert s.mean == 0.0
    assert s.min == float("inf")
    # Verifica se o novo limite é respeitado
    s.update(10.0)
    s.update(20.0)
    assert s.is_full is True


def test_histogram_success():
    """Verifica se o histograma gera bins e contagens corretas para dados simples."""
    samples = np.array([10.0, 10.1, 10.2, 10.3, 10.4, 10.5])
    res = histogram(samples, amplitude=0.5,
                    mvg_average=10.25, resolucao_adc=0.1)

    assert isinstance(res, dict)
    assert len(res) > 0
    assert sum(res.values()) == len(samples)


def test_histogram_amplitude_zero():
    """Deve retornar um único bin se a amplitude for zero."""
    samples = np.array([25.0, 25.0, 25.0])
    res = histogram(samples, amplitude=0.0,
                    mvg_average=25.0, resolucao_adc=0.1)

    assert len(res) == 1
    assert list(res.values())[0] == 3
    assert "25.0" in res


def test_histogram_outlier_filtering():
    """Verifica se o filtro de Tukey remove outliers extremos do histograma visual."""
    # 10 amostras normais e 1 outlier extremo (100.0)
    samples = np.array([10.0] * 10 + [100.0])

    # O histograma deve focar nos dados em torno de 10.0
    res = histogram(samples, amplitude=90.0,
                    mvg_average=18.18, resolucao_adc=0.1)

    # Se o outlier fosse incluído, teríamos muitos bins vazios entre 10 e 100
    # Com o filtro, devemos ter poucos bins e o outlier deve ser ignorado na contagem visual
    # (ou cair no bin final se a margem for grande, mas aqui ele é removido dos dados_limpos)
    assert sum(res.values()) == 10  # 10 amostras limpas
    assert "100.0" not in res


def test_histogram_respects_adc_resolution():
    """Verifica se a largura do bin (h_ideal) respeita a resolução mínima do ADC."""
    samples = np.array([10.0, 10.0001, 10.0002]
                       )  # Variação menor que a resolução
    res = histogram(samples, amplitude=0.0002,
                    mvg_average=10.0, resolucao_adc=0.1)

    # Com resolucao_adc=0.1, ele deve criar 1 bin de largura 0.1
    assert len(res) == 1
    assert sum(res.values()) == 3


def test_residuals_empty_list():
    """Deve retornar lista vazia se não houver amostras."""
    assert detrend([]) == []


def test_residuals_single_sample():
    """Deve retornar zero para uma única amostra (sem tendência possível)."""
    samples = [25.5]
    assert detrend(samples) == [0.0]


def test_residuals_perfect_constant_line():
    """Resíduos de uma linha constante devem ser todos zero."""
    samples = [25.0, 25.0, 25.0]
    residuals = detrend(samples)
    assert np.allclose(residuals, [0.0, 0.0, 0.0], atol=1e-10)


def test_residuals_perfect_sloped_line():
    """Resíduos de uma linha perfeitamente inclinada devem ser aproximadamente zero."""
    # y = 2x + 10 -> [10, 12, 14, 16]
    samples = [10.0, 12.0, 14.0, 16.0]
    residuals = detrend(samples)
    # Usamos np.allclose devido a precisão de ponto flutuante
    assert np.allclose(residuals, [0.0, 0.0, 0.0, 0.0], atol=1e-10)


def test_residuals_with_noise():
    """Verifica se os resíduos capturam a variação em torno da tendência."""
    # Dados: [10, 11, 11, 10] -> Média 10.5, Reta de tendência horizontal y=10.5
    # Resíduos esperados: [-0.5, 0.5, 0.5, -0.5]
    samples = [10.0, 11.0, 11.0, 10.0]
    residuals = detrend(samples)
    assert np.isclose(residuals, [-0.5, 0.5, 0.5, -0.5]).all()


def test_numpy_histogram_empty():
    """Deve retornar dict vazio para entrada vazia."""
    res = numpy_histogram(np.array([]))
    assert res == {}


def test_numpy_histogram_limit_bins():
    """Deve limitar o número de bins a no máximo 15."""
    # 5000 amostras normalmente gerariam muito mais que 15 bins com 'auto'
    samples = np.random.normal(loc=10, scale=1, size=5000)
    res = numpy_histogram(samples)
    assert len(res) <= 15
    assert sum(res.values()) == 5000


def test_hybrid_histogram_prefers_numpy_when_small():
    """Deve usar NumPy se o número de bins for pequeno (<= 10)."""
    # Poucos dados -> NumPy deve gerar poucos bins
    samples = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
    res = hybrid_histogram(samples, 0.4, 1.2, 0.1)
    # Com 5 amostras e bins='auto', NumPy provavelmente gera 2-3 bins
    assert len(res) <= 10


def test_hybrid_histogram_prefers_classic_when_numpy_is_dense():
    """Deve preferir o algoritmo clássico se ele resultar em menos bins que o NumPy (quando NumPy > 10)."""
    # Gerar dados que forçam o NumPy a gerar 15 bins
    samples = np.random.normal(loc=25, scale=5, size=5000)

    res_np = numpy_histogram(samples, decimals=1)
    res_classic = histogram(samples, 40.0, 25.0, 0.5, 1)

    res_hybrid = hybrid_histogram(samples, 40.0, 25.0, 0.5, 1)

    # Se ambos foram calculados e o clássico for menor, o híbrido deve ser o clássico
    if len(res_np) >= 10 and len(res_classic) < len(res_np):
        assert len(res_hybrid) == len(res_classic)
    else:
        # Caso contrário (ou se NumPy < 10), deve ser o NumPy
        assert len(res_hybrid) == len(res_np)


def test_hybrid_histogram_avoids_too_few_classic_bins():
    """Verifica se a função híbrida evita usar o clássico quando este resulta em <= 2 bins."""
    # Dados que forçam o NumPy a gerar 15 bins
    samples = np.random.normal(loc=25, scale=5, size=5000)

    # Forçamos uma resolução ADC muito alta para o algoritmo clássico colapsar em 1 ou 2 bins
    # O Freedman-Diaconis vai usar max(h_fd, resolucao_adc)
    res_np = numpy_histogram(samples, decimals=1)  # terá 15 bins

    # Resolução gigante para forçar poucos bins no clássico
    resolucao_gigante = 50.0
    res_classic = histogram(samples, 40.0, 25.0, resolucao_gigante, 1)

    assert len(res_classic) <= 2

    res_hybrid = hybrid_histogram(samples, 40.0, 25.0, resolucao_gigante, 1)

    # Mesmo que len(res_classic) < len(res_np), o híbrido deve recusar o clássico por ter bins insuficientes
    assert len(res_hybrid) == len(res_np)
