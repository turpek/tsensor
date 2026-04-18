import pytest
from tsensor.core.serial_reader import serial_reading, sheets_reading, offline_reading, batch_manager
from tsensor.core.sheets import SpreadSheetRange, SheetsManager
from tsensor.core.handlers import StreamManager
from tsensor.extensions import sheet_range


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
    mock_manager = mocker.Mock(spec=StreamManager)
    # O loop roda enquanto is_active for True.
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, True, False],
    )

    # 3. Execução
    serial_reading(
        port="/dev/ttyUSB0",
        baudrate=115200,
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

    mock_manager = mocker.Mock(spec=StreamManager)
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, False],
    )

    serial_reading("COM1", 9600, mock_manager)

    # O caractere \xff deve ser ignorado conforme errors='ignore' no decode
    mock_manager.dispatch.assert_called_once_with("T=1024")
    mock_ser_instance.close.assert_called_once()


# --- TESTES PARA NOVAS FUNÇÕES ---

def test_batch_manager_write_mode(mocker):
    """Verifica se o modo WRITE avança o SpreadSheetRange corretamente."""
    mocker.patch(
        "tsensor.core.serial_reader.sleep")  # Não queremos pausar o teste

    # Reseta o range global para um estado conhecido antes do teste
    sheet_range.clear()
    assert sheet_range.to_a1() == "A1"

    # Executa o batch manager no modo WRITE para avançar 10 linhas e 2 colunas
    result = batch_manager('WRITE', 0, 10, 2)

    # O range deve ter avançado para A1:B10
    assert result == sheet_range
    assert result.to_a1() == "A1:B10"

    # Avança mais 5 linhas e 2 colunas -> A11:B15
    result2 = batch_manager('WRITE', 0, 5, 2)
    assert result2.to_a1() == "A11:B15"


def test_batch_manager_read_mode_success(mocker):
    """Verifica se o modo READ faz fetch, avança cursor e retorna os dados."""
    mocker.patch("tsensor.core.serial_reader.sleep")
    mock_sheet_manager = mocker.Mock(spec=SheetsManager)

    sheet_range.clear()

    # Simula o retorno de dados com o tamanho esperado
    mock_sheet_manager.fetch_data.return_value = {
        'valueRanges': [{'values': [["ts1", "val1"], ["ts2", "val2"]]}]
    }

    # Solicita 2 linhas
    result = batch_manager('READ', 0, 2, 2, mock_sheet_manager)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == ["ts1", "val1"]

    # Verifica se o fetch_data foi chamado com o range A1:B2
    mock_sheet_manager.fetch_data.assert_called_once()
    assert sheet_range.to_a1() == "A1:B2"


def test_batch_manager_read_mode_eof_compensation(mocker):
    """Verifica se o modo READ compensa o cursor ao bater no fim da planilha."""
    mocker.patch("tsensor.core.serial_reader.sleep")
    mock_sheet_manager = mocker.Mock(spec=SheetsManager)

    sheet_range.clear()  # Começa em A1

    # Simula que a planilha só tem 3 linhas restantes, mas pedimos 5
    mock_sheet_manager.fetch_data.return_value = {
        'valueRanges': [{'values': [["t1", "1"], ["t2", "2"], ["t3", "3"]]}]
    }

    # Pedimos 5 linhas (row=5). O range inicialmente irá para A1:B5
    # Mas como só retornou 3, deve compensar o cursor.
    result = batch_manager('READ', 0, 5, 2, mock_sheet_manager)

    assert len(result) == 3
    # Range real lido foi de 3 linhas, então o cursor deve ter recuado para refletir o A1:B3
    assert sheet_range.to_a1() == "A1:B3"

    # Na próxima chamada (ex: pede 5 de novo), ele deve avançar a partir de A4, não A6.
    # Vamos validar isso: A4:B8
    mock_sheet_manager.fetch_data.return_value = {
        'valueRanges': [{'values': []}]  # Simula que a planilha acabou
    }
    result2 = batch_manager('READ', 0, 5, 2, mock_sheet_manager)
    assert result2 == []
    # Como não leu nada, ele recua totalmente o que avançou, voltando para o final das 3 linhas
    # Ou A3, mas o importante é que o start/end_row estão consistentes
    assert sheet_range.to_a1() == "A4:B3"


def test_batch_manager_read_mode_missing_manager(mocker):
    """Garante que READ sem sheet_manager retorna lista vazia e avisa erro."""
    mocker.patch("tsensor.core.serial_reader.sleep")
    mock_logger = mocker.patch("tsensor.core.serial_reader.logger")

    result = batch_manager('READ', 0, 10, 2)

    assert result == []
    mock_logger.error.assert_called_with(
        "sheet_manager é obrigatório no modo READ")


def test_offline_reading(mocker):
    """Verifica se offline_reading chama o batch_manager em loop para avançar range."""
    mock_batch = mocker.patch("tsensor.core.serial_reader.batch_manager")

    mock_manager = mocker.Mock(spec=StreamManager)
    # Roda o loop 2 vezes
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, True, False],
    )
    # Simula o __len__ do StreamManager (2 sensores ativos)
    mock_manager.__len__ = mocker.Mock(return_value=2)

    offline_reading(mock_manager)

    # Deve chamar o batch_manager 2 vezes no modo WRITE
    # columns = 1 (timestamp) + 2 (sensores) = 3
    assert mock_batch.call_count == 2
    mock_batch.assert_any_call('WRITE', 1, 10, 3)


def test_sheets_reading(mocker):
    """Verifica se sheets_reading consome do batch_manager em loop e despacha no manager."""
    mock_batch = mocker.patch("tsensor.core.serial_reader.batch_manager")

    # Na primeira iteração, retorna 2 linhas. Na segunda, retorna lista vazia.
    mock_batch.side_effect = [
        [["10:00:00", "25.0"], ["10:00:01", "25.1"]],
        [],
    ]

    mock_manager = mocker.Mock(spec=StreamManager)
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, True, False],
    )
    mock_manager.__len__ = mocker.Mock(return_value=1)  # 1 sensor

    # Mock do SheetsManager para pular a autenticação real
    mock_sheet_cls = mocker.patch("tsensor.core.serial_reader.SheetsManager")
    mock_sheet_inst = mock_sheet_cls.return_value

    sheets_reading(sheet_range, mock_manager)

    # Deve ter despachado 2 linhas (da primeira iteração do loop)
    assert mock_manager.dispatch_sheets.call_count == 2
    mock_manager.dispatch_sheets.assert_any_call(["10:00:00", "25.0"])

    # Deve ter chamado o setup do Google Sheets
    mock_sheet_inst.setup.assert_called_once()
