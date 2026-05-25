import threading
from loguru import logger
from tsensor.extensions import manager, config, setup_stream_manager
from tsensor.core.serial_reader import sheets_reading, serial_reading

# Controle global das threads
_sheets_thread = None
_serial_thread = None
_thread_lock = threading.Lock()


def stop_acquisition():
    """Para todas as threads de aquisição (Sheets e Serial)."""
    global _sheets_thread, _serial_thread
    with _thread_lock:
        if manager:
            manager.stop()

        _sheets_thread = None
        _serial_thread = None
        logger.info("Comando de parada enviado para todas as threads.")


def start_acquisition():
    """Inicia o monitoramento padrão via Google Sheets."""
    global _sheets_thread

    with _thread_lock:
        if _sheets_thread and _sheets_thread.is_alive():
            logger.warning("Monitoramento Sheets já está em execução.")
            return

        setup_stream_manager(config)
        hardware_config = config.get("hardware", {})

        def run_sheets():
            try:
                logger.info(
                    "Iniciando monitoramento autônomo do Google Sheets.")
                sheets_reading(
                    manager, timeout=hardware_config.get("timeout", 1.0))
            except Exception as e:
                logger.error(f"Erro na thread do Sheets: {e}")
            finally:
                logger.info("Thread Sheets finalizada.")

        _sheets_thread = threading.Thread(target=run_sheets, daemon=True)
        _sheets_thread.start()
        logger.info("Monitoramento Sheets disparado com sucesso.")


def start_serial():
    """Ativa a funcionalidade de tempo real via Serial (ESP32)."""
    global _serial_thread

    with _thread_lock:
        if _serial_thread and _serial_thread.is_alive():
            logger.warning("Aquisição Serial em tempo real já está ativa.")
            return

        hardware_config = config.get("hardware", {})
        port = hardware_config.get("port")
        baudrate = hardware_config.get("baudrate", 115200)

        if not port:
            logger.error(
                "Porta serial não configurada. Impossível ativar tempo real.")
            return

        def run_serial():
            try:
                logger.info(f"Ativando modo Tempo Real na porta {port}.")
                serial_reading(port, baudrate, manager)
            except Exception as e:
                logger.error(f"Erro na thread Serial: {e}")
            finally:
                logger.info("Thread Serial finalizada.")

        _serial_thread = threading.Thread(target=run_serial, daemon=True)
        _serial_thread.start()
        logger.info("Modo Tempo Real (Serial) disparado com sucesso.")
