from loguru import logger
from serial import Serial
from tsensor.core.handlers import SerialHandler


def serial_reading(
    port: str,
    baudrate: int,
    samples: int,
    handler: SerialHandler,
    timeout: int = 1
) -> None:
    ser = Serial(port, baudrate, timeout=timeout)
    logger.info("Iniciando coleta...")

    while handler.is_active:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        handler.handle(line)

    ser.close()
    logger.info(f"Coleta finalizada: {len(handler.data)} amostras")
