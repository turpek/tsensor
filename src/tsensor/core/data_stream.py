from collections import deque
from tsensor.core.utils import hybrid_histogram, Stat
from threading import Lock
from typing import Optional

import numpy as np


class DataStream(Stat):
    def __init__(self, total_samples: int):
        super().__init__(total_samples)

        self._lock = Lock()
        self._data: deque[float] = deque()
        self._ts: deque[str] = deque()

    def __len__(self) -> int:
        return len(self._data)

    def _maintain_window(self) -> None | float:
        if self.is_full:
            old_data = self._data.popleft()
            return old_data

    def add(self, data: float, timestamp: str) -> None:
        with self._lock:
            old_data = self._maintain_window()
            self._data.append(data)
            self._ts.append(timestamp)
            self.update(data, old_data)

    def clear(self, total_samples: Optional[int] = None) -> None:
        self._data.clear()
        super().clear(total_samples)

    def histogram(
        self,
        resolucao_adc: float,
        decimal_label: int = 1,
    ) -> dict[str, int]:
        data = np.array([d for d in self.samples])
        return hybrid_histogram(
            data,
            self.amplitude,
            self.moving_average,
            resolucao_adc,
            decimal_label
        )

    @property
    def samples(self) -> deque[float]:
        return self._data

    @property
    def timestamp(self) -> deque[str]:
        return self._ts
