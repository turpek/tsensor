from collections import deque
from math import ceil, sqrt
from threading import Lock


class DataStream:
    def __init__(self, total_samples: int):
        self._lock = Lock()
        self._total_count = 0
        self._total_samples = total_samples
        self._data: deque[tuple[str, float]] = deque()
        self._moving_sum = 0.0
        self._moving_average = 0.0
        self._mean = 0.0
        self._max = -float("inf")
        self._min = float("inf")
        self.__m2 = 0.0
        self.__old_shift = 0.0
        self.__new_shift = 0.0

    def __len__(self) -> int:
        return len(self._data)

    def _update_shift_and_mean(self, data: float) -> None:
        self.__old_shift = data - self._mean
        self._mean += self.__old_shift / self._total_count
        self.__new_shift = data - self.mean
        self.__m2 += self.__new_shift * self.__old_shift

    def _update_stats(self, data: float) -> None:
        self._moving_sum += data
        self._total_count += 1
        self._update_shift_and_mean(data)
        self._max = max(data, self._max)
        self._min = min(data, self._min)
        self._moving_average = self._moving_sum / len(self)

    def _maintain_window(self) -> None:
        if self._total_samples == len(self):
            _, oldest = self._data.popleft()
            self._moving_sum -= oldest

    def add(self, data: float, timestamp: str) -> None:
        with self._lock:
            self._maintain_window()
            self._data.append((timestamp, data))
            self._update_stats(data)

    def clear(self) -> None:
        self._data.clear()
        self._max = 0.0
        self._total_count = 0
        self._moving_sum = 0.0
        self._moving_average = 0.0
        self._mean = 0.0
        self._max = -float("inf")
        self._min = float("inf")
        self.__m2 = 0.0
        self.__old_shift = 0.0
        self.__new_shift = 0.0

    def histogram(
        self,
        resolucao_adc: float,
        decimal_label: int = 1,
    ) -> dict[str, int]:

        n = len(self.sample)
        if n == 0:
            return {}
        if self.amplitude == 0:
            return {f"{self.moving_average:.{decimal_label}f}": n}

        temperaturas = [dado for _, dado in self.sample]
        temperaturas.sort()

        q1_idx = n // 4
        q3_idx = (n * 3) // 4
        q1 = temperaturas[q1_idx]
        q3 = temperaturas[q3_idx]
        iqr = q3 - q1

        # --- FILTRO DE OUTLIERS DE TUKEY ---
        # Multiplicador 1.5 ou 2.0 (2.0 é mais tolerante e evita cortar dados válidos)
        margem = 2.0 * iqr
        limite_inferior = q1 - margem
        limite_superior = q3 + margem

        dados_limpos = [
            x for x in temperaturas if limite_inferior <= x <= limite_superior
        ]

        # Se por acaso filtrar tudo (muito raro), aborta e usa o normal
        if not dados_limpos:
            dados_limpos = temperaturas

        min_visual = dados_limpos[0]
        max_visual = dados_limpos[-1]
        amplitude_visual = max_visual - min_visual

        if iqr > 0:
            h_fd = 2 * iqr / (n ** (1 / 3))
        else:
            h_fd = 0.1

        resolucao_adc = 0.1074
        h_ideal = max(h_fd, resolucao_adc)

        k = max(5, ceil(amplitude_visual / h_ideal))
        h_real = amplitude_visual / k if k > 0 else h_ideal

        labels_list = [
            f"{(min_visual + i * h_real):.{decimal_label}f}" for i in range(k)
        ]
        histograma_dit = {label: 0 for label in labels_list}

        for data in dados_limpos:
            idx = max(0, min(int((data - min_visual) / h_real), k - 1))
            histograma_dit[labels_list[idx]] += 1

        return histograma_dit

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
            return sqrt(self.__m2 / (n - 1))
        return 0.0

    @property
    def max(self) -> float:
        return self._max

    @property
    def min(self) -> float:
        return self._min

    @property
    def amplitude(self) -> float:
        return self.max - self.min

    @property
    def sample(self) -> list:
        with self._lock:
            return list(self._data)

    @property
    def is_full(self) -> bool:
        return self._total_samples == len(self)
