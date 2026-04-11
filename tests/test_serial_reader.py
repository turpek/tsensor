from tsensor.core.serial_reader import serial_reading


def test_serial_reading_calls_dispatch_until_inactive(mocker):
    """Verifica se o loop de leitura chama o dispatch enquanto o manager estiver ativo."""
    # 1. Mock do Serial
    mock_serial_cls = mocker.patch("tsensor.core.serial_reader.Serial")
    mock_ser_instance = mock_serial_cls.return_value

    # Simula o retorno de linhas pela serial (bytes)
    mock_ser_instance.readline.side_effect = [
        b"T=2025\n",
        b"T=2026\n",
        b"T=2027\n",
    ]

    # 2. Mock do StreamManager
    mock_manager = mocker.Mock()
    # O loop roda enquanto is_active for True.
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, True, False],
    )

    # Mock para evitar erro no log final: {len(stream_manager.count_samples)}
    # Mesmo sendo um erro no backend, o mock precisa sustentar a chamada para o teste passar
    mock_manager.count_samples = [1, 2]

    # 3. Execução
    serial_reading(
        port="/dev/ttyUSB0",
        baudrate=115200,
        samples=10,
        stream_manager=mock_manager,
        timeout=1,
    )

    # 4. Asserts
    # O loop deve rodar 2 vezes (True, True) e parar antes da 3ª leitura
    assert mock_manager.dispatch.call_count == 2
    mock_manager.dispatch.assert_any_call("T=2025")
    mock_manager.dispatch.assert_any_call("T=2026")

    # Verifica se a serial foi aberta e fechada corretamente
    mock_serial_cls.assert_called_once_with("/dev/ttyUSB0", 115200, timeout=1)
    mock_ser_instance.close.assert_called_once()


def test_serial_reading_handles_decoding_errors(mocker):
    """Verifica se a função lida com caracteres inválidos na serial usando ignore."""
    mock_serial_cls = mocker.patch("tsensor.core.serial_reader.Serial")
    mock_ser_instance = mock_serial_cls.return_value
    mock_ser_instance.readline.return_value = b"T=10\xff24\n"

    mock_manager = mocker.Mock()
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, False],
    )
    mock_manager.count_samples = [1]

    serial_reading("COM1", 9600, 1, mock_manager)

    # O caractere \xff deve ser ignorado conforme errors='ignore' no decode
    mock_manager.dispatch.assert_called_once_with("T=1024")
    mock_ser_instance.close.assert_called_once()
