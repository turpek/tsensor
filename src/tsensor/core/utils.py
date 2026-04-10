from datetime import datetime
import toml
import os

# Caminho absoluto para o arquivo de configuração (mesma pasta que app.py)
CONFIG_PATH = os.path.join(os.getcwd(), "config.toml")


def timestamp() -> str:
    """Retorna timestamp no formato HH:MM:SS:mmm."""
    return datetime.now().strftime("%H:%M:%S:%f")[:-3]


def load_config() -> dict:
    """Carrega as configurações do arquivo TOML."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado em: {CONFIG_PATH}"
        )

    with open(CONFIG_PATH, "r") as f:
        return toml.load(f)


def save_config(config: dict) -> None:
    """Salva as configurações de volta no arquivo TOML."""
    with open(CONFIG_PATH, "w") as f:
        toml.dump(config, f)
