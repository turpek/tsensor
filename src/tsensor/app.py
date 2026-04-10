import threading
import os
import sys
from flask import Flask
from loguru import logger
from tsensor.routes.home import home_route
from tsensor.routes.api import api_route
from tsensor.extensions import data_stream, buffer_stream
from tsensor.core.handlers import HANDLERS
from tsensor.core.serial_reader import serial_reading
from tsensor.core.utils import load_config

config = load_config()

# Configura o loguru dinamicamente conforme o TOML
logger.remove()
logger.add(sys.stderr, level=config["presentation"]["log_level"])

app = Flask(__name__)
app.secret_key = "SUA_CHAVE_SECRETA"

app.register_blueprint(home_route)
app.register_blueprint(api_route)


def serial_acquisition():
    # Inicializa o handler dinamicamente via dicionário HANDLERS
    sensor_type = config["sensor"]["type"]

    if sensor_type not in HANDLERS:
        logger.error(f"Tipo de sensor desconhecido: {sensor_type}")
        return

    handler_cls = HANDLERS[sensor_type]
    handler = handler_cls(
        data=data_stream,
        temporal_data=buffer_stream,
        samples=config["acquisition"]["total_samples"],
        timeout=config["acquisition"]["max_runtime_sec"],
        adc_max=config["sensor"]["adc_max"],
        v_ref=config["sensor"]["v_ref"],
    )

    logger.info(
        f"Iniciando coleta para sensor {sensor_type} (VRef: {config['sensor']['v_ref']}V)..."
    )
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
