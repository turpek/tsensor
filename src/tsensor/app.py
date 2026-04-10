import threading
from flask import Flask
from loguru import logger
from tsensor.routes.home import home_route
from tsensor.routes.api import api_route
from tsensor.extensions import data_stream, buffer_stream
from tsensor.core.handlers import LM35Handler
from tsensor.core.serial_reader import serial_reading

app = Flask(__name__)
app.secret_key = "SUA_CHAVE_SECRETA"

app.register_blueprint(home_route)
app.register_blueprint(api_route)


def serial_acquisition():
    handler = LM35Handler(data_stream, buffer_stream, 1_000_000, 1800, 1023, 1.1)

    logger.info("Iniciando leitura serial simulada...")
    serial_reading(
        port="/dev/ttyACM1",
        baudrate=115200,
        samples=1_000_000,
        handler=handler,
        timeout=1,
    )


if __name__ == "__main__":
    import os

    # Garante que a thread de aquisição inicie apenas uma vez no modo debug do Flask
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        acquisition_thread = threading.Thread(
            target=serial_acquisition, daemon=True
        )
        acquisition_thread.start()

    app.run(debug=True)
