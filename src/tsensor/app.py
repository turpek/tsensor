import threading
import os
from flask import Flask
from loguru import logger
from tsensor.routes.home import home_route
from tsensor.routes.api import api_route
from tsensor.extensions import data_stream, buffer_stream
from tsensor.core.handlers import LM35Handler, NTCHandler
from tsensor.core.serial_reader import serial_reading
from tsensor.core.utils import load_config

# Carrega a configuração global
config = load_config()

app = Flask(__name__)
app.secret_key = "SUA_CHAVE_SECRETA"

app.register_blueprint(home_route)
app.register_blueprint(api_route)


def serial_acquisition():
    # Inicializa o handler conforme o tipo do sensor no TOML
    sensor_type = config["sensor"]["type"]

    params = {
        "data": data_stream,
        "temporal_data": buffer_stream,
        "samples": config["acquisition"]["total_samples"],
        "timeout": config["acquisition"]["max_runtime_sec"],
        "adc_max": config["sensor"]["adc_max"],
        "v_ref": config["sensor"]["v_ref"],
    }

    if sensor_type == "LM35":
        handler = LM35Handler(**params)
    elif sensor_type == "NTC":
        handler = NTCHandler(**params)
    else:
        logger.error(f"Tipo de sensor desconhecido: {sensor_type}")
        return

    logger.info(f"Iniciando coleta serial para sensor {sensor_type}...")
    serial_reading(
        port=config["hardware"]["port"],
        baudrate=config["hardware"]["baudrate"],
        samples=config["acquisition"]["total_samples"],
        handler=handler,
        timeout=config["hardware"]["timeout"],
    )


if __name__ == "__main__":
    # Garante que a thread de aquisição inicie apenas uma vez no modo debug do Flask
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        acquisition_thread = threading.Thread(target=serial_acquisition, daemon=True)
        acquisition_thread.start()

    app.run(
        debug=config["presentation"]["debug_mode"],
        port=config["presentation"]["flask_port"],
    )
