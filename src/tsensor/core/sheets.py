from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger
# from googleapiclient.errors import HttpError
from tsensor.core.exporters import DataExporter
from typing import Any, Optional, Iterator
from pathlib import Path
from queue import Queue, Empty


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

    @property
    def row(self):
        return self._row

    @property
    def col(self):
        return self._col

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

    def revert_rows(self, count: int) -> None:
        """
        Retrai o intervalo descartando 'count' linhas.
        Afeta tanto o início (row) quanto o fim (end_row) para manter a dimensão relativa,
        ou apenas o fim se for uma correção de leitura (unread).
        """
        if count <= 0:
            return

        # Para a janela deslizante, precisamos recuar o ponto de partida
        self._row -= count
        self._end_row -= count

        # Garante que o cursor não fique antes do início da planilha
        if self._row < 1:
            self._row = 1
        if self._end_row < 1:
            self._end_row = 1

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

    def setup(self, row_count: Optional[int] = None, col_count: Optional[int] = None, sheet_name: str = 'Página1') -> Any:

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
        self._spreadsheet = self._service.spreadsheets()
        self._sheet = self._spreadsheet

        # Configura a grade inicial se solicitado
        if row_count or col_count:
            self._ensure_grid_size(
                row_count or 1000, col_count or 3, sheet_name)

        return self._sheet

    def _ensure_grid_size(self, rows: int, cols: int, sheet_name: str) -> None:
        """Ajusta o tamanho da grade da planilha para garantir espaço suficiente, com margem de segurança."""
        try:
            # Obtém metadados para verificar se o ajuste é realmente necessário
            meta = self.fetch_metadata(name=sheet_name)
            current_rows = meta.get("rowCount", 0)
            current_cols = meta.get("columnCount", 0)

            # Só redimensiona se o alvo for maior que o atual
            # Adiciona uma folga de 1000 linhas para evitar redimensionamentos frequentes
            target_rows = max(rows, current_rows)
            if rows > current_rows:
                target_rows = rows + 1000

            target_cols = max(cols, current_cols)

            if target_rows > current_rows or target_cols > current_cols:
                logger.info(
                    f"Redimensionando planilha para {target_rows}x{target_cols}...")
                spreadsheet = self._sheet.get(
                    spreadsheetId=SPREADSHEET_ID).execute()
                sheet_id = None
                for s in spreadsheet.get('sheets', []):
                    if s.get('properties', {}).get('title') == sheet_name:
                        sheet_id = s.get('properties', {}).get('sheetId')
                        break

                if sheet_id is not None:
                    body = {
                        'requests': [{
                            'updateSheetProperties': {
                                'properties': {
                                    'sheetId': sheet_id,
                                    'gridProperties': {
                                        'rowCount': target_rows,
                                        'columnCount': target_cols
                                    }
                                },
                                'fields': 'gridProperties(rowCount, columnCount)'
                            }
                        }]
                    }
                    self._sheet.batchUpdate(
                        spreadsheetId=SPREADSHEET_ID, body=body).execute()
                    # Atualiza metadados locais após o sucesso
                    self._metadata["rowCount"] = target_rows
                    self._metadata["columnCount"] = target_cols
        except Exception as e:
            if "429" in str(e):
                logger.warning(
                    "Cota de gravação excedida ao tentar ajustar a grade.")
            else:
                logger.warning(
                    f"Ajuste de grade falhou: {e}")

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

        try:
            return self._sheet.values().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body=body
            ).execute()
        except Exception as e:
            # Se o erro for por limite de grade, tenta expandir e repetir UMA vez
            if "exceeds grid limits" in str(e):
                logger.warning(
                    f"Limite de grade atingido em {sheet_range.to_a1()}. Tentando expandir...")
                self._ensure_grid_size(
                    sheet_range._end_row, sheet_range._end_col, name)

                # Aguarda um pequeno cooldown se necessário ou apenas tenta novamente
                return self._sheet.values().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body=body
                ).execute()
            raise e

    def fetch_data(
        self,
        sheet_range: SpreadSheetRange,
        name: str = 'Página1',
        major_mode: str = 'ROWS',
    ) -> dict:

        range_ = f'{name}!{sheet_range.to_a1()}'
        try:
            result = self._sheet.values().batchGet(
                spreadsheetId=SPREADSHEET_ID,
                majorDimension=major_mode,
                ranges=[range_],
                valueRenderOption='UNFORMATTED_VALUE',
                dateTimeRenderOption='FORMATTED_STRING'
            ).execute()
            return result
        except Exception as e:
            # Se o erro for por limite de grade (leitura além do fim da planilha),
            # retorna vazio para que o polling continue tentando sem travar.
            if "exceeds grid limits" in str(e):
                return {'valueRanges': []}
            raise e

    def fetch_metadata(self, name: str = 'Página1') -> dict:
        """Obtém metadados da planilha: total de linhas, colunas e o cabeçalho."""
        # 1. Obtém propriedades da planilha (dimensões)
        spreadsheet = self._sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = spreadsheet.get('sheets', [])

        meta = {"rowCount": 0, "columnCount": 0, "header": []}

        for s in sheets:
            props = s.get('properties', {})
            if props.get('title') == name:
                grid = props.get('gridProperties', {})
                meta["rowCount"] = grid.get('rowCount', 0)
                meta["columnCount"] = grid.get('columnCount', 0)
                break

        # 2. Obtém a primeira linha (cabeçalho)
        header_result = self._sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{name}!1:1'
        ).execute()

        values = header_result.get('values', [])
        meta["header"] = values[0] if values else []

        self._metadata = meta
        return meta

    @property
    def metadata(self) -> dict:
        """Retorna os metadados cacheados da última execução de fetch_metadata."""
        return getattr(self, '_metadata', {"rowCount": 0, "columnCount": 0, "header": []})

    def delete_rows(self, start: int, count: int, sheet_name: str = 'Página1') -> dict:
        """
        Remove um intervalo de linhas e desloca as linhas restantes para cima.
        Útil para implementar buffer circular/janela deslizante.
        Índices baseados em 1 (Human-readable).
        """
        try:
            # Obtém o sheet_id necessário para batchUpdate
            spreadsheet = self._sheet.get(
                spreadsheetId=SPREADSHEET_ID, fields='sheets.properties').execute()
            sheet_id = None
            for s in spreadsheet.get('sheets', []):
                if s.get('properties', {}).get('title') == sheet_name:
                    sheet_id = s.get('properties', {}).get('sheetId')
                    break

            if sheet_id is None:
                raise ValueError(f"Sheet '{sheet_name}' não encontrado.")

            # API usa índices 0-based, inclusive no início e exclusivo no fim.
            # Ex: Deletar linhas 2 a 51 (Human) -> start=1, end=51 (0-based)
            body = {
                'requests': [{
                    'deleteRange': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': start - 1,
                            'endRowIndex': start - 1 + count
                        },
                        'shiftDimension': 'ROWS'
                    }
                }]
            }

            logger.info(
                f"Removendo {count} linhas da planilha '{sheet_name}' (Janela Deslizante)...")
            return self._sheet.batchUpdate(
                spreadsheetId=SPREADSHEET_ID, body=body).execute()

        except Exception as e:
            logger.error(f"Falha ao remover linhas da planilha: {e}")
            raise e


class SheetSleep:
    def __init__(self, request: int):
        self._count = 0
        self._req = request
        self._time = 1


class SyncCoordinator:
    def __init__(self, total_samples: int):
        self.write_cursor = SpreadSheetRange(row=2)
        self.read_cursor = SpreadSheetRange(row=2)
        self.total_samples = total_samples
        self.batch_size = 30000  # Inicia no modo histórico com batch grande
        self.mode = 'HISTORY'  # 'HISTORY' ou 'REALTIME'
        self._queue: Queue = Queue()

    def on_write_batch(self, sheet: Any, batch_size: int, sheets_lock: Any):
        """Gerencia a escrita de um lote e a lógica de janela deslizante."""
        # Janela Deslizante: Se o próximo lote ultrapassar o limite, removemos o topo
        if self.write_cursor.row + batch_size > self.total_samples + 1:
            delete_count = batch_size * 2
            with sheets_lock:
                sheet.delete_rows(start=2, count=delete_count)
                # Recua AMBOS os cursores para manter a sincronia física
                self.write_cursor.revert_rows(delete_count)
                self.read_cursor.revert_rows(delete_count)

        # Sinaliza que novos dados foram escritos
        self._queue.put(True)

    def get_read_params(self) -> tuple[int, bool]:
        """Retorna o (batch_size, deve_esperar) baseado no modo atual."""
        if self.mode == 'HISTORY':
            return self.batch_size, False
        return self.batch_size, True

    def switch_to_realtime(self):
        """Transiciona para o modo de tempo real."""
        if self.mode == 'HISTORY':
            logger.info("SyncCoordinator: Transicionando para modo REALTIME.")
            self.mode = 'REALTIME'
            # Limpa a fila para garantir sincronia com os novos dados
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Empty:
                    break

    def wait_for_data(self, timeout: float = 5.0) -> bool:
        """Aguarda sinal de novos dados (apenas em modo REALTIME)."""
        if self.mode == 'HISTORY':
            return True
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return False
