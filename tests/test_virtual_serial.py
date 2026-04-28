import os
from tsensor.core.serial_connection import VirtualSerial


def test_virtual_serial_readline_format(mocker):
    """Garante que o readline retorna o formato correto (bytes, prefixo e \n)."""
    mocker.patch("time.sleep")  # Acelera o teste
    # Usando ESP32 como padrão de teste
    v_serial = VirtualSerial("SIM", 115200)
    line = v_serial.readline()

    assert isinstance(line, bytes)
    decoded = line.decode().strip()
    # Agora pode começar com T=, P= ou U=
    assert any(decoded.startswith(p) for p in ["T=", "P=", "U="])
    assert line.endswith(b"\n")


def test_virtual_serial_values_within_range(mocker):
    """Valida se os valores gerados estão coerentes com a tabela de hardware (ESP32)."""
    mocker.patch("time.sleep")  # Acelera o teste

    # Mock da config com DOIS sensores ativos para testar o novo formato T=NUM,P=NUM
    mock_config = {
        "hardware": {"mcu": "esp32", "simulation_latency_us": 100},
        "sensors": [
            {"name": "Temp", "model": "LM35", "calibration": {"v_ref": 3.3}},
            {"name": "Pres", "model": "MPS20N0040D", "calibration": {"v_ref": 3.3}}
        ],
        "acquisition": {"max_runtime_sec": 1800, "total_samples": 1000000}
    }
    mocker.patch.dict("tsensor.extensions.config", mock_config, clear=True)

    v_serial = VirtualSerial("SIM", 115200)

    # Coleta 5 amostras. No novo formato, cada linha deve ter T=... E P=... E U=...
    samples = [v_serial.readline().decode().strip() for _ in range(5)]

    for line in samples:
        assert "T=" in line
        assert "P=" in line
        assert "U=" in line
        assert "," in line

        # Parsing robusto do novo formato T=NUM,P=NUM,U=NUM (usa float para o timestamp)
        parts = {p.split("=")[0]: float(p.split("=")[1])
                 for p in line.split(",")}

        # Verifica ranges do ESP32 (LM35 ~310, MPS20 ~93556)
        assert 200 < parts["T"] < 400
        assert 90000 < parts["P"] < 96000
        assert parts["U"] >= 608200  # Valor simulado do ESP32

def test_serial_factory_selection(mocker):
    """Verifica se o módulo exporta a classe correta baseada na variável de ambiente."""

    # Testa modo Simulação
    mocker.patch.dict(os.environ, {"TSENSOR_SIMULATION": "true"})
    # Recarrega o módulo para reavaliar a variável de ambiente
    import importlib
    import tsensor.core.serial_connection
    importlib.reload(tsensor.core.serial_connection)

    assert tsensor.core.serial_connection.Serial == tsensor.core.serial_connection.VirtualSerial

    # Testa modo Real (Default)
    mocker.patch.dict(os.environ, {"TSENSOR_SIMULATION": "false"})
    importlib.reload(tsensor.core.serial_connection)
    assert tsensor.core.serial_connection.Serial != tsensor.core.serial_connection.VirtualSerial
