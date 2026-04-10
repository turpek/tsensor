from loguru import logger
from serial import Serial
from tsensor.core.handlers import SerialHandler


def serial_reading(
    port: str, baudrate: int, samples: int, handler: SerialHandler, timeout: int = 1
) -> None:
    ser = Serial(port, baudrate, timeout=timeout)
    logger.info("Iniciando coleta...")

    while handler.is_active:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line.startswith("T="):
            # Passa apenas o valor numérico após o 'T='
            handler.handle(line[2:])
        elif line:
            logger.debug(f"Descartando dado fora do protocolo: {line!r}")

    ser.close()
    logger.info(f"Coleta finalizada: {len(handler.data)} amostras")
