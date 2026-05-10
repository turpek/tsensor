import pytest
from tsensor.core.serial_reader import serial_reading, sheets_reading
from tsensor.core.sheets import SpreadSheetRange, SheetsManager
from tsensor.core.handlers import StreamManager
from tsensor.extensions import app_status


def test_serial_reading_basic_loop(mocker):
    """Verifica se o loop de leitura serial consome dados e despacha para o local_manager."""
    # 1. Mock do Serial
    mock_serial_cls = mocker.patch("tsensor.core.serial_reader.Serial")
    mock_ser_instance = mock_serial_cls.return_value
    # Fornece timestamps para sincronização (precisa de max_samples=10 agora) e depois dados
    sync_samples = [b"U=1714240000\n"] * 12
    data_samples = [b"T=2500\n", b""]
    mock_ser_instance.readline.side_effect = sync_samples + data_samples

    # 2. Mock do StreamManager (Global - usado para controle)
    mock_manager = mocker.Mock(spec=StreamManager)
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, True, False])

    # 3. Mock do Local Manager (retornado pelo setup_serial_manager)
    mock_local_manager = mocker.Mock(spec=StreamManager)
    mocker.patch("tsensor.core.serial_reader.setup_serial_manager",
                 return_value=mock_local_manager)

    # Mock do SheetsManager para evitar exportação real
    mock_sheet_cls = mocker.patch("tsensor.core.serial_reader.SheetsManager")

    # Mock do config
    mocker.patch("tsensor.core.serial_reader.config", {
                 "acquisition": {"serial_batch_size": 50}})

    # 4. Execução
    serial_reading(port="/dev/ttyUSB0", baudrate=115200,
                   stream_manager=mock_manager)

    # 5. Asserts
    # Deve despachar para o local_manager
    assert mock_local_manager.dispatch.call_count >= 1
    mock_ser_instance.close.assert_called_once()


def test_serial_reading_handles_errors(mocker):
    """Verifica se a função lida com falhas na abertura da porta."""
    from tsensor.core.serial_connection import SerialException
    mocker.patch("tsensor.core.serial_reader.Serial",
                 side_effect=SerialException("Port busy"))

    mock_manager = mocker.Mock(spec=StreamManager)
    serial_reading("COM1", 9600, mock_manager)

    assert app_status["connected"] is False
    assert "Port busy" in app_status["error"]


def test_sheets_reading_success_loop(mocker):
    """Verifica se sheets_reading consome dados da planilha e respeita o loop."""
    mocker.patch("tsensor.core.serial_reader.time.sleep")
    # Mock do acq_gate para retornar True imediatamente e não travar o teste
    mock_gate = mocker.patch("tsensor.core.serial_reader.acq_gate")
    mock_gate.wait.return_value = True

    # Mock do SheetsManager
    mock_sheet_cls = mocker.patch("tsensor.core.serial_reader.SheetsManager")
    mock_sheet_inst = mock_sheet_cls.return_value

    # Simula retorno de 2 linhas
    mock_sheet_inst.fetch_data.return_value = {
        'valueRanges': [{'values': [["10:00:00", "25.0"], ["10:00:01", "25.1"]]}]
    }

    mock_manager = mocker.Mock(spec=StreamManager)
    # Roda 1 vez e para
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, False])
    mock_manager.__len__ = mocker.Mock(return_value=1)

    sheets_reading(mock_manager)

    # Verificações
    mock_sheet_inst.setup.assert_called_once()
    assert mock_manager.dispatch.call_count == 2
    # Verifica se o primeiro argumento da chamada foi um iterador (não comparamos o objeto iterador diretamente)
    args, _ = mock_manager.dispatch.call_args
    assert isinstance(args[0], type(iter([])))


def test_serial_reading_skips_invalid_data(mocker):
    """Garante que linhas vazias, corrompidas ou incompletas são ignoradas."""
    # 1. Mock do Serial
    mock_serial_cls = mocker.patch("tsensor.core.serial_reader.Serial")
    mock_ser_instance = mock_serial_cls.return_value

    # Sequência de leitura:
    # 1. Sync (pular)
    # 2. Vazio
    # 3. Corrompido (só prefixo)
    # 4. Incompleto (falta um sensor)
    # 5. Válido (para fechar um ciclo)
    # 6. Stop
    sync_samples = [b"U=1714240000\n"] * 12
    invalid_samples = [
        b"\n",               # 1. Vazio
        b"T=\n",             # 2. Corrompido
        b"T=25.5\n",         # 3. Incompleto (falta P= se houver 2 sensores)
        b"T=25.5,P=1013\n"   # 4. Válido
    ]
    mock_ser_instance.readline.side_effect = sync_samples + invalid_samples + [b""]

    # 2. Mock do StreamManager principal
    mock_manager = mocker.Mock(spec=StreamManager)
    # Loop roda enquanto True, para no False
    # Precisamos de chamadas suficientes para consumir os samples
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True] * (len(invalid_samples) + 1) + [False]
    )

    # 3. Configuração do Local Manager com 2 handlers (Temp e Pressão)
    from tsensor.core.handlers import LM35Handler, MPS20Handler
    from tsensor.core.data_stream import DataStream

    local_sm = StreamManager()
    local_sm.configure()
    local_sm.add_handler("T", LM35Handler(DataStream(10), DataStream(
        10), DataStream(10), 4095, 3.3))
    local_sm.add_handler("P", MPS20Handler(DataStream(10), DataStream(
        10), DataStream(10), 4095, 3.3))

    mocker.patch("tsensor.core.serial_reader.setup_serial_manager",
                 return_value=local_sm)

    # Espiona o dispatch do local_sm
    spy_dispatch = mocker.spy(local_sm, "dispatch")

    # Mock do SheetsManager
    mocker.patch("tsensor.core.serial_reader.SheetsManager")
    mocker.patch("tsensor.core.serial_reader.config", {
        "acquisition": {"serial_batch_size": 10},
        "sensors": [{"name": "T", "type": "LM35"}, {"name": "P", "type": "MPS20"}]
    })

    # 4. Execução
    serial_reading(port="COM1", baudrate=115200, stream_manager=mock_manager)

    # 5. Asserts
    # Apenas a última linha (Válida) deve ter passado pelo validate e chegado no dispatch
    # Note: O loop do serial_reading chama local_manager.dispatch(line)
    assert spy_dispatch.call_count == 1
    # Verifica se o dado despachado foi a linha completa
    assert "T=25.5,P=1013" in spy_dispatch.call_args[0][0]


def test_sheets_reading_quota_error_handling(mocker):
    """Verifica se a função lida com o erro 429 (Quota Exceeded) do Google."""
    mock_sleep = mocker.patch("tsensor.core.serial_reader.time.sleep")
    # Mock do acq_gate
    mock_gate = mocker.patch("tsensor.core.serial_reader.acq_gate")
    mock_gate.wait.return_value = True

    mock_sheet_cls = mocker.patch("tsensor.core.serial_reader.SheetsManager")
    mock_sheet_inst = mock_sheet_cls.return_value

    # Simula erro 429 na primeira chamada e sucesso na segunda
    from googleapiclient.errors import HttpError
    mock_response = mocker.Mock()
    mock_response.status = 429
    mock_response.reason = "Quota Exceeded"

    mock_sheet_inst.fetch_data.side_effect = [
        Exception("429 Quota Exceeded"),
        {'valueRanges': []}
    ]

    mock_manager = mocker.Mock(spec=StreamManager)
    # Roda 2 vezes para testar o retry e para
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, True, False])
    mock_manager.__len__ = mocker.Mock(return_value=1)

    sheets_reading(mock_manager)

    # Deve ter chamado o sleep de 15 segundos (cooldown)
    mock_sleep.assert_any_call(15)


def test_sheets_reading_reverts_cursor_when_empty(mocker):
    """Verifica se o cursor volta se não houver dados novos na planilha."""
    mocker.patch("tsensor.core.serial_reader.time.sleep")
    # Mock do acq_gate
    mock_gate = mocker.patch("tsensor.core.serial_reader.acq_gate")
    mock_gate.wait.return_value = True

    mock_sheet_cls = mocker.patch("tsensor.core.serial_reader.SheetsManager")
    mock_sheet_inst = mock_sheet_cls.return_value
    mock_sheet_inst.fetch_data.return_value = {
        'valueRanges': []}  # Planilha "vazia" no momento

    mock_manager = mocker.Mock(spec=StreamManager)
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, False])
    mock_manager.__len__ = mocker.Mock(return_value=1)

    # Espiona o SpreadSheetRange para ver o revert_rows
    # Como SpreadSheetRange é instanciado localmente, vamos mockar a classe
    mock_range_cls = mocker.patch(
        "tsensor.core.serial_reader.SpreadSheetRange")
    mock_range_inst = mock_range_cls.return_value

    sheets_reading(mock_manager)

    # Deve ter chamado revert_rows porque lines estava vazio
    mock_range_inst.revert_rows.assert_called()


def test_sheets_reading_uses_correct_column_count(mocker):
    """Verifica se sheets_reading utiliza len(stream_manager) para definir o range de colunas."""
    mocker.patch("tsensor.core.serial_reader.time.sleep")
    # Mock do acq_gate
    mock_gate = mocker.patch("tsensor.core.serial_reader.acq_gate")
    mock_gate.wait.return_value = True

    # Mock do SheetsManager
    mock_sheet_cls = mocker.patch("tsensor.core.serial_reader.SheetsManager")
    mock_sheet_inst = mock_sheet_cls.return_value
    mock_sheet_inst.fetch_data.return_value = {'valueRanges': []}

    # Mock do StreamManager com 4 handlers (ex: Timestamp + 3 Sensores)
    mock_manager = mocker.Mock(spec=StreamManager)
    type(mock_manager).is_active = mocker.PropertyMock(
        side_effect=[True, False])
    mock_manager.__len__ = mocker.Mock(return_value=4)

    # Mock do SpreadSheetRange para capturar a chamada major_row
    mock_range_cls = mocker.patch(
        "tsensor.core.serial_reader.SpreadSheetRange")
    mock_range_inst = mock_range_cls.return_value

    sheets_reading(mock_manager)

    # Verifica se major_row foi chamado com cols=4
    # major_row(self, rows: int, cols: int)
    mock_range_inst.major_row.assert_called_once_with(mocker.ANY, 4)
