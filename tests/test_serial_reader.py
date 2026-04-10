import pytest
from tsensor.core.serial_reader import serial_reading


def test_serial_reading_calls_handler_until_inactive(mocker):
    """Verifica se o loop de leitura chama o handler enquanto ele estiver ativo."""
    # 1. Mock do Serial
    # Patching onde Serial é importado em serial_reader.py
    mock_serial_cls = mocker.patch("tsensor.core.serial_reader.Serial")
    mock_ser_instance = mock_serial_cls.return_value

    # Simula o retorno de linhas pela serial (bytes)
    mock_ser_instance.readline.side_effect = [b"1024\n", b"2048\n", b"3072\n"]

    # 2. Mock do Handler
    # Criamos um mock e configuramos a property is_active para alternar valores
    mock_handler = mocker.Mock()
    type(mock_handler).is_active = mocker.PropertyMock(side_effect=[True, True, False])

    # Mock do atributo .data para o log final
    mock_handler.data = [1, 2]

    # 3. Execução
    serial_reading(
        port="/dev/ttyUSB0",
        baudrate=115200,
        samples=10,
        handler=mock_handler,
        timeout=1,
    )

    # 4. Asserts
    # O loop deve rodar 2 vezes (True, True) e parar na 3ª (False)
    assert mock_handler.handle.call_count == 2
    mock_handler.handle.assert_any_call("1024")
    mock_handler.handle.assert_any_call("2048")

    # Verifica se a serial foi aberta e fechada corretamente
    mock_serial_cls.assert_called_once_with("/dev/ttyUSB0", 115200, timeout=1)
    mock_ser_instance.close.assert_called_once()


def test_serial_reading_handles_decoding_errors(mocker):
    """Verifica se a função lida com caracteres inválidos na serial usando ignore."""
    mock_serial_cls = mocker.patch("tsensor.core.serial_reader.Serial")
    mock_ser_instance = mock_serial_cls.return_value
    mock_ser_instance.readline.return_value = b"10\xff24\n"

    mock_handler = mocker.Mock()
    type(mock_handler).is_active = mocker.PropertyMock(side_effect=[True, False])
    mock_handler.data = [1]

    serial_reading("COM1", 9600, 1, mock_handler)

    # O caractere \xff deve ser ignorado conforme errors='ignore' no decode
    mock_handler.handle.assert_called_once_with("1024")
    mock_ser_instance.close.assert_called_once()
