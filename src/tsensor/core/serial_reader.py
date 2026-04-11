from loguru import logger
from serial import Serial, SerialException
from tsensor.core.handlers import StreamManager
from tsensor.extensions import app_status


def serial_reading(
    port: str, baudrate: int, samples: int, stream_manager: StreamManager, timeout: int = 1
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
        return None

    logger.info("Iniciando coleta...")

    while stream_manager.is_active:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        stream_manager.dispatch(line)

    ser.close()
    logger.info(
        f"Coleta finalizada: {stream_manager.count_samples} amostras",
    )
