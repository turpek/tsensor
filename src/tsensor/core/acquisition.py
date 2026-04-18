import threading
from loguru import logger
from tsensor.extensions import manager, config, setup_manager, sheet_range
from tsensor.core.serial_reader import sheets_reading

# Controle global da thread
_acquisition_thread = None
_thread_lock = threading.Lock()


def stop_acquisition():
    """Para a thread de aquisição atual se estiver rodando."""
    global _acquisition_thread
    with _thread_lock:
        if manager:
            manager.stop()

        if _acquisition_thread and _acquisition_thread.is_alive():
            # Não damos join com timeout longo para não travar o Flask
            # O manager.stop() já sinaliza a interrupção no serial_reader
            logger.info("Sinalizando parada para a thread de aquisição.")

        _acquisition_thread = None


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
            try:
                # Configura o manager global com base no TOML atualizado
                setup_manager(config)

                logger.info(
                    "Iniciando leitura a partir das planilhas Google Sheets..."
                )
                sheets_reading(
                    sheet_range=sheet_range,
                    stream_manager=manager,
                    timeout=config["hardware"].get("timeout", 1.0),
                )
            except Exception as e:
                logger.error(f"Erro crítico na thread de aquisição: {e}")
            finally:
                logger.info("Thread de aquisição finalizada.")

        _acquisition_thread = threading.Thread(
            target=run, daemon=True,
        )
        _acquisition_thread.start()
        logger.info("Thread de aquisição disparada com sucesso.")
