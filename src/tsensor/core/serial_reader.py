from loguru import logger
from tsensor.core.serial_connection import Serial, SerialException
from tsensor.core.handlers import StreamManager
from tsensor.core.sheets import SheetsManager, SpreadSheetRange
from tsensor.extensions import app_status, sheet_range
from time import sleep
from typing import Optional, Union


def serial_reading(
    port: str, baudrate: int, stream_manager: StreamManager, timeout: float = 1.0
) -> None:
    try:
        ser = Serial(port, baudrate, timeout=timeout)
        app_status["connected"] = True
        app_status["error"] = None
        logger.info(f"Conexão serial estabelecida em {port}")
    except SerialException as e:
        app_status["connected"] = False
        app_status["error"] = str(e)
        logger.error(f"Erro ao abrir porta serial {port}: {e}")
        return None

    logger.info("Iniciando coleta...")

    while stream_manager.is_active:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        stream_manager.dispatch(line)

    ser.close()
    logger.info(
        f"Coleta finalizada: {stream_manager.count_samples} amostras",
    )


def sheets_reading(
    sheet_range: SpreadSheetRange, stream_manager: StreamManager, timeout: float = 1.0
) -> None:
    try:
        sheet = SheetsManager()
        sheet.setup()
        app_status["connected"] = True
        app_status["error"] = None
        logger.info("Conexão estabelecida no Google Sheets")
    except Exception as e:
        app_status["connected"] = False
        app_status["error"] = str(e)
        logger.error("Erro ao tentar se conectar ao Google Sheets")
        return None

    logger.info("Iniciando coleta a partir das planilhas...")
    cols = 1 + len(stream_manager)
    batch_size = 50

    while stream_manager.is_active:
        lines = batch_manager('READ', 1, batch_size, cols, sheet)
        if isinstance(lines, list):
            for line in lines:
                stream_manager.dispatch_sheets(line)

    logger.info(
        f"Coleta finalizada: {stream_manager.count_samples} amostras",
    )


def offline_reading(
    stream_manager: StreamManager, timeout: float = 1.0
) -> None:
    """
    Função que substitui o `serial_reading` no modo offline.
    Apenas avança o cursor no SpreadSheetRange chamando o batch_manager,
    para simular a chegada de novos dados e permitir que o sheets_reading os leia.
    """
    logger.info("Iniciando controle de lotes (Modo Offline)...")

    # 1 coluna para timestamp + 1 coluna para cada sensor ativo
    cols = 1 + len(stream_manager)
    batch_size = 10
    sleep_time = 1

    while stream_manager.is_active:
        # Atualiza o range a cada ciclo (como se novos dados estivessem chegando)
        batch_manager('WRITE', sleep_time, batch_size, cols)

    logger.info("Controle de lotes (Modo Offline) finalizado.")


def batch_manager(
    mode: str,
    sl: int,
    row: int,
    col: int,
    sheet_manager: Optional[SheetsManager] = None
) -> Union[SpreadSheetRange, list]:
    """
        Função que centraliza o gerenciamento de lotes de dados.

        mode: define o tipo de operação:
              'WRITE': row e col atualizam o range, simulando gravação.
              'READ': busca os dados do range atual, avançando o cursor e lidando com o EOF.
        sl: tempo de aguardo para outra chamada da api
    """
    if mode == 'WRITE':
        sheet_range.major_row(row, col)
        sleep(sl)
        return sheet_range
    elif mode == 'READ':
        if not sheet_manager:
            logger.error("sheet_manager é obrigatório no modo READ")
            sleep(sl)
            return []

        sheet_range.major_row(row, col)
        try:
            print(" A1", sheet_range.to_a1())
            result = sheet_manager.fetch_data(sheet_range)
            value_ranges = result.get('valueRanges', [])

            if not value_ranges or not value_ranges[0].get('values', []):
                # Não encontrou valores na planilha (fim da planilha)
                sheet_range.revert_rows(row)
                sleep(sl)
                return []

            lines = value_ranges[0].get('values', [])

            if len(lines) < row:
                # Leu menos dados do que pediu, compensa o fim do cursor
                unread = row - len(lines)
                sheet_range.revert_rows(unread)

            sleep(sl)
            return lines
        except Exception as e:
            logger.error(f"Erro ao buscar dados do Sheets: {e}")
            sleep(sl)
            return []
    return []
