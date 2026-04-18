import pytest
from pathlib import Path
from tsensor.core.sheets import SheetsManager, SpreadSheetRange

@pytest.fixture
def mock_google_api(mocker):
    """Mocka todas as dependências externas do Google e do sistema de arquivos."""
    mocker.patch("tsensor.core.sheets.Path.exists", return_value=True)
    mocker.patch("tsensor.core.sheets.Path.open", mocker.mock_open(read_data='{"token": "dummy"}'))
    
    mock_creds = mocker.Mock()
    mock_creds.valid = True
    mock_creds.to_json.return_value = '{"token": "mocked"}'
    mocker.patch("tsensor.core.sheets.Credentials.from_authorized_user_file", return_value=mock_creds)
    
    mock_service = mocker.Mock()
    mock_build = mocker.patch("tsensor.core.sheets.build", return_value=mock_service)
    
    return {
        "service": mock_service,
        "build": mock_build,
        "creds": mock_creds
    }

def test_spreadsheet_range_initialization():
    """Valida se o range inicia corretamente na célula A1 por padrão."""
    sr = SpreadSheetRange()
    assert sr.to_a1() == "A1"

def test_major_row_advances_cursor():
    """Valida o avanço do cursor por linhas informando dimensões."""
    sr = SpreadSheetRange(1, 1)
    sr.major_row(2, 2) 
    assert sr.to_a1() == "A1:B2"
    sr.major_row(1, 3)
    assert sr.to_a1() == "A3:C3"

def test_major_col_advances_cursor():
    """Valida o avanço do cursor por colunas informando dimensões."""
    sr = SpreadSheetRange(1, 1)
    sr.major_col(2, 3)
    assert sr.to_a1() == "A1:B3"
    sr.major_col(2, 2)
    assert sr.to_a1() == "C1:D2"

def test_mixed_advancement():
    """Valida o avanço misto."""
    sr = SpreadSheetRange(1, 1)
    sr.major_row(1, 4) # A1:D1
    assert sr.to_a1() == "A1:D1"
    sr.major_row(2, 4) # A2:D3
    assert sr.to_a1() == "A2:D3"
    sr.major_col(1, 5) # E2:E6
    assert sr.to_a1() == "E2:E6"

def test_clear_with_custom_start():
    """Valida o reset do cursor."""
    sr = SpreadSheetRange(1, 1)
    sr.major_row(2, 2)
    sr.clear(10, 10)
    assert sr.to_a1() == "J10"

# --- Testes do SheetsManager ---

def test_sheets_manager_setup_success(mock_google_api):
    """Valida se o setup inicializa o serviço corretamente."""
    manager = SheetsManager()
    manager.setup()
    mock_google_api["build"].assert_called_once()
    assert manager._sheet is not None

def test_sheets_manager_export_calls_batch_update(mock_google_api, mocker):
    """Valida se o método export envia dados usando a instância do SpreadSheetRange injetada."""
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    mock_values = mocker.Mock()
    mock_batch = mocker.Mock()
    
    manager._sheet = mock_sheet_service
    mock_sheet_service.values.return_value = mock_values
    mock_values.batchUpdate.return_value = mock_batch
    mock_batch.execute.return_value = {"status": "success"}

    sr = SpreadSheetRange(1, 1)
    sr.major_row(2, 2) # Range A1:B2 definido pelo chamador
    
    result = manager.export([["data1", "data2"], ["data3", "data4"]], sr)
    
    assert mock_values.batchUpdate.called
    # Verifica se o range enviado no body do batchUpdate é o correto vindo do SpreadSheetRange
    call_args = mock_values.batchUpdate.call_args
    assert call_args[1]['body']['data'][0]['range'] == "Página1!A1:B2"
    assert result == {"status": "success"}

def test_sheets_manager_fetch_data_calls_batch_get(mock_google_api, mocker):
    """Valida se o método fetch_data busca dados usando a instância do SpreadSheetRange injetada."""
    manager = SheetsManager()
    mock_sheet_service = mocker.Mock()
    mock_values = mocker.Mock()
    mock_get = mocker.Mock()
    
    manager._sheet = mock_sheet_service
    mock_sheet_service.values.return_value = mock_values
    mock_values.batchGet.return_value = mock_get
    mock_get.execute.return_value = {"valueRanges": [{"values": [["fetched"]]}]}

    sr = SpreadSheetRange(1, 1)
    sr.major_col(2, 3) # Range A1:B3 definido pelo chamador
    
    result = manager.fetch_data(sr)
    
    assert mock_values.batchGet.called
    call_args = mock_values.batchGet.call_args
    assert call_args[1]['ranges'] == ["Página1!A1:B3"]
    assert result == {"valueRanges": [{"values": [["fetched"]]}]}

def test_sheets_manager_setup_expired_token_refresh(mocker, mock_google_api):
    """Valida o refresh de token expirado."""
    mock_creds = mock_google_api["creds"]
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "some_token"
    
    mocker.patch("tsensor.core.sheets.Request")
    
    manager = SheetsManager()
    manager.setup()
    
    mock_creds.refresh.assert_called_once()
