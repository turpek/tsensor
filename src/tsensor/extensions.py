from loguru import logger
from tsensor.core.data_stream import DataStream
from tsensor.core.handlers import StreamManager, HANDLERS
from tsensor.core.sheets import SheetsManager, SpreadSheetRange
from tsensor.core.utils import load_config

# Carrega as configurações globais
config = load_config()
manager = StreamManager()

# Instância e configuração global do SheetsManager
sheet_manager = SheetsManager()
sheet_manager.setup()
sheet_range = SpreadSheetRange()


def setup_manager(config: dict) -> StreamManager:
    # Parâmetros vindos do TOML
    manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec"),
        total_samples=config["acquisition"].get("total_samples"),
    )

    session_limit = config["acquisition"].get("total_samples", 1000000)
    buffer_limit = config["acquisition"].get("buffer_samples", 1000)
    timeseries_limit = config["acquisition"].get("timeseries_samples", 480)

    for sensor in config.get('sensors', []):
        sensor_model = sensor.get("model")
        if sensor_model not in HANDLERS:
            logger.error(f"Modelo de sensor desconhecido: {sensor_model}")
            continue

        data_stream = DataStream(total_samples=session_limit)
        data_buffer = DataStream(total_samples=buffer_limit)
        time_series = DataStream(total_samples=timeseries_limit)

        cls_handler = HANDLERS.get(sensor_model)
        kwargs = sensor.get('calibration', {})
        name = sensor.get('name')
        handler = cls_handler(data_stream, data_buffer, time_series, **kwargs)
        manager.add_handler(name, handler)

    if len(manager) == 0:
        raise RuntimeError(
            "Nenhum sensor válido foi configurado para aquisição.")

    return manager


# Estado global da aplicação
app_status = {
    "connected": False,
    "port": config["hardware"]["port"],
    "mcu": config["hardware"]["mcu"],
    "error": None,
}
