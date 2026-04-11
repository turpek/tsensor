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
        temporal_data: DataStream,
        samples: int,
        timeout: int,
        adc_max: int,
        v_ref: float,
    ):
        ...

    def handle(self, line: str) -> bool:
        ...

    @property
    def data(self) -> DataStream:
        ...

    @property
    def temporal_data(self) -> DataStream:
        ...


class TemperatureHandler(ABC):
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
            self._temporal_data.add(temperature, time_now)
            return True
        return False

    @property
    def temporal_data(self) -> DataStream:
        return self._temporal_data

    @property
    def data(self) -> DataStream:
        return self._data


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


class StreamManager:
    def __init__(
        self,
        samples: int,
        timeout: int,
        adc_max: int,
        v_ref: float,
        total_samples: Optional[int] = None,
    ):
        self._samples = samples
        self._timeout = timeout
        self._start = time()
        self._adc_max = adc_max
        self._v_ref = v_ref
        self._active = True
        self._handlers: dict[str, SerialHandler] = {}
        self._total_samples = total_samples
        self._count = 0

    def add_handler(
        self,
        name: str,
        cls_handler: type[SerialHandler],
        data: DataStream,
        temporal_data: DataStream,
    ) -> None:

        self._handlers[name] = cls_handler(
            data,
            temporal_data,
            self._samples,
            self._timeout,
            self._adc_max,
            self._v_ref,
        )

    def get_handler(self, name: str) -> None | SerialHandler:
        return self._handlers.get(name)

    def dispatch(self, line: str) -> None:
        for handler in self._handlers.values():
            if handler.handle(line):
                self._count += 1

    def stop(self) -> None:
        self._active = False

    @property
    def count_samples(self) -> int:
        return self._count

    @property
    def is_active(self) -> bool:
        if time() - self._start > self._timeout:
            return False
        elif (
            isinstance(self._total_samples,
                       int) and self._count >= self._total_samples
        ):
            return False
        return self._active


# Mapeamento global de handlers disponíveis para configuração via TOML
HANDLERS = {
    "LM35": LM35Handler,
    "NTC": NTCHandler,
}
