from loguru import logger
from tsensor.core.data_stream import DataStream
from tsensor.core.sheets import SheetsManager, SyncCoordinator
from tsensor.core.handlers import StreamManager, SerialManager, HANDLERS, TimestampHandler
from tsensor.core.utils import load_config

import threading
import os
import re

# Carrega as configurações globais
config = load_config()


def sync_ai_config():
    """Sincroniza a configuração de sensores diretamente com o DataManager da IA."""
    try:
        from tsensor.ai.dashboard import data_manager
        sensors = [{"name": s["name"], "type": s.get("type", "valor")}
                   for s in config.get("sensors", [])]
        data_manager.update_config(
            sensors, config["acquisition"].get("total_samples", 1000))
        logger.info(f"IA sincronizada: {len(sensors)} sensores carregados.")
    except Exception as e:
        logger.warning(f"Não foi possível sincronizar a IA no boot: {e}")


# Inicializa a IA com as configurações atuais
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


def setup_serial_manager(config: dict) -> SerialManager:
    """Configura um SerialManager local para aquisição Serial em lotes."""
    serial_manager = SerialManager()

    # Parâmetros para o modo Serial
    batch_limit = config["acquisition"].get("serial_batch_size", 50)

    serial_manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec")
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
    """Configura o StreamManager global para o Dashboard via Google Sheets."""
    # Configura os limites globais
    manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec"),
        total_samples=config["acquisition"].get("total_samples"),
    )

    session_limit = config["acquisition"].get("total_samples", 1000000)
    buffer_limit = config["acquisition"].get("buffer_samples", 1000)
    timeseries_limit = config["acquisition"].get("timeseries_samples", 480)

    # Tenta descobrir o cabeçalho real da planilha
    header_values = []
    try:
        from tsensor.core.sheets import SpreadSheetRange
        header_range = SpreadSheetRange(row=1, col=1)
        header_range.major_row(1, 26)
        with sheets_lock:
            res = sheet_manager.fetch_data(header_range)
        val_ranges = res.get('valueRanges', [])
        header_values = val_ranges[0].get('values', [[]])[0] if val_ranges else []
    except Exception:
        logger.warning("Não foi possível ler o cabeçalho do Sheets. Usando config local.")

    # Limpa handlers antigos
    manager._handlers = {}

    # Se descobriu cabeçalho, usa a ordem da planilha
    if header_values:
        logger.info(f"Configurando Dashboard via cabeçalho Sheets: {header_values}")
        for col in header_values:
            # 1. Verifica primeiro se é o timestamp (Coluna A)
            if "timestamp" in col.lower():
                h = TimestampHandler(
                    data=DataStream(total_samples=session_limit),
                    data_buffer=DataStream(total_samples=buffer_limit),
                    time_series=DataStream(total_samples=timeseries_limit),
                    name="timestamp",
                    adc_max=0, v_ref=0.0
                )
                manager.add_handler("timestamp", h)
                continue

            # 2. Se não for timestamp, tenta casar com o padrão de sensor tipo[nome]
            match = re.match(r"(\w+)\[(.*)\]", col)
            if match:
                s_type, s_name = match.groups()
                sensor_cfg = next((s for s in config.get('sensors', []) if s['name'] == s_name), None)
                model = sensor_cfg['model'] if sensor_cfg else None
                if model in HANDLERS:
                    h = HANDLERS[model](
                        data=DataStream(total_samples=session_limit),
                        data_buffer=DataStream(total_samples=buffer_limit),
                        time_series=DataStream(total_samples=timeseries_limit),
                        adc_max=0, v_ref=0.0
                    )
                    manager.add_handler(s_name, h)
    
    # Se não há cabeçalho ou falhou, usa a configuração local como fallback
    if not manager._handlers:
        logger.info("Configurando Dashboard via configuração local (fallback).")
        ts_handler = TimestampHandler(
            data=DataStream(total_samples=session_limit),
            data_buffer=DataStream(total_samples=buffer_limit),
            time_series=DataStream(total_samples=timeseries_limit),
            name="timestamp",
            adc_max=0, v_ref=0.0
        )
        manager.add_handler("timestamp", ts_handler)

        for sensor in config.get('sensors', []):
            model = sensor.get("model")
            if model in HANDLERS:
                h = HANDLERS[model](
                    data=DataStream(total_samples=session_limit),
                    data_buffer=DataStream(total_samples=buffer_limit),
                    time_series=DataStream(total_samples=timeseries_limit),
                    adc_max=0, v_ref=0.0
                )
                manager.add_handler(sensor['name'], h)

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
