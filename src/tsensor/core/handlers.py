from abc import ABC, abstractmethod
from loguru import logger
from math import log
from time import time
from typing import Protocol, Optional, Iterator
from tsensor.core.data_stream import DataStream
from tsensor.core.utils import TSSync

import re

REG_ADC_VALUE = r"(\d+\.\d+|\d+)"


sync_time = TSSync()


class SerialHandler(Protocol):
    """Qualquer classe com esses método será considerada um SerialParser"""

    def __init__(
        self,
        data: DataStream,
        data_buffer: DataStream,
        time_series: DataStream,
        adc_max: int,
        v_ref: float,
    ):
        ...

    def convert(self, line: str) -> float | str:
        ...

    def update(self, line: str | float) -> bool:
        ...

    @property
    def data(self) -> DataStream:
        ...

    @property
    def data_buffer(self) -> DataStream:
        ...

    @property
    def time_series(self) -> DataStream:
        ...


class SheetsHandler:

    def __init__(
        self,
        data: DataStream,
        data_buffer: DataStream,
        time_series: DataStream,
        name: str,
        adc_max: int,
        v_ref: float,
    ):
        self._data = data
        self._data_buffer = data_buffer
        self._time_series = time_series
        self._name = name

    def update(self, line: Iterator) -> bool:
        line = float(next(line))
        logger.debug(f"{self._name}: {line:.4f}")
        self._data.add(line)
        self._data_buffer.add(line)
        return True

    def str_to_float(self, line: str) -> None | float:
        try:
            return float(line)
        except (ValueError, TypeError):
            return None

    def convert(self, line: str) -> float | str:
        val = self.str_to_float(line)
        if val is not None:
            return val
        return ""

    @property
    def data_buffer(self) -> DataStream:
        return self._data_buffer

    @property
    def data(self) -> DataStream:
        return self._data

    @property
    def time_series(self) -> DataStream:
        return self._time_series


class PressureHandler(ABC):
    def __init__(
        self,
        data: DataStream,
        data_buffer: DataStream,
        time_series: DataStream,
        adc_max: int,
        v_ref: float,
        offset: float = 22.6,
        sensitivity: float = 1.25
    ):
        self._data = data
        self._data_buffer = data_buffer
        self._time_series = time_series
        self._adc_max = adc_max
        self._v_ref = v_ref
        self._offset = offset
        self._sensitivity = sensitivity
        self._re = re.compile(f"P={REG_ADC_VALUE}")

    def str_to_float(self, line: str) -> None | float:
        match = self._re.search(line)
        if match:
            return float(match.group(1))
        else:
            logger.warning(
                f"Ruído ou padrão 'P=' não encontrado na linha: '{line}'")
        return None

    @abstractmethod
    def _convert(self, adc: float):
        ...

    def convert(self, line: str) -> float | str:
        val = self.str_to_float(line)
        if val is not None:
            pressure = self._convert(val)
            logger.debug(f"pressao: {pressure:.4f}")
            return pressure
        return ""

    def update(self, line: str) -> bool:
        if line:
            val = float(line)
            self._data.add(val)
            self._data_buffer.add(val)
            return True
        return False

    @property
    def data_buffer(self) -> DataStream:
        return self._data_buffer

    @property
    def data(self) -> DataStream:
        return self._data

    @property
    def time_series(self) -> DataStream:
        return self._time_series


class TemperatureHandler(ABC):
    def __init__(
        self,
        data: DataStream,
        data_buffer: DataStream,
        time_series: DataStream,
        adc_max: int,
        v_ref: float,
    ):
        self._data = data
        self._data_buffer = data_buffer
        self._time_series = time_series
        self._adc_max = adc_max
        self._v_ref = v_ref
        self._re = re.compile(f"T={REG_ADC_VALUE}")

    def str_to_float(self, line: str) -> None | float:
        match = self._re.search(line)
        if match:
            return float(match.group(1))
        else:
            logger.warning(
                f"Ruído ou padrão 'T=' não encontrado na linha: '{line}'")
        return None

    def _check_adc(self, adc: float) -> bool:
        return 0 <= adc <= self._adc_max

    def convert(self, line: str) -> float | str:
        val = self.str_to_float(line)
        if val is not None:
            temperature = self._convert(val)
            logger.debug(f"temperatura: {temperature:.4f}")
            return temperature
        return ""

    @abstractmethod
    def _convert(self, adc: float):
        ...

    def update(self, line: str) -> bool:
        if line:
            val = float(line)
            self._data.add(val)
            self._data_buffer.add(val)
            return True
        return False

    @property
    def data_buffer(self) -> DataStream:
        return self._data_buffer

    @property
    def data(self) -> DataStream:
        return self._data

    @property
    def time_series(self) -> DataStream:
        return self._time_series


class NTCHandler(TemperatureHandler):
    def _convert(self, adc: float):
        V = adc * self._v_ref / self._adc_max
        Rfixo = 10000.0

        Rntc = Rfixo * (V / (self._v_ref - V))

        B = 3950
        T0 = 298.15
        R0 = 10000

        T = 1 / ((1 / T0) + (1 / B) * log(Rntc / R0))
        temp = T - 273.15
        return round(temp, 4)


class LM35Handler(TemperatureHandler):
    def _convert(self, adc: float):
        tensao = (adc * self._v_ref) / (self._adc_max)
        temp = tensao * 100.0
        return round(temp, 4)


class MPS20Handler(PressureHandler):
    def _convert(self, adc: float):
        # B = 128  # ganho
        # adc_max = 2 ** 24
        # v_ref_milli = self._v_ref * 1000
        # v_sensor_mv = (adc * v_ref_milli) / (B * adc_max)
        # press = (v_sensor_mv) / self._sensitivity
        offset = 4075138
        escala = 0.001313
        press = (adc - offset) * escala / 1e3
        return round(press, 4)


class RadarDataHandler:
    def __init__(
        self,
        data: Optional[DataStream] = None,
        data_buffer: Optional[DataStream] = None,
        time_series: Optional[DataStream] = None,
        adc_max: int = 4095,
        v_ref: float = 3.3,
        prefix: str = "A"
    ):
        self._data = data if data else DataStream(total_samples=1000000)
        self._data_buffer = data_buffer if data_buffer else DataStream(total_samples=1)
        self._time_series = time_series if time_series else DataStream(total_samples=1)
        self._adc_max = adc_max
        self._v_ref = v_ref
        self.prefix = prefix
        self.value: int = 0
        self._re = re.compile(f"{prefix}={REG_ADC_VALUE}")

    def str_to_float(self, line: str) -> None | float:
        match = self._re.search(line)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                return None
        return None

    def _check_adc(self, adc: float) -> bool:
        return 0 <= adc <= self._adc_max

    def update(self, line: str) -> bool:
        if line:
            val = float(line)
            self._data.add(val)
            self._data_buffer.add(val)
            return True
        return False

    def convert(self, line: str) -> float | str:
        val = self.str_to_float(line)
        if val is not None:
            return self._convert(val)
        return ""

    @property
    def data(self) -> DataStream:
        return self._data

    @property
    def data_buffer(self) -> DataStream:
        return self._data_buffer

    @property
    def time_series(self) -> DataStream:
        return self._time_series


class RadarAngleHandler(RadarDataHandler):
    def __init__(self, *args, **kwargs):
        if "prefix" not in kwargs:
            kwargs["prefix"] = "A"
        super().__init__(*args, **kwargs)

    def _convert(self, adc: float):
        angle = float(adc)
        logger.debug(f"angle: {angle:.4f}")
        return angle


class RadarDistanceHandler(RadarDataHandler):
    def __init__(self, *args, **kwargs):
        if "prefix" not in kwargs:
            kwargs["prefix"] = "D"
        super().__init__(*args, **kwargs)

    def _convert(self, adc: float):
        dist = float(adc)
        logger.debug(f"distancia: {adc:.4f}")
        return dist


class TimestampHandler:
    _re = re.compile(f"U={REG_ADC_VALUE}")

    def __init__(
        self,
        data: DataStream,
        data_buffer: DataStream,
        time_series: DataStream,
        name: str,
        adc_max: int,
        v_ref: float,
    ):
        self._data = data
        self._data_buffer = data_buffer
        self._time_series = time_series
        self._name = name

    @classmethod
    def convert_raw(cls, line: str) -> float | None:
        """Extrai o timestamp bruto (U=...) da linha."""
        match = cls._re.search(line)
        if match:
            return float(match.group(1))
        return None

    def str_to_float(self, line: str) -> None | float:
        return self.convert_raw(line)

    def _convert(self, val: float) -> float | str:
        ts = sync_time.get_real(val)
        logger.debug(f"timestamp: {ts:.4f}")
        return ts

    def convert(self, line: str) -> float | str:
        val = self.str_to_float(line)
        if val is not None:
            return self._convert(val)
        return time()

    def update(self, line: str) -> bool:
        if line:
            val = float(line)
            self._data.add(val)
            self._data_buffer.add(val)
            return True
        return False

    @property
    def data_buffer(self) -> DataStream:
        return self._data_buffer

    @property
    def data(self) -> DataStream:
        return self._data

    @property
    def time_series(self) -> DataStream:
        return self._time_series


class StreamManager:
    def __init__(self):
        self._timeout: Optional[int]
        self._start: float
        self._active: bool
        self._handlers: dict[str, SerialHandler] = {}
        self._total_samples: Optional[int]
        self._count: int

    def configure(
        self,
        timeout: Optional[int] = None,
        total_samples: Optional[int] = None,
    ):
        self._timeout = timeout
        self._start = time()
        self._active = True
        self._handlers = {}
        self._total_samples = total_samples
        self._count = 0

    def __len__(self) -> int:
        """Retorna a quantidade de handlers."""
        return len(self._handlers)

    def add_handler(self, name: str, handler: SerialHandler) -> None:
        self._handlers[name] = handler

    def get_handler(self, name: str) -> None | SerialHandler:
        return self._handlers.get(name)

    def validate(self, line: str) -> bool:
        """Verifica se todos os handler's reconhecem os dados na linha."""
        if not isinstance(line, str):
            return False
        for handler in self._handlers.values():
            if handler.str_to_float(line) is None:
                return False
        return True

    def dispatch(self, row: list) -> None:
        # row é a linha da planilha [colunaA, colunaB, ...]
        # zip pareia cada handler com seu valor correspondente na linha
        for handler, val in zip(self._handlers.values(), row):
            handler.update(val)
        self._count += 1

    def stop(self) -> None:
        self._active = False

    @property
    def count_samples(self) -> int:
        return self._count

    @property
    def is_active(self) -> bool:
        # Se houver timeout, verifica o tempo decorrido
        if self._timeout is not None and (time() - self._start > self._timeout):
            return False

        # Se houver limite de amostras, verifica a contagem
        # if isinstance(self._total_samples, int) and self._count >= self._total_samples:
        #     return False

        return self._active


class SerialManager:
    def __init__(self):
        self._handlers: dict[str, SerialHandler] = {}
        self.table: list[list] = []
        self._timeout: Optional[int] = None
        self._start: float = time()
        self._active: bool = False

    def configure(self, timeout: Optional[int] = None):
        self._timeout = timeout
        self._start = time()
        self._active = True
        self._handlers = {}
        self.table = []

    def add_handler(self, name: str, handler: SerialHandler) -> None:
        self._handlers[name] = handler

    def dispatch(self, line: str) -> None:
        # Cria a linha chamando convert em cada handler
        row = [h.convert(line) for h in self._handlers.values()]

        # O primeiro elemento é o timestamp.
        # Só adicionamos a linha se houver pelo menos um dado de sensor real.
        if any(val != "" for val in row[1:]):
            self.table.append(row)

    def stop(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        if self._timeout is not None and (time() - self._start > self._timeout):
            return False
        return self._active

    def __len__(self) -> int:
        return len(self._handlers)


# Mapeamento global de handlers disponíveis para configuração via TOML
HANDLERS = {
    "LM35": LM35Handler,
    "NTC": NTCHandler,
    "MPS20N0040D": MPS20Handler,
    "RADAR_ANGLE": RadarAngleHandler,
    "RADAR_DISTANCE": RadarDistanceHandler,
}
