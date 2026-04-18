from abc import ABC, abstractmethod
from loguru import logger
from math import log
from time import time
from typing import Protocol, Optional
from tsensor.core.data_stream import DataStream
from tsensor.core.utils import timestamp

import re

REG_ADC_VALUE = r"(\d+)"


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

    def handle(self, line: str | float) -> bool:
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

    def handle(self, line: str, timestamp: str = '') -> bool:
        line = float(line)
        logger.debug(f"{self._name}: {line:.4f}")
        self._data.add(line, timestamp)
        self._data_buffer.add(line, timestamp)
        return True

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
        sensitivity: float = 1.6949
    ):
        self._data = data
        self._data_buffer = data_buffer
        self._time_series = time_series
        self._adc_max = adc_max
        self._v_ref = v_ref
        self._offset = offset
        self._sensitivity = sensitivity
        self._re = re.compile(f"P={REG_ADC_VALUE}")

    def _str_to_int(self, line: str) -> None | int:
        match = self._re.search(line)
        if match:
            return int(match.group(1))
        else:
            logger.warning(
                f"Ruído ou padrão 'P=' não encontrado na linha: '{line}'")
        return None

    @abstractmethod
    def _convert(self, adc: int):
        ...

    def handle(self, line: str) -> bool:
        adc = self._str_to_int(line)
        if adc is not None:
            pressure = self._convert(adc)
            time_now = timestamp()
            logger.debug(f"pressao: {pressure:.4f}")
            self._data.add(pressure, time_now)
            self._data_buffer.add(pressure, time_now)
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

    def _str_to_int(self, line: str) -> None | int:
        match = self._re.search(line)
        if match:
            return int(match.group(1))
        else:
            logger.warning(
                f"Ruído ou padrão 'T=' não encontrado na linha: '{line}'")
        return None

    def _check_adc(self, adc: int) -> bool:
        return 0 < adc < self._adc_max

    @abstractmethod
    def _convert(self, adc: int):
        ...

    def handle(self, line: str) -> bool:
        adc = self._str_to_int(line)
        if adc is not None and self._check_adc(adc):
            temperature = self._convert(adc)
            time_now = timestamp()
            logger.debug(f"temperatura: {temperature:.4f}")
            self._data.add(temperature, time_now)
            self._data_buffer.add(temperature, time_now)
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
    def _convert(self, adc: int):
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
    def _convert(self, adc: int):
        tensao = (adc * self._v_ref) / (self._adc_max)
        temp = tensao * 100.0
        return round(temp, 4)


class MPS20Handler(PressureHandler):
    def _convert(self, adc: int):
        B = 128  # ganho
        adc_max = 2 ** 24
        v_ref_milli = self._v_ref * 1000
        v_sensor_mv = (adc * v_ref_milli) / (B * adc_max)
        press = (v_sensor_mv) / self._sensitivity
        return round(press, 4)


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

    def dispatch(self, line: str) -> None:
        counts = [self._count]
        for handler in self._handlers.values():
            handler.handle(line)
            counts.append(len(handler.data))
        self._count = max(counts)

    def dispatch_sheets(self, line: str) -> None:
        counts = [self._count]
        ts = line[0]
        for handler, col in zip(self._handlers.values(), line[1:]):
            handler.handle(col, ts)
            counts.append(len(handler.data))
        self._count = max(counts)

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
        if isinstance(self._total_samples, int) and self._count >= self._total_samples:
            return False

        return self._active


# Mapeamento global de handlers disponíveis para configuração via TOML
HANDLERS = {
    "LM35": LM35Handler,
    "NTC": NTCHandler,
    "MPS20N0040D": MPS20Handler,
}
