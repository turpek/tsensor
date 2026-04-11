import threading
import os
import sys
from flask import Flask
from loguru import logger
from tsensor.routes.home import home_route
from tsensor.routes.api import api_route
from tsensor.core.utils import load_config
from tsensor.core.acquisition import start_acquisition

# Carrega a configuração global (já resolvida com padrões de MCU)
config = load_config()

# Configura o loguru dinamicamente conforme o TOML
logger.remove()
logger.add(sys.stderr, level=config["presentation"]["log_level"])

app = Flask(__name__)
app.secret_key = "SUA_CHAVE_SECRETA"

app.register_blueprint(home_route)
app.register_blueprint(api_route)


if __name__ == "__main__":
    # Inicia a aquisição se não estiver no modo debug OU se for o processo principal do modo debug
    if not config["presentation"]["debug_mode"] or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_acquisition()

    app.run(
        debug=config["presentation"]["debug_mode"],
        port=config["presentation"]["flask_port"],
    )
