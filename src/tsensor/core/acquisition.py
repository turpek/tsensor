import threading
from loguru import logger
from tsensor.extensions import data_stream, buffer_stream, config
from tsensor.core.handlers import HANDLERS
from tsensor.core.serial_reader import serial_reading

# Controle global da thread
_acquisition_thread = None
_thread_lock = threading.Lock()


def start_acquisition():
    """Inicia ou reinicia a thread de aquisição serial se não estiver rodando."""
    global _acquisition_thread

    with _thread_lock:
        if _acquisition_thread and _acquisition_thread.is_alive():
            logger.warning(
                "Tentativa de iniciar aquisição, mas a thread já está ativa."
            )
            return

        def run():
            sensor_type = config["sensor"]["type"]
            if sensor_type not in HANDLERS:
                logger.error(f"Tipo de sensor desconhecido: {sensor_type}")
                return

            handler_cls = HANDLERS[sensor_type]
            handler = handler_cls(
                data=data_stream,
                temporal_data=buffer_stream,
                samples=config["acquisition"]["total_samples"],
                timeout=config["acquisition"]["max_runtime_sec"],
                adc_max=config["sensor"]["adc_max"],
                v_ref=config["sensor"]["v_ref"],
            )

            logger.info(
                f"Iniciando tentativa de conexão em {config['hardware']['port']}..."
            )
            serial_reading(
                port=config["hardware"]["port"],
                baudrate=config["hardware"]["baudrate"],
                samples=config["acquisition"]["total_samples"],
                handler=handler,
                timeout=config["hardware"]["timeout"],
            )

        _acquisition_thread = threading.Thread(target=run, daemon=True)
        _acquisition_thread.start()
        logger.info("Thread de aquisição disparada com sucesso.")
