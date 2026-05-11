import pytest
from pathlib import Path
from tsensor.core.sheets import SheetsManager, SpreadSheetRange


@pytest.fixture
def mock_sheets_deps(mocker):
    """Isola completamente o SheetsManager de dependências externas (FileSystem e Google)."""
    # Importa de forma segura
    try:
        from tests.conftest import original_sheets_setup
        mocker.patch("tsensor.core.sheets.SheetsManager.setup",
                     new=original_sheets_setup)
    except ImportError:
        pass

    # 1. Mock do Path com instâncias controladas
    m_path_class = mocker.patch("tsensor.core.sheets.Path")
    mock_instances = {}

    def path_side_effect(p):
        p_str = str(p)
        if p_str not in mock_instances:
            m_p = mocker.MagicMock(spec=Path)
            m_p.__str__.return_value = p_str
            m_p.exists.return_value = True
            mock_instances[p_str] = m_p
        return mock_instances[p_str]
    m_path_class.side_effect = path_side_effect

    # 2. Mock do builtin 'open' no namespace do módulo
    m_open = mocker.patch("tsensor.core.sheets.open",
                          mocker.mock_open(read_data='{"token": "dummy"}'))

    # 3. Mock Google Auth e API
    mock_creds = mocker.Mock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.refresh_token = "some_refresh_token"
    mock_creds.to_json.return_value = '{"token": "mocked_json"}'

    mocker.patch(
        "tsensor.core.sheets.Credentials.from_authorized_user_file", return_value=mock_creds)
    m_flow = mocker.patch("tsensor.core.sheets.InstalledAppFlow")
    m_request = mocker.patch("tsensor.core.sheets.Request")
    m_build = mocker.patch("tsensor.core.sheets.build")

    return {
        "path": m_path_class,
        "instances": mock_instances,
        "open": m_open,
        "creds": mock_creds,
        "flow": m_flow,
        "build": m_build,
        "request": m_request
    }

# --- Testes de Lógica: SpreadSheetRange ---


def test_spreadsheet_range_initialization():
    sr = SpreadSheetRange()
    assert sr.to_a1() == "A1"


def test_major_row_advances_cursor():
    sr = SpreadSheetRange(1, 1)
    sr.major_row(2, 2)
    assert sr.to_a1() == "A1:B2"
    sr.major_row(1, 3)
    assert sr.to_a1() == "A3:C3"


def test_major_col_advances_cursor():
    sr = SpreadSheetRange(1, 1)
    sr.major_col(2, 3)
    assert sr.to_a1() == "A1:B3"
    sr.major_col(2, 2)
    assert sr.to_a1() == "C1:D2"


def test_mixed_advancement():
    sr = SpreadSheetRange(1, 1)
    sr.major_row(1, 4)
    assert sr.to_a1() == "A1:D1"
    sr.major_col(1, 5)
    assert sr.to_a1() == "E1:E5"


def test_clear_with_custom_start():
    sr = SpreadSheetRange(1, 1)
    sr.major_row(2, 2)
    sr.clear(10, 10)
    assert sr.to_a1() == "J10"


def test_current_rows_property():
    sr = SpreadSheetRange(1, 1)
    # Range atual: A1
    assert sr.current_rows == 1

    sr.major_row(5, 2)
    # Range atual: A1:B5
    assert sr.current_rows == 5


def test_revert_rows():
    sr = SpreadSheetRange(1, 1)
    sr.major_row(5, 2)
    # Range: A1:B5 (row=1, end_row=5)

    sr.revert_rows(2)
    # Novo comportamento: recua row e end_row.
    # row=1-2 -> 1. end_row=5-2 -> 3.
    assert sr.row == 1
    assert sr._end_row == 3

    # Próximo major_row inicia no 4 (end_row + 1)
    sr.major_row(5, 2)
    # Range novo: A4:B8
    assert sr.to_a1() == "A4:B8"

    sr.revert_rows(10)
    # 4-10 -> 1. 8-10 -> 1.
    assert sr.row == 1
    assert sr._end_row == 1

    # Próximo major_row inicia no 1 (is_first foi resetado? Não, mas end_row=1 então inicia em 2)
    # Se is_first for False, inicia em end_row + 1 = 2.
    sr.major_row(5, 2)
    assert sr.to_a1() == "A2:B6"

# --- Testes de Integração: SheetsManager ---


def test_sheets_manager_setup_success(mock_sheets_deps):
    manager = SheetsManager()
    manager.setup()
    mock_sheets_deps["build"].assert_called_once()
    assert manager._sheet is not None


def test_sheets_manager_export_calls_batch_update(mock_sheets_deps, mocker):
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    manager._sheet = mock_sheet_service

    sr = SpreadSheetRange(1, 1)
    sr.major_row(2, 2)

    manager.export([["d1", "d2"]], sr)
    assert mock_sheet_service.values().batchUpdate.called
    call_args = mock_sheet_service.values().batchUpdate.call_args[1]
    assert call_args['body']['data'][0]['range'] == "Página1!A1:B2"


def test_sheets_manager_fetch_data_calls_batch_get(mock_sheets_deps, mocker):
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    manager._sheet = mock_sheet_service

    sr = SpreadSheetRange(1, 1)
    sr.major_col(2, 3)

    manager.fetch_data(sr)
    assert mock_sheet_service.values().batchGet.called
    call_args = mock_sheet_service.values().batchGet.call_args[1]
    assert call_args['ranges'] == ["Página1!A1:B3"]


def test_sheets_manager_fetch_data_handles_grid_limits(mock_sheets_deps, mocker):
    """Verifica se fetch_data retorna vazio ao atingir o limite da grade (EOF simulado)."""
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    manager._sheet = mock_sheet_service

    # Simula a exceção que a Google API lança quando o range está fora do grid
    mock_sheet_service.values.return_value.batchGet.return_value.execute.side_effect = Exception(
        "Range exceeds grid limits. Max rows: 100, max columns: 3"
    )

    sr = SpreadSheetRange(1, 1)
    sr.major_row(10, 3)

    result = manager.fetch_data(sr)

    # Deve retornar o formato esperado de dados vazios em vez de estourar a exceção
    assert result == {'valueRanges': []}


def test_sheets_manager_fetch_metadata_success(mock_sheets_deps, mocker):
    """Valida a extração de metadados (dimensões e cabeçalho)."""
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    manager._sheet = mock_sheet_service

    # 1. Mock do spreadsheet.get().execute() -> Dimensões
    mock_spreadsheet_resp = {
        'sheets': [{
            'properties': {
                'title': 'Página1',
                'gridProperties': {'rowCount': 100, 'columnCount': 10}
            }
        }]
    }
    mock_sheet_service.get.return_value.execute.return_value = mock_spreadsheet_resp

    # 2. Mock do values().get().execute() -> Cabeçalho
    mock_values_resp = {'values': [['timestamp', 'temp', 'pres']]}
    mock_sheet_service.values.return_value.get.return_value.execute.return_value = mock_values_resp

    # Execução
    result = manager.fetch_metadata("Página1")

    # Verificações
    assert result["rowCount"] == 100
    assert result["columnCount"] == 10
    assert result["header"] == ['timestamp', 'temp', 'pres']
    assert manager.metadata == result

    # Verifica se as chamadas foram corretas
    mock_sheet_service.get.assert_called_with(
        spreadsheetId="1E9ws5ui_I5rw58dLbIXrFTggOQ87mCAAit3nCeSkFp8")
    mock_sheet_service.values.return_value.get.assert_called_with(
        spreadsheetId="1E9ws5ui_I5rw58dLbIXrFTggOQ87mCAAit3nCeSkFp8",
        range="Página1!1:1"
    )


def test_sheets_manager_setup_expired_token_refresh(mock_sheets_deps):
    mock_creds = mock_sheets_deps["creds"]
    mock_creds.valid = False
    mock_creds.expired = True

    manager = SheetsManager()
    manager.setup()

    mock_creds.refresh.assert_called_once()


def test_sheets_manager_setup_new_login(mock_sheets_deps):
    # Simula que o TOKEN não existe (força novo login via credenciais)
    mock_sheets_deps["path"]("token.json").exists.return_value = False

    mock_flow_class = mock_sheets_deps["flow"]
    mock_flow_instance = mock_flow_class.from_client_secrets_file.return_value
    mock_flow_instance.run_local_server.return_value = mock_sheets_deps["creds"]

    manager = SheetsManager(
        credentials_path="creds.json", token_path="token.json")
    manager.setup()

    # Valida se usou o arquivo de credenciais correto e salvou no token.json
    mock_flow_class.from_client_secrets_file.assert_called_once_with(
        "creds.json", ["https://www.googleapis.com/auth/spreadsheets"]
    )
    assert mock_sheets_deps["open"].called


def test_sheets_manager_delete_rows_calls_batch_update(mock_sheets_deps, mocker):
    """Verifica se delete_rows chama a API com os índices e sheetId corretos."""
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    manager._sheet = mock_sheet_service

    # Mock do retorno do get() para encontrar o sheetId da aba
    mock_sheet_service.get.return_value.execute.return_value = {
        'sheets': [{
            'properties': {'title': 'Página1', 'sheetId': 12345}
        }]
    }

    # Executa a deleção de 50 linhas a partir da linha 2 (índice 1)
    manager.delete_rows(start=2, count=50)

    assert mock_sheet_service.batchUpdate.called
    call_args = mock_sheet_service.batchUpdate.call_args[1]

    # A API usa 0-based: start 2 -> index 1. end 51 -> index 51 (exclusivo)
    expected_request = {
        'deleteRange': {
            'range': {
                'sheetId': 12345,
                'dimension': 'ROWS',
                'startRowIndex': 1,
                'endRowIndex': 51
            },
            'shiftDimension': 'ROWS'
        }
    }
    assert call_args['body']['requests'][0] == expected_request


def test_sliding_window_cursor_logic():
    """Valida a manipulação manual do cursor para compensar o deslocamento da janela deslizante."""
    sr = SpreadSheetRange(row=951)
    batch_size = 50

    # Avança para o final do lote (951:1000)
    sr.major_row(batch_size, 3)
    assert sr._row == 951
    assert sr._end_row == 1000

    # Ao deletar 50 linhas do topo, as linhas na memória devem "recuar"
    # para que o próximo major_row aponte para o lugar correto
    sr._row -= batch_size
    sr._end_row -= batch_size

    assert sr._row == 901
    assert sr._end_row == 950

    # Próximo avanço volta para a posição correta de append
    sr.major_row(batch_size, 3)
    assert sr._row == 951
    assert sr._end_row == 1000
