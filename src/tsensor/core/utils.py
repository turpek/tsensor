from datetime import datetime
from math import ceil
from typing import Optional
import numpy as np
import os
import toml

# Caminho absoluto para o arquivo de configuração
CONFIG_PATH = os.path.join(os.getcwd(), "config.toml")

# Template padrão para inicialização do sistema
DEFAULT_CONFIG = {
    "hardware": {
        "port": "/dev/ttyUSB0",
        "baudrate": 115200,
        "timeout": 1.0,
        "mcu": "esp32",
    },
    "sensor": {
        "type": "LM35",
        "adc_max": 4095,
        "v_ref": 3.3,
    },
    "acquisition": {
        "total_samples": 1000000,
        "buffer_samples": 1000,
        "max_runtime_sec": 1800,
    },
    "presentation": {
        "log_level": "INFO",
        "decimal_places": 1,
        "update_interval_ms": 1000,
        "flask_port": 5000,
        "debug_mode": False,
    },
    "exporter": {
        "google_drive": {
            "credentials_file": "credentials.json",
            "token_file": "token.json",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
            "file_name": "tsensor_data",
        }
    },
}

# Única fonte de presets para microcontroladores
MCU_PRESETS = {
    "arduino_uno": {"adc_max": 1023, "v_ref": 1.1},
    "esp32": {"adc_max": 4095, "v_ref": 3.3},
}


def timestamp() -> str:
    """Retorna timestamp no formato HH:MM:SS:mmm."""
    return datetime.now().strftime("%H:%M:%S:%f")[:-3]


def load_config() -> dict:
    """Carrega as configurações do arquivo TOML ou usa o template padrão."""
    if not os.path.exists(CONFIG_PATH):
        # Se não existir, retorna uma cópia profunda do template padrão
        import copy

        return copy.deepcopy(DEFAULT_CONFIG)

    with open(CONFIG_PATH, "r") as f:
        config = toml.load(f)

    # Resolve os padrões baseados no MCU para garantir integridade
    mcu_type = config.get("hardware", {}).get("mcu", "arduino_uno")
    preset = MCU_PRESETS.get(mcu_type, MCU_PRESETS["arduino_uno"])

    if "sensor" not in config:
        config["sensor"] = {}

    config["sensor"].setdefault("adc_max", preset["adc_max"])
    config["sensor"].setdefault("v_ref", preset["v_ref"])

    return config


def save_config(config_dict: dict) -> None:
    """Salva as configurações de volta no arquivo TOML."""
    with open(CONFIG_PATH, "w") as f:
        toml.dump(config_dict, f)


def detrend(samples: list[float]) -> list[float]:

    if not samples:
        return []
    elif len(samples) == 1:
        return [0.0]

    y_temperature = np.array(samples)
    x_time = np.arange(len(y_temperature))
    coefficient = np.polyfit(x_time, y_temperature, 1)
    line = np.poly1d(coefficient)
    y_projected = line(x_time)

    residuals = y_temperature - y_projected
    return residuals.tolist()


def histogram(
    samples: np.ndarray,
    amplitude: float,
    mvg_average: float,
    resolucao_adc: float,
    decimal_label: int = 1
) -> dict[str, int]:
    """Calcula o histograma otimizado com comportamento clássico e performance NumPy."""
    n = samples.size
    if n == 0:
        return {}
    if amplitude == 0:
        return {f"{mvg_average:.{decimal_label}f}": n}

    # Ordenação rápida (O(N log N) em C) para garantir quartis por índice
    data = np.sort(samples)

    # Seleção de quartis por índice (Comportamento Clássico - evita interpolação)
    q1 = data[n // 4]
    q3 = data[(n * 3) // 4]
    iqr = q3 - q1

    iqr_seguro = max(iqr, resolucao_adc)
    margem = 2.0 * iqr_seguro
    limite_inferior = q1 - margem
    limite_superior = q3 + margem

    # Filtro de Tukey vetorizado
    mask = (data >= limite_inferior) & (data <= limite_superior)
    dados_limpos = data[mask]

    if dados_limpos.size == 0:
        dados_limpos = data

    min_visual = float(dados_limpos[0])
    max_visual = float(dados_limpos[-1])
    amplitude_visual = max_visual - min_visual

    # Binning de Freedman-Diaconis
    h_fd = 2.0 * iqr_seguro / (n ** (1 / 3))
    h_ideal = max(h_fd, resolucao_adc)

    k = max(1, ceil(amplitude_visual / h_ideal))
    h_real = amplitude_visual / k if amplitude_visual > 0 else h_ideal

    # Contagem ultra-rápida via NumPy (substitui o loop Python)
    counts, _ = np.histogram(dados_limpos, bins=k,
                             range=(min_visual, max_visual))

    labels_list = [
        f"{(min_visual + i * h_real):.{decimal_label}f}" for i in range(k)
    ]

    return dict(zip(labels_list, counts.tolist()))


class Stat:
    def __init__(self, total_samples: int):
        self._total_count = 0
        self._tc_samples = 0
        self._total_samples = total_samples
        self._moving_sum = 0.0
        self._moving_average = 0.0
        self._mean = 0.0
        self._max = -float("inf")
        self._min = float("inf")
        self.__m2 = 0.0
        self.__old_shift = 0.0
        self.__new_shift = 0.0

    def _update_shift_and_mean(self, data: float) -> None:
        self.__old_shift = data - self._mean
        self._mean += self.__old_shift / self._total_count
        self.__new_shift = data - self.mean
        self.__m2 += self.__new_shift * self.__old_shift

    def __maintain_window(self, old_date) -> None:
        if old_date and self._total_samples >= self._tc_samples:
            self._moving_sum -= old_date
            self._tc_samples -= 1

    def _update_stats(self, data: float) -> None:
        self._moving_sum += data
        self._total_count += 1
        self._tc_samples += 1
        self._update_shift_and_mean(data)
        self._max = max(data, self._max)
        self._min = min(data, self._min)
        self._moving_average = self._moving_sum / self._tc_samples

    def update(self, new_data: float, old_date: Optional[float] = None) -> None:
        self.__maintain_window(old_date)
        self._update_stats(new_data)

    def clear(self, total_samples: Optional[int] = None) -> None:
        self._max = 0.0
        self._total_count = 0
        self._tc_samples = 0
        self._moving_sum = 0.0
        self._moving_average = 0.0
        self._mean = 0.0
        self._max = -float("inf")
        self._min = float("inf")
        self.__m2 = 0.0
        self.__old_shift = 0.0
        self.__new_shift = 0.0

        if total_samples:
            self._total_samples = total_samples

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def moving_average(self) -> float:
        return self._moving_average

    @property
    def std(self) -> float:
        if self._total_count > 1:
            n = self._total_count
            return np.sqrt(self.__m2 / (n - 1))
        return 0.0

    @property
    def max(self) -> float:
        return self._max

    @property
    def min(self) -> float:
        return self._min

    @property
    def amplitude(self) -> float:
        if self._total_count > 0:
            return self.max - self.min
        return 0.0

    @property
    def is_full(self) -> bool:
        return self._total_samples == self._tc_samples
