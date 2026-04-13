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
    assert decoded.startswith(("T=", "P="))
    assert line.endswith(b"\n")


def test_virtual_serial_values_within_range(mocker):
    """Valida se os valores gerados estão coerentes com a tabela de hardware (ESP32)."""
    mocker.patch("time.sleep")  # Acelera o teste
    # Mock da config para garantir que o init use ESP32
    mock_config = {
        "hardware": {"mcu": "esp32"},
        "sensors": [{"model": "LM35", "calibration": {"v_ref": 3.3}}],
        "acquisition": {"max_runtime_sec": 1800, "total_samples": 1000000}
    }
    mocker.patch("tsensor.extensions.config", mock_config)

    v_serial = VirtualSerial("SIM", 115200)

    # Coleta 20 amostras para garantir que pegamos ambos os prefixos
    samples = [v_serial.readline().decode().strip() for _ in range(20)]

    t_values = [int(s[2:]) for s in samples if s.startswith("T=")]
    p_values = [int(s[2:]) for s in samples if s.startswith("P=")]

    # Verifica se gerou ambos os tipos
    assert len(t_values) > 0
    assert len(p_values) > 0

    # No ESP32 @ 3.3V: T (LM35) ~ 310, P ~ 14.707.010
    # Usamos uma margem generosa de 10 sigmas para evitar falhas randômicas em testes
    if t_values:
        for v in t_values:
            assert 200 < v < 400  # Em torno de 310

    if p_values:
        for v in p_values:
            assert 11000000 < v < 16000000  # Cobre alvos de 0.5 kPa e 2.0 kPa


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
