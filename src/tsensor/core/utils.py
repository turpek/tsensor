from datetime import datetime
import toml
import os

# Caminho absoluto para o arquivo de configuração
CONFIG_PATH = os.path.join(os.getcwd(), "config.toml")

# Única fonte de presets para microcontroladores
MCU_PRESETS = {
    "arduino_uno": {"adc_max": 1023, "v_ref": 1.1},
    "esp32": {"adc_max": 4095, "v_ref": 3.3},
}


def timestamp() -> str:
    """Retorna timestamp no formato HH:MM:SS:mmm."""
    return datetime.now().strftime("%H:%M:%S:%f")[:-3]


def load_config() -> dict:
    """Carrega as configurações do arquivo TOML e aplica padrões do MCU."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado em: {CONFIG_PATH}"
        )

    with open(CONFIG_PATH, "r") as f:
        config = toml.load(f)

    # Resolve os padrões baseados no MCU
    mcu_type = config.get("hardware", {}).get("mcu", "arduino_uno")
    preset = MCU_PRESETS.get(mcu_type, MCU_PRESETS["arduino_uno"])

    # Se adc_max ou v_ref não existirem no TOML, usa o do preset
    if "sensor" not in config:
        config["sensor"] = {}

    config["sensor"].setdefault("adc_max", preset["adc_max"])
    config["sensor"].setdefault("v_ref", preset["v_ref"])

    return config


def save_config(config: dict) -> None:
    """Salva as configurações de volta no arquivo TOML."""
    with open(CONFIG_PATH, "w") as f:
        toml.dump(config, f)
