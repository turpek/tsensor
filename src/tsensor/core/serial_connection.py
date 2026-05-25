import os
import random
import time
from loguru import logger
from serial import Serial as _RealSerial, SerialException

# Tabela de referência: (mcu, vref) -> targets de ADC
SIM_DATA = {
    ("esp32", 3.3): {
        "P": 4455945,  # ~0.5 kPa
        "LM35": 310,
        "NTC": 2047,
        "sigma_t": 2,
        "sigma_p": 5000  # ~0.006 kPa fluctuation
    },
    ("arduino_uno", 5.0): {
        "P": 5598367,  # ~2.0 kPa
        "LM35": 51,
        "NTC": 511,
        "sigma_t": 1,
        "sigma_p": 15000  # ~0.02 kPa fluctuation
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
        self.active_models = [s["model"] for s in config.get("sensors", [])]

        # Carrega latência configurada (Padrão 100ms se ausente)
        latency_us = config["hardware"].get("simulation_latency_us", 100000)
        self.latency = latency_us / 1_000_000.0
        self._start_ts = 608200.0
        self._creation_time = time.time()

        # Estado do Radar
        self._angle = 0
        self._angle_step = 1

        logger.info(
            f"VIRTUAL SERIAL: Simulando {mcu.upper()} @ {vref}V (Latency: {self.latency:.6f}s)")

    def reset_input_buffer(self) -> None:
        """Limpa o buffer de entrada (simulado)."""
        pass

    def readline(self) -> bytes:
        """Gera dados simulados com ruído gaussiano baseado no hardware configurado."""
        time.sleep(self.latency)

        # 20% de chance de falha na comunicação
        if random.random() < 0.20:
            fail_mode = random.choice(["empty", "corrupted", "incomplete"])
            if fail_mode == "empty":
                return b"\n"
            if fail_mode == "corrupted":
                prefix = random.choice(["T=", "P=", "U=", "A=", "D="])
                return f"{prefix}\n".encode()
            if fail_mode == "incomplete":
                # Retorna apenas um dado parcial
                return b"A=90\n"

        results = []

        # Temperatura (T)
        if any(m in self.active_models for m in ["NTC", "LM35"]):
            target = self.targets["NTC"] if "NTC" in self.active_models else self.targets["LM35"]
            val_t = int(random.gauss(target, self.targets["sigma_t"]))
            results.append(f"T={max(0, val_t)}")

        # Pressão (P)
        if "MPS20N0040D" in self.active_models:
            target = self.targets["P"]
            val_p = int(random.gauss(target, self.targets["sigma_p"]))
            results.append(f"P={max(0, val_p)}")

        # Radar (A e D)
        # Simula varredura 0 -> 180 -> 0
        results.append(f"A={self._angle}")
        # Simula objeto no centro
        dist = 20 if (80 < self._angle < 100) else 50
        results.append(f"D={dist}")

        self._angle += self._angle_step
        if self._angle >= 180 or self._angle <= 0:
            self._angle_step *= -1

        # Timestamp (U)
        current_ts = self._start_ts + (time.time() - self._creation_time)
        results.append(f"U={current_ts:.4f}")

        return (",".join(results) + "\n").encode()

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
