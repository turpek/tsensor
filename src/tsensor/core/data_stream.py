from collections import deque
from datetime import datetime
from math import sqrt, floor
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
        self._max = -float('inf')
        self._min = float('inf')
        self.__m2 = 0.0
        self.__old_shift = 0.0
        self.__new_shift = 0.0

    def __len__(self) -> int:
        return len(self._data)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S:%f")[:-3]

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

    def _get_labels(
            self,
            decimal_label: int,
            width: float,
            bins: int,
            min_bins: int,
    ) -> tuple[int, float, list[str], float]:
        w_art = 10 ** (-decimal_label)
        if width > w_art:
            return (
                bins,
                width,
                [
                    f'{(self.min + i * width):.{decimal_label}f}' for i in range(bins)
                ],
                self.min,
            )

        left_offset = min_bins // 2
        start_val = self.min - (left_offset * w_art)
        return (
            min_bins,
            w_art,
            [
                f'{(start_val + i * w_art):.{decimal_label}f}' for i in range(min_bins)
            ],
            start_val
        )

    def add(self, data: float) -> None:
        with self._lock:
            self._maintain_window()
            timestamp = self._timestamp()
            self._data.append((timestamp, data))
            self._update_stats(data)

    def clear(self) -> None:
        self._data.clear()
        self._max = 0.0
        self._total_count = 0
        self._moving_sum = 0.0
        self._moving_average = 0.0
        self._mean = 0.0
        self._max = -float('inf')
        self._min = float('inf')
        self.__m2 = 0.0
        self.__old_shift = 0.0
        self.__new_shift = 0.0

    def histogram(
        self,
        decimal_label: int = 1,
        min_bins: int = 5,
        max_bins: int = 30,
    ) -> dict[str, int]:

        if self.amplitude == 0:
            return {f'{self.min:.{decimal_label}f}': len(self)}

        k = min(int(sqrt(len(self))), max_bins)
        k = max(k, min_bins)
        h = self.amplitude / k

        k, h, labels_list, min_ = self._get_labels(decimal_label, h, int(k), min_bins)
        histogram = {label: 0 for label in labels_list}
        for _, data in self.sample:
            idx = max(0, floor((data - min_) / h))
            if idx >= k:
                idx = k - 1
            label = labels_list[idx]
            histogram[label] += 1
        return histogram

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
