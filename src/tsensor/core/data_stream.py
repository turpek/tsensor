from collections import deque
from tsensor.core.utils import numpy_histogram, Stat
from threading import Lock
from typing import Optional

import numpy as np


class DataStream(Stat):
    def __init__(self, total_samples: int):
        super().__init__(total_samples)

        self._lock = Lock()
        self._data: deque[tuple[str, float]] = deque()

    def __len__(self) -> int:
        return len(self._data)

    def _maintain_window(self) -> None | float:
        if self.is_full:
            _, old_data = self._data.popleft()
            return old_data

    def add(self, data: float, timestamp: str) -> None:
        with self._lock:
            old_data = self._maintain_window()
            self._data.append((timestamp, data))
            self.update(data, old_data)

    def clear(self, total_samples: Optional[int] = None) -> None:
        self._data.clear()
        super().clear(total_samples)

    def histogram(
        self,
        resolucao_adc: float,  # Mantido apenas para compatibilidade de assinatura se necessário
        decimal_label: int = 1,
    ) -> dict[str, int]:
        data = np.array([d for d in self.data])
        return numpy_histogram(data, decimals=decimal_label)

    @property
    def sample(self) -> list:
        with self._lock:
            return list(self._data)

    @property
    def data(self) -> list:
        with self._lock:
            return [d[1] for d in self._data]
