from tsensor.core.exporters import CSVExporter
import pytest
import io
from tsensor.core.exporters import GoogleDriveExporter


@pytest.fixture
def exporter():
    return GoogleDriveExporter(
        credentials_path="credentials.json",
        token_path="token.json",
        scopes=["https://www.googleapis.com/auth/drive.file"],
        header=["timestamp", "temperatura"]
    )


def test_google_drive_setup_with_existing_token(exporter, mocker):
    """Verifica se o setup carrega o token existente sem abrir navegador."""
    # Mock do Path.exists e Credentials
    mocker.patch("tsensor.core.exporters.Path.exists", return_value=True)
    mock_creds = mocker.patch(
        "tsensor.core.exporters.Credentials.from_authorized_user_file")
    mock_build = mocker.patch("tsensor.core.exporters.build")

    service = exporter.setup()

    mock_creds.assert_called_once()
    mock_build.assert_called_once_with(
        'drive', 'v3', credentials=mock_creds.return_value)
    assert service == mock_build.return_value


def test_google_drive_setup_triggers_oauth_flow(exporter, mocker):
    """Verifica se o setup inicia o fluxo OAuth caso o token não exista."""
    mocker.patch("tsensor.core.exporters.Path.exists", return_value=False)

    # Mocks das bibliotecas do Google
    mock_flow_cls = mocker.patch(
        "tsensor.core.exporters.InstalledAppFlow.from_client_secrets_file")
    mock_flow_inst = mock_flow_cls.return_value
    mock_creds = mock_flow_inst.run_local_server.return_value

    # Mock do open para não escrever no disco
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("tsensor.core.exporters.build")

    exporter.setup()

    mock_flow_cls.assert_called_once()
    mock_flow_inst.run_local_server.assert_called_once_with(port=0)
    mock_creds.to_json.assert_called_once()


def test_google_drive_export_success(exporter, mocker):
    """Verifica o processo de upload de dados com sucesso."""
    # Mock do serviço do Google Drive
    mock_service = mocker.Mock()
    exporter._service = mock_service

    # Simula a cadeia de chamadas: files().create().execute()
    mock_create = mock_service.files.return_value.create
    mock_execute = mock_create.return_value.execute
    mock_execute.return_value = {'id': '12345_google_id'}

    # Dados de teste
    data = [("10:00:01", 25.5), ("10:00:02", 26.0)]

    # Precisamos mockar o MediaIoBaseUpload para não validar o stream real nos asserts simples
    mocker.patch("tsensor.core.exporters.MediaIoBaseUpload")

    # Execução
    result = exporter.export(data, "teste_coleta")

    assert result is True
    mock_service.files.assert_called_once()
    mock_create.assert_called_once()
    # Verifica se o metadata foi enviado corretamente (mesmo que fixo por enquanto no código)
    args, kwargs = mock_create.call_args
    assert kwargs['body']['name'] == 'dados_esp32'
    assert kwargs['body']['mimeType'] == 'application/vnd.google-apps.spreadsheet'


def test_google_drive_export_failure_logs_error(exporter, mocker):
    """Verifica se erros no upload são capturados e logados."""
    mock_service = mocker.Mock()
    exporter._service = mock_service

    # Simula uma exceção durante o execute()
    mock_service.files.return_value.create.return_value.execute.side_effect = Exception(
        "Quota Exceeded")
    mock_logger = mocker.patch("tsensor.core.exporters.logger")

    data = [("10:00:01", 25.5)]
    result = exporter.export(data, "teste_falha")

    assert result is False
    # Verifica se o logger reportou o erro
    mock_logger.info.assert_called()
    # Pega a última chamada do logger para ver se contém a mensagem de erro
    last_call_args = mock_logger.info.call_args_list[-1][0][0]
    assert "Upload falhou" in last_call_args


@pytest.fixture
def csv_exporter(tmp_path):
    """Cria um CSVExporter em um diretório temporário para testes."""
    return CSVExporter(
        directory=str(tmp_path / "exports"),
        header=["timestamp", "temperatura"]
    )


def test_csv_exporter_setup_creates_directory(csv_exporter):
    """Verifica se o setup cria o diretório de exportação."""
    path = csv_exporter.setup()
    assert path.exists()
    assert path.is_dir()


def test_csv_exporter_export_saves_file(csv_exporter):
    """Verifica se o export salva os dados corretamente no disco."""
    csv_exporter.setup()
    data = [("10:00:01", 25.5), ("10:00:02", 26.0)]

    result = csv_exporter.export(data, "test_file")

    assert result is True

    file_path = csv_exporter._directory / "test_file.csv"
    assert file_path.exists()

    # Valida o conteúdo do arquivo
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert lines[0].strip() == "timestamp,temperatura"
        assert lines[1].strip() == "10:00:01,25.5"
        assert lines[2].strip() == "10:00:02,26.0"


def test_csv_exporter_failure_returns_false(csv_exporter, mocker):
    """Verifica se falhas na escrita retornam False."""
    csv_exporter.setup()
    # Mock do open para lançar erro (simulando permissão negada, p.ex)
    mocker.patch("builtins.open",
                 side_effect=PermissionError("Permission Denied"))

    result = csv_exporter.export([("10:00:01", 25.5)], "fail_file")
    assert result is False
