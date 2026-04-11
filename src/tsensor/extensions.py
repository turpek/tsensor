from tsensor.core.data_stream import DataStream
from tsensor.core.utils import load_config

# Carrega as configurações globais
config = load_config()

# Parâmetros vindos do TOML
TOTAL_SAMPLES = config["acquisition"]["total_samples"]
TOTA_TEMPORAL_SAMPLES = config["acquisition"]["buffer_samples"]

data_stream = DataStream(total_samples=TOTAL_SAMPLES)
buffer_stream = DataStream(total_samples=TOTA_TEMPORAL_SAMPLES)
history_stream = DataStream(total_samples=TOTA_TEMPORAL_SAMPLES)

# Estado global da aplicação
app_status = {
    "connected": False,
    "port": config["hardware"]["port"],
    "mcu": config["hardware"]["mcu"],
    "error": None,
}
