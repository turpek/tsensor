from loguru import logger
from serial import Serial, SerialException
from tsensor.core.handlers import SerialHandler
from tsensor.extensions import app_status


def serial_reading(
    port: str, baudrate: int, samples: int, handler: SerialHandler, timeout: int = 1
) -> None:
    try:
        ser = Serial(port, baudrate, timeout=timeout)
        app_status["connected"] = True
        app_status["error"] = None
        logger.info(f"Conexão serial estabelecida em {port}")
    except SerialException as e:
        app_status["connected"] = False
        app_status["error"] = str(e)
        logger.error(f"Erro ao abrir porta serial {port}: {e}")
        return

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
