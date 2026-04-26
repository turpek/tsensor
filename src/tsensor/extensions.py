from loguru import logger
from tsensor.core.data_stream import DataStream
from tsensor.core.sheets import SheetsManager
from tsensor.core.handlers import StreamManager, HANDLERS, SheetsHandler, TimestampHandler
from tsensor.core.utils import load_config

import threading
import os

# Carrega as configurações globais
config = load_config()

# Tenta carregar latência média persistida
_initial_latency = 0.0
_latency_cache = os.path.join("exports", ".latency_cache")
if os.path.exists(_latency_cache):
    try:
        with open(_latency_cache, "r") as f:
            _initial_latency = float(f.read().strip())
    except Exception:
        pass

manager = StreamManager()

# Instância e configuração global do SheetsManager
sheet_manager = SheetsManager()
# Expande a planilha conforme as amostras configuradas (+1 para cabeçalho) e 3 colunas (TS, Temp, Pres)
total_samples = config["acquisition"].get("total_samples", 1000)
sheet_manager.setup(row_count=total_samples + 1, col_count=3)


def setup_serial_manager(config: dict) -> StreamManager:
    """Configura um StreamManager local para aquisição Serial em lotes."""
    serial_manager = StreamManager()

    # Parâmetros para o modo Serial
    batch_limit = config["acquisition"].get("serial_batch_size", 50)

    serial_manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec"),
        total_samples=None,  # O controle de parada será externo ou via is_active global
    )

    # Adiciona o TimestampHandler como primeiro da fila
    ts_handler = TimestampHandler(
        data=DataStream(total_samples=batch_limit),
        data_buffer=DataStream(total_samples=1),
        time_series=DataStream(total_samples=1),
        name="timestamp",
        adc_max=0,
        v_ref=0.0
    )
    serial_manager.add_handler("timestamp", ts_handler)

    for sensor in config.get('sensors', []):

        sensor_model = sensor.get("model")
        if sensor_model not in HANDLERS:
            continue

        # DataStream principal tem o tamanho do lote de exportação
        data_stream = DataStream(total_samples=batch_limit)
        # Buffers de tempo real têm tamanho 1 (apenas a última amostra)
        data_buffer = DataStream(total_samples=1)
        time_series = DataStream(total_samples=1)

        kwargs = sensor.get('calibration', {})
        name = sensor.get('name')

        handler = HANDLERS[sensor_model](
            data=data_stream,
            data_buffer=data_buffer,
            time_series=time_series,
            adc_max=kwargs.get('adc_max', 4095),
            v_ref=kwargs.get('v_ref', 3.3)
        )
        serial_manager.add_handler(name, handler)

    return serial_manager


def setup_manager(config: dict) -> StreamManager:
    # Configura os limites globais
    manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec"),
        total_samples=config["acquisition"].get("total_samples"),
    )

    session_limit = config["acquisition"].get("total_samples", 1000000)
    buffer_limit = config["acquisition"].get("buffer_samples", 1000)
    timeseries_limit = config["acquisition"].get("timeseries_samples", 480)

    # Adiciona o SheetsHandler para a coluna de tempo (Coluna A da Planilha)
    ts_handler = SheetsHandler(
        data=DataStream(total_samples=session_limit),
        data_buffer=DataStream(total_samples=buffer_limit),
        time_series=DataStream(total_samples=timeseries_limit),
        name="timestamp",
        adc_max=0,
        v_ref=0.0
    )
    manager.add_handler("timestamp", ts_handler)

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

    if len(manager) <= 1:
        raise RuntimeError(
            "Nenhum sensor válido foi configurado para aquisição.")

    return manager


# Estado global da aplicação
app_status = {
    "connected": False,
    "port": config["hardware"]["port"],
    "mcu": config["hardware"]["mcu"],
    "batch_latency": _initial_latency,
    "fetch_time": 0.0,
    "error": None,
}

sheets_lock = threading.Semaphore(1)
