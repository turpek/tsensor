import os
import random
import time
from loguru import logger
from serial import Serial as _RealSerial, SerialException

# Tabela de referência: (mcu, vref) -> targets de ADC
SIM_DATA = {
    ("esp32", 3.3): {
        "P": 15358544,  # Alvo: 0.5 kPa
        "LM35": 310,
        "NTC": 2047,
        "sigma_t": 2,
        "sigma_p": 500
    },
    ("arduino_uno", 5.0): {
        "P": 11162548,  # Alvo: 2.0 kPa
        "LM35": 51,
        "NTC": 511,
        "sigma_t": 1,
        "sigma_p": 300
    },
    ("arduino_uno", 1.1): {
        "P": 16777215,  # Saturado
        "LM35": 232,
        "NTC": 511,
        "sigma_t": 1,
        "sigma_p": 0
    }
}

DEFAULT_TARGETS = SIM_DATA[("esp32", 3.3)]


class VirtualSerial:
    """Simula a interface da biblioteca pyserial com base em valores reais de hardware."""

    def __init__(self, port, baudrate, timeout=1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True

        # Import local para evitar dependência circular
        from tsensor.extensions import config

        mcu = config["hardware"].get("mcu", "esp32")
        # Usa a V_Ref do primeiro sensor como base para a simulação do sistema
        vref = 3.3
        if config["sensors"]:
            vref = config["sensors"][0]["calibration"].get("v_ref", 3.3)

        # Seleciona os targets da tabela ou usa default (ESP32)
        self.targets = SIM_DATA.get((mcu, vref), DEFAULT_TARGETS)
        self.active_models = [s["model"] for s in config["sensors"]]

        # Carrega latência configurada (Padrão 100ms se ausente)
        latency_us = config["hardware"].get("simulation_latency_us", 100000)
        self.latency = latency_us / 1_000_000.0

        logger.info(
            f"VIRTUAL SERIAL: Simulando {mcu.upper()} @ {vref}V (Latency: {self.latency:.6f}s)")

    def readline(self) -> bytes:
        """Gera dados simulados com ruído gaussiano baseado no hardware configurado."""
        time.sleep(self.latency)

        # Decide qual prefixo enviar (T ou P)
        prefix = random.choice(["T", "P"])

        if prefix == "T":
            # Escolhe o alvo baseado no modelo de temperatura presente na config
            if "NTC" in self.active_models:
                target = self.targets["NTC"]
            else:
                target = self.targets["LM35"]
            val = int(random.gauss(target, self.targets["sigma_t"]))
        else:
            # Pressão (MPS20 / HX710B)
            target = self.targets["P"]
            val = int(random.gauss(target, self.targets["sigma_p"]))

        val = max(0, val)
        return f"{prefix}={val}\n".encode()

    def close(self):
        self.is_open = False
        logger.info("Virtual Serial encerrada.")


# Seleção automática baseada em variável de ambiente
_USE_SIMULATOR = os.getenv("TSENSOR_SIMULATION", "false").lower() == "true"

if _USE_SIMULATOR:
    logger.warning("Sistema rodando em MODO SIMULAÇÃO (VirtualSerial)")
    Serial = VirtualSerial
else:
    Serial = _RealSerial

SerialException = SerialException
