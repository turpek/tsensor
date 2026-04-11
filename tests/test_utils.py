import numpy as np
from tsensor.core.utils import detrend


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
    assert np.allclose(residuals, [-0.5, 0.5, 0.5, -0.5])
