from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError
from tsensor.core.exporters import DataExporter
from typing import Any
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SAMPLE_RANGE_NAME = "Página1!A1:B3"
SPREADSHEET_ID = "1E9ws5ui_I5rw58dLbIXrFTggOQ87mCAAit3nCeSkFp8"


class SpreadSheetRange:
    def __init__(self, row: int = 1, col: int = 1):
        self._row = row
        self._col = col
        self._end_row = row
        self._end_col = col
        self._is_first = True

    def calculate_letter(self, index: int) -> str:
        """Converte índice numérico (1-based) para letras (1=A, 27=AA)."""
        letter = ''
        while index > 0:
            index, rest = divmod(index - 1, 26)
            letter = chr(65 + rest) + letter
        return letter

    def major_row(self, rows: int, cols: int) -> None:
        """Avança para a próxima linha disponível com base nas dimensões informadas."""
        if rows <= 0 or cols <= 0:
            return
        if not self._is_first:
            self._row = self._end_row + 1

        self._end_row = self._row + rows - 1
        self._end_col = self._col + cols - 1
        self._is_first = False

    def major_col(self, cols: int, rows: int) -> None:
        """Avança para a próxima coluna disponível com base nas dimensões informadas."""
        if rows <= 0 or cols <= 0:
            return
        if not self._is_first:
            self._col = self._end_col + 1

        self._end_col = self._col + cols - 1
        self._end_row = self._row + rows - 1
        self._is_first = False

    def to_a1(self) -> str:
        """Retorna o range do bloco atual em notação A1."""
        s_letter = self.calculate_letter(self._col)
        e_letter = self.calculate_letter(self._end_col)

        start_cell = f"{s_letter}{self._row}"
        if self._row == self._end_row and self._col == self._end_col:
            return start_cell

        return f"{start_cell}:{e_letter}{self._end_row}"

    @property
    def current_rows(self) -> int:
        """Retorna a quantidade de linhas no intervalo atual."""
        return (self._end_row - self._row) + 1

    def revert_rows(self, unread_rows: int) -> None:
        """
        Retrai o final do intervalo descartando as linhas não lidas.
        Utilizado para compensar leituras que atingiram o final da planilha (EOF),
        garantindo que a próxima leitura inicie logo após a última linha válida.
        """
        if unread_rows <= 0:
            return
            
        self._end_row -= unread_rows
        
        # Garante que o cursor final não fique antes do início
        if self._end_row < 0:
            self._end_row = 0

    def clear(self, row: int = 1, col: int = 1) -> None:
        """Reseta o cursor para uma nova posição inicial."""
        self._row = row
        self._col = col
        self._end_row = row
        self._end_col = col
        self._is_first = True


class SheetsManager(DataExporter):

    def __init__(
        self,
        credentials_path: str | Path = 'credentials.json',
        token_path: str | Path = 'token.json',
        sheet: Any = None
    ):
        self._service: Any = None
        self._sheet = sheet
        self._credentials_path = Path(credentials_path)
        self._token_path = Path(token_path)

    def setup(self) -> Any:

        creds = None
        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self._token_path, "w") as token:
                token.write(creds.to_json())

        self._service = build("sheets", "v4", credentials=creds)
        self._sheet = self._service.spreadsheets()
        return self._sheet

    def export(
        self,
        data: list[list],
        sheet_range: SpreadSheetRange,
        name: str = 'Página1',
        major_mode: str = 'ROWS',
    ) -> dict:

        datas = {
            'range': f'{name}!{sheet_range.to_a1()}',
            'values': data,
            'majorDimension': major_mode,
        }

        body = {
            'valueInputOption': 'USER_ENTERED',
            'data': [datas]
        }

        result = self._sheet.values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body
        ).execute()
        return result

    def fetch_data(
        self,
        sheet_range: SpreadSheetRange,
        name: str = 'Página1',
        major_mode: str = 'ROWS',
    ) -> dict:

        range_ = f'{name}!{sheet_range.to_a1()}'
        result = self._sheet.values().batchGet(
            spreadsheetId=SPREADSHEET_ID,
            majorDimension=major_mode,
            ranges=[range_],
        ).execute()
        return result
