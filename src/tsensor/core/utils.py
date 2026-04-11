from datetime import datetime
import os
import toml
from datetime import datetime

# Caminho absoluto para o arquivo de configuração
CONFIG_PATH = os.path.join(os.getcwd(), "config.toml")

# Template padrão para inicialização do sistema
DEFAULT_CONFIG = {
    "hardware": {
        "port": "/dev/ttyUSB0",
        "baudrate": 115200,
        "timeout": 1.0,
        "mcu": "esp32",
    },
    "sensor": {
        "type": "LM35",
        "adc_max": 4095,
        "v_ref": 3.3,
    },
    "acquisition": {
        "total_samples": 1000000,
        "buffer_samples": 1000,
        "max_runtime_sec": 1800,
    },
    "presentation": {
        "log_level": "INFO",
        "decimal_places": 1,
        "update_interval_ms": 1000,
        "flask_port": 5000,
        "debug_mode": False,
    },
}

# Única fonte de presets para microcontroladores
MCU_PRESETS = {
    "arduino_uno": {"adc_max": 1023, "v_ref": 1.1},
    "esp32": {"adc_max": 4095, "v_ref": 3.3},
}


def timestamp() -> str:
    """Retorna timestamp no formato HH:MM:SS:mmm."""
    return datetime.now().strftime("%H:%M:%S:%f")[:-3]


def load_config() -> dict:
    """Carrega as configurações do arquivo TOML ou usa o template padrão."""
    if not os.path.exists(CONFIG_PATH):
        # Se não existir, retorna uma cópia profunda do template padrão
        import copy

        return copy.deepcopy(DEFAULT_CONFIG)

    with open(CONFIG_PATH, "r") as f:
        config = toml.load(f)

    # Resolve os padrões baseados no MCU para garantir integridade
    mcu_type = config.get("hardware", {}).get("mcu", "arduino_uno")
    preset = MCU_PRESETS.get(mcu_type, MCU_PRESETS["arduino_uno"])

    if "sensor" not in config:
        config["sensor"] = {}

    config["sensor"].setdefault("adc_max", preset["adc_max"])
    config["sensor"].setdefault("v_ref", preset["v_ref"])

    return config


def save_config(config_dict: dict) -> None:
    """Salva as configurações de volta no arquivo TOML."""
    with open(CONFIG_PATH, "w") as f:
        toml.dump(config_dict, f)
