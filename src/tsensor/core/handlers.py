from loguru import logger
from math import log
from time import time
from typing import Protocol
from tsensor.core.data_stream import DataStream
from tsensor.core.utils import timestamp


class SerialHandler(Protocol):
    """Qualquer classe com esses método será considerada um SerialParser"""

    def handle(self, line: str) -> None:
        ...

    @property
    def is_active(self) -> bool:
        ...

    @property
    def data(self) -> DataStream:
        return self._data


class NTCHandler:

    def __init__(
        self,
        data: DataStream,
        temporal_data: DataStream,
        samples: int,
        timeout: int,
        adc_max: int,
        v_ref: float,
    ):
        self._data = data
        self._temporal_data = temporal_data
        self._samples = samples
        self._timeout = timeout
        self._start = time()
        self._adc_max = adc_max
        self._v_ref = v_ref

    def _str_to_int(self, line: str) -> None | int:
        try:
            return int(line)
        except Exception as err:
            logger.error(f'Falha ao converter {line}. Exceção "{err}"')
        return None

    def _check_adc(self, adc: int) -> bool:
        return 0 < adc < self._adc_max

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

    def handle(self, line: str) -> None:
        adc = self._str_to_int(line)
        if adc is not None and self._check_adc(adc):
            temperature = self._convert(adc)
            time_now = timestamp()
            logger.debug(f'temperatura: {temperature:.4f}')
            self._data.add(temperature, time_now)
            self._temporal_data.add(temperature, time_now)

    @property
    def is_active(self) -> bool:
        if time() - self._start > self._timeout:
            return False
        elif len(self._data) >= self._samples:
            return False
        return True

    @property
    def temporal_data(self) -> DataStream:
        return self._temporal_data

    @property
    def data(self) -> DataStream:
        return self._data


class LM35Handler:

    def __init__(
        self,
        data: DataStream,
        temporal_data: DataStream,
        samples: int,
        timeout: int,
        adc_max: int,
        v_ref: float,
    ):
        self._data = data
        self._temporal_data = temporal_data
        self._samples = samples
        self._timeout = timeout
        self._start = time()
        self._adc_max = adc_max
        self._v_ref = v_ref

    def _str_to_float(self, line: str) -> None | float:
        try:
            return float(line)
        except Exception as err:
            logger.debug(f'Falha ao converter {line}. Exceção "{err}"')
        return None

    def _check_adc(self, adc: int) -> bool:
        return 0 < adc < self._adc_max

    def _convert(self, adc: float):
        tensao = (adc * self._v_ref) / (self._adc_max)
        temp = tensao * 100.0
        return round(temp, 4)

    def handle(self, line: str) -> None:
        adc = self._str_to_float(line)
        if adc is not None and self._check_adc(adc):
            temperature = self._convert(adc)
            time_now = timestamp()
            logger.debug(f'temperatura: {temperature:.4f}')
            self._data.add(temperature, time_now)
            self._temporal_data.add(temperature, time_now)

    @property
    def is_active(self) -> bool:
        if time() - self._start > self._timeout:
            return False
        elif len(self._data) >= self._samples:
            return False
        return True

    @property
    def temporal_data(self) -> DataStream:
        return self._temporal_data

    @property
    def data(self) -> DataStream:
        return self._data
