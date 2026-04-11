import threading
from loguru import logger
from tsensor.extensions import data_stream, buffer_stream, config
from tsensor.core.handlers import HANDLERS, StreamManager
from tsensor.core.serial_reader import serial_reading

# Controle global da thread
_acquisition_thread = None
_current_manager = None
_thread_lock = threading.Lock()

TEMP_NAME = 'temperature'


def stop_acquisition():
    """Para a thread de aquisição atual se estiver rodando."""
    global _acquisition_thread, _current_manager
    with _thread_lock:
        if _current_manager:
            _current_manager.stop()
        
        if _acquisition_thread and _acquisition_thread.is_alive():
            _acquisition_thread.join(timeout=2)
            logger.info("Thread de aquisição interrompida.")
        
        _acquisition_thread = None
        _current_manager = None


def start_acquisition():
    """Inicia ou reinicia a thread de aquisição serial se não estiver rodando."""
    global _acquisition_thread, _current_manager

    with _thread_lock:
        if _acquisition_thread and _acquisition_thread.is_alive():
            logger.warning(
                "Tentativa de iniciar aquisição, mas a thread já está ativa."
            )
            return

        def run(manager):
            sensor_type = config["sensor"]["type"]
            if sensor_type not in HANDLERS:
                logger.error(f"Tipo de sensor desconhecido: {sensor_type}")
                return

            handler_cls = HANDLERS[sensor_type]

            manager.add_handler(
                TEMP_NAME,
                handler_cls,
                data_stream,
                buffer_stream,
            )

            logger.info(
                f"Iniciando tentativa de conexão em {config['hardware']['port']}..."
            )
            serial_reading(
                port=config["hardware"]["port"],
                baudrate=config["hardware"]["baudrate"],
                samples=config["acquisition"]["total_samples"],
                stream_manager=manager,
                timeout=config["hardware"]["timeout"],
            )

        _current_manager = StreamManager(
            samples=config["acquisition"]["total_samples"],
            timeout=config["acquisition"]["max_runtime_sec"],
            adc_max=config["sensor"]["adc_max"],
            v_ref=config["sensor"]["v_ref"],
        )

        _acquisition_thread = threading.Thread(target=run, args=(_current_manager,), daemon=True)
        _acquisition_thread.start()
        logger.info("Thread de aquisição disparada com sucesso.")
