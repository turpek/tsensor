import numpy as np


class DataManager:
    def __init__(self, config=None):
        self.sensors = config if config else []
        self.max_rows = 1000
        self.data = []
        self._cache_stats = []
        self._last_processed_len = 0

    def set_max_rows(self, max_rows):
        self.max_rows = max_rows

    def update_config(self, config, max_rows=None):
        self.sensors = config
        if max_rows is not None:
            self.max_rows = max_rows
        # Invalida cache se mudar a config
        self._last_processed_len = -1

    def add_row(self, row):
        try:
            processed_row = [float(val) for val in row]
            self.data.append(processed_row)
            if len(self.data) > self.max_rows:
                self.data = self.data[-self.max_rows:]
            return True
        except (ValueError, TypeError):
            return False

    def get_statistics(self):
        if not self.data:
            return []

        # Otimização: Se o número de amostras não mudou, retorna o cache
        # Isso evita cálculos pesados de NumPy em cada polling do browser
        if len(self.data) == self._last_processed_len:
            return self._cache_stats

        arr = np.array(self.data)
        stats = []
        for i in range(len(self.sensors)):
            col_idx = i + 1
            if col_idx >= arr.shape[1]:
                continue
            col_data = arr[:, col_idx]
            mean = np.mean(col_data)
            stats.append({
                "name": self.sensors[i]["name"],
                "type": self.sensors[i]["type"],
                "min": float(np.min(col_data)),
                "max": float(np.max(col_data)),
                "mean": float(mean),
                "std": float(np.std(col_data)),
                "samples": int(len(col_data)),
                "residuals": (col_data - mean).tolist()
            })

        self._cache_stats = stats
        self._last_processed_len = len(self.data)
        return stats

    def get_all_data(self):
        return self.data
