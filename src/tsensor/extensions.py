from loguru import logger
from tsensor.core.data_stream import DataStream
from tsensor.core.handlers import StreamManager, HANDLERS, SheetsHandler
from tsensor.core.sheets import SheetsManager, SpreadSheetRange
from tsensor.core.utils import load_config

# Carrega as configurações globais
config = load_config()
manager = StreamManager()

# Instância e configuração global do SheetsManager
sheet_manager = SheetsManager()
# Expande a planilha conforme as amostras configuradas (+1 para cabeçalho) e 3 colunas (TS, Temp, Pres)
total_samples = config["acquisition"].get("total_samples", 1000)
sheet_manager.setup(row_count=total_samples + 1, col_count=3)
sheet_range = SpreadSheetRange(row=2)


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

        kwargs = sensor.get('calibration', {})
        name = sensor.get('name')

        handler = SheetsHandler(
            data=data_stream,
            data_buffer=data_buffer,
            time_series=time_series,
            name=name,
            adc_max=kwargs.get('adc_max', 4095),
            v_ref=kwargs.get('v_ref', 3.3)
        )
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
