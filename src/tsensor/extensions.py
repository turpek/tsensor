from loguru import logger
from tsensor.core.data_stream import DataStream
from tsensor.core.sheets import SheetsManager, SyncCoordinator, get_header
from tsensor.core.handlers import SerialHandler, StreamManager, SerialManager, HANDLERS, TimestampHandler
from tsensor.core.utils import load_config

import threading
import os
import re

# Carrega as configurações globais
config = load_config()


def sync_ai_config(sensors_list=None):
    """Sincroniza a configuração de sensores diretamente com o DataManager da IA."""
    try:
        from tsensor.ai.dashboard import data_manager
        # Usa a lista fornecida (ex: vinda da planilha) ou o config local
        target_sensors = sensors_list if sensors_list is not None else config.get("sensors", [])

        sensors = [{"name": s["name"], "type": s.get("type", "valor")}
                   for s in target_sensors]
        data_manager.update_config(
            sensors, config["acquisition"].get("total_samples", 1000))
        logger.info(f"IA sincronizada: {len(sensors)} sensores carregados.")
    except Exception as e:
        logger.warning(f"Não foi possível sincronizar a IA: {e}")


# Inicializa a IA com as configurações iniciais
sync_ai_config()

# Parâmetros de sincronização
_total_samples_limit = config["acquisition"].get("total_samples", 1000)

# Objeto global para coordenar cursores e transição de modo
sync_coordinator = SyncCoordinator(_total_samples_limit)

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
# Expande a planilha conforme as amostras configuradas (+1 para cabeçalho)
total_samples = config["acquisition"].get("total_samples", 1000)
# Dinâmico: Timestamp + Sensores
col_count = 1 + len(config.get('sensors', []))
sheet_manager.setup(row_count=total_samples + 1, col_count=col_count)


def factory_handler(
    handler_cls: type[SerialHandler],
    sensor: dict,
    session_limit: int,
    buffer_limit: int,
    timeseries_limit: int,
) -> SerialHandler:

    # DataStream principal tem o tamanho do lote de exportação
    data_stream = DataStream(total_samples=session_limit)
    # Buffers de tempo real têm tamanho 1 (apenas a última amostra)
    data_buffer = DataStream(total_samples=buffer_limit)
    time_series = DataStream(total_samples=timeseries_limit)

    kwargs = sensor.get('calibration', {})
    name = sensor.get('name')
    model = sensor.get('model')
    type_sensor = sensor.get('type')
    full_name = f'{type_sensor}[{name},{model}]'

    handler = handler_cls(
        data=data_stream,
        data_buffer=data_buffer,
        name=full_name,
        time_series=time_series,
        adc_max=kwargs.get('adc_max', 4095),
        v_ref=kwargs.get('v_ref', 3.3)
    )
    return handler


def setup_manager(
    manager: SerialManager | StreamManager,
    sensors: list,
    session_limit: int,
    buffer_limit: int,
    timeseries_limit: int,
) -> SerialManager | StreamManager:
    """Configura um SerialManager local para aquisição Serial em lotes."""

    # Adiciona o TimestampHandler como primeiro da fila
    ts_sensor = {
        'name': 'time',
        'type': 'timestamp',
        'calibration': {"adc_max": 0, "v_ref": 0.0}
    }
    limits = (session_limit, buffer_limit, timeseries_limit)
    ts_handler = factory_handler(TimestampHandler, ts_sensor, *limits)
    manager.add_handler("timestamp", ts_handler,)

    for sensor in sensors:
        sensor_model = sensor.get("model")
        name = sensor.get('name')
        handler_cls = HANDLERS[sensor_model]
        handler = factory_handler(handler_cls, sensor, *limits)
        manager.add_handler(name, handler)

    return manager


def setup_serial_manager(config: dict) -> SerialManager:
    """Configura um SerialManager local para aquisição Serial em lotes."""
    serial_manager = SerialManager()
    # Parâmetros para o modo Serial
    serial_manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec")
    )
    sensors = config.get('sensors', [])
    return setup_manager(serial_manager, sensors, 1, 1, 1)


def setup_stream_manager(config: dict) -> StreamManager:
    """Configura o StreamManager global para o Dashboard via Google Sheets."""
    # Configura os limites globais
    manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec"),
        total_samples=config["acquisition"].get("total_samples"),
    )

    session_limit = config["acquisition"].get("total_samples", 1000000)
    buffer_limit = config["acquisition"].get("buffer_samples", 1000)
    timeseries_limit = config["acquisition"].get("timeseries_samples", 480)
    sensors = config.get('sensors', [])

    # Limpa handlers antigos
    manager._handlers = {}

    # Se descobriu cabeçalho, usa a ordem da planilha
    header_values = get_header(manager, sheets_lock)
    if header_values:
        logger.info(f"Configurando Dashboard via cabeçalho Sheets: {header_values}")
        ordered_sensors = []

        for col in header_values[1:]:
            # Tenta casar com o padrão tipo[nome,model]
            match = re.match(r"(\w+)\[(.+),(.+)]", col)
            if match:
                s_type, s_name, s_model = match.groups()
                sensor_cfg = {
                    'name': s_name,
                    'type': s_type,
                    'model': s_model,
                    'calibration': {'adc_max': 0, 'v_ref': 0.0}
                }
                ordered_sensors.append(sensor_cfg)
        if ordered_sensors:
            sensors = ordered_sensors
            # Sincroniza a IA com a nova ordem descoberta na planilha
            sync_ai_config(sensors)

    setup_manager(manager, sensors, session_limit, buffer_limit, timeseries_limit)
    if len(manager) < 1:
        raise RuntimeError("Nenhum sensor válido foi configurado para visualização.")

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
