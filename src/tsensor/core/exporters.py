from abc import abstractmethod
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from loguru import logger
from pathlib import Path
from typing import Protocol, List, Tuple, Any

import io
import csv
import pandas as pd


class DataExporter(Protocol):
    """
    Protocolo que define a interface para exportação de dados.
    Qualquer classe de exportação (Google Sheets, CSV, Banco de Dados)
    deve implementar estes métodos.
    """

    @abstractmethod
    def setup(self) -> Any:
        """
        Prepara o exportador para uso.
        Pode envolver autenticação com serviços externos (Google, AWS)
        ou preparação de recursos locais (abrir arquivos, criar pastas).

        Returns:
            Any: Credenciais, cliente autenticado ou objeto de conexão.
        """
        ...

    @abstractmethod
    def export(self, data: List[Tuple[str, float]], destination_name: str) -> bool:
        """
        Envia a lista de amostras para o destino final.

        Args:
            data: Lista de tuplas contendo (timestamp, valor).
            destination_name: Nome do arquivo ou tabela de destino.

        Returns:
            bool: True se a exportação foi bem-sucedida, False caso contrário.
        """
        ...


class GoogleDriveExporter:
    def __init__(self, credentials_path: str, token_path: str, scopes: list, header: list):
        self._credentials_path = Path(credentials_path)
        self._token_path = Path(token_path)
        self._scopes = scopes
        self._service: Any = None
        self._header = header

    def setup(self) -> Any:
        creds: Credentials = None
        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._token_path),
                self._scopes,
            )

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._credentials_path),
                self._scopes,
            )
            creds = flow.run_local_server(port=0)

            with open(str(self._token_path), 'w') as token:
                token.write(creds.to_json())

        self._service = build('drive', 'v3', credentials=creds)
        return self._service

    def export(self, data: list[tuple[str, float]], destination_name: str) -> bool:
        file_metadata = {
            'name': 'dados_esp32',
            'mimeType': 'application/vnd.google-apps.spreadsheet',
        }

        # 1. Cria o arquivo CSV na memória RAM
        output = io.StringIO()
        writer = csv.writer(output)

        # Escreve o cabeçalho e os dados
        writer.writerow(self._header)
        writer.writerows(data)

        # 2. Prepara o conteúdo para o upload (converte para bytes)
        content = output.getvalue().encode('utf-8')
        fh = io.BytesIO(content)
        media = MediaIoBaseUpload(fh, mimetype='text/csv', resumable=True)

        try:
            arquivo_drive = self._service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            logger.info(f"Upload concluído! ID: {arquivo_drive.get('id')}")
        except Exception as err:
            logger.info(f'Upload falhou! erro "{err}"')
            return False

        return True


class CSVExporter:
    def __init__(self, directory: str, header: list):
        """
        Exportador de dados para formato CSV local.

        Args:
            directory: Pasta onde os arquivos serão salvos.
            header: Cabeçalho das colunas.
        """
        self._directory = Path(directory)
        self._header = header

    def setup(self) -> Path:
        """Garante que o diretório de exportação existe."""
        if not self._directory.exists():
            self._directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Diretório de exportação criado: {self._directory}")
        return self._directory

    def export(self, data: Any, destination_name: str, sep: str = ";", comment: str = None) -> bool:
        """
        Salva os dados em um arquivo CSV local.
        Suporta opcionalmente uma linha de comentário no topo e separador customizado.
        """
        file_path = self._directory / f"{destination_name}.csv"

        try:
            df = pd.DataFrame(data, columns=self._header)

            if comment:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {comment}\n")
                df.to_csv(file_path, index=False, sep=sep, mode='a')
            else:
                df.to_csv(file_path, index=False, sep=sep)

            logger.info(f"Dados exportados com sucesso para: {file_path}")
            return True
        except Exception as err:
            logger.error(f"Falha ao exportar CSV local: {err}")
            return False
