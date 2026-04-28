from loguru import logger
from tsensor.core.serial_connection import Serial, SerialException
from tsensor.core.handlers import StreamManager, sync_time, TimestampHandler
from tsensor.core.sheets import SheetsManager, SpreadSheetRange
from tsensor.extensions import app_status, acq_gate, config, setup_serial_manager, sheets_lock
import time


def synchronize_time(ser: Serial) -> None:
    logger.info("Iniciando a sincronização do tempo (Amostragem Múltipla)...")
    ser.reset_input_buffer()
    # Descarta a primeira linha potencial incompleta
    ser.readline()

    offsets = []
    attempts = 0
    max_samples = 10

    while len(offsets) < max_samples and attempts < 50:
        attempts += 1
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        t_arrival = time.time()
        ts_mcu = TimestampHandler.convert(line)

        if ts_mcu:
            # t_arrival = ts_mcu + offset -> offset = t_arrival - ts_mcu
            offsets.append(t_arrival - ts_mcu)
            if len(offsets) % 2 == 0:
                logger.debug(f"Sincronizando... {len(offsets)}/{max_samples}")

    if offsets:
        # Usamos o mínimo observado para o offset. 
        # O menor offset representa o pacote que viajou com menor latência USB/Buffer.
        sync_time.offset = min(offsets)
        logger.info(f"Tempo sincronizado! Offset: {sync_time.offset:.4f}s (baseado em {len(offsets)} amostras)")
    else:
        logger.error("Falha ao sincronizar tempo: nenhum timestamp válido recebido.")



def serial_reading(
    port: str, baudrate: int, stream_manager: StreamManager, timeout: float = 1.0
) -> None:
    """Aquisição Serial em tempo real com exportação em lotes para o Google Sheets."""
    try:
        ser = Serial(port, baudrate, timeout=timeout)
        app_status["connected"] = True
        app_status["error"] = None
        logger.info(f"Conexão serial estabelecida em {port} (Tempo Real)")
    except SerialException as e:
        app_status["connected"] = False
        app_status["error"] = str(e)
        logger.error(f"Erro ao abrir porta serial {port}: {e}")
        return None

    # Configuração do manager local para lotes
    local_manager = setup_serial_manager(config)
    batch_size = config["acquisition"].get("serial_batch_size", 50)

    # Gerenciador de exportação local
    sheet = SheetsManager()
    sheet.setup()
    export_cursor = SpreadSheetRange(row=2)

    acq_gate.enable()
    synchronize_time(ser)
    logger.info(
        f"Iniciando coleta Serial (Modo Batch Export: {batch_size})...")

    try:
        ser.reset_input_buffer()
        while stream_manager.is_active:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not local_manager.validate(line):
                continue

            # Despacha APENAS para o manager local (acumulação para Sheets)
            local_manager.dispatch(line)

            # Assume que todos os handlers têm o mesmo tamanho
            first_handler = next(iter(local_manager._handlers.values()))

            if len(first_handler.data) >= batch_size:
                logger.info(f"Exportando lote de {batch_size} amostras (Modo COLUMNS)...")

                handlers = list(local_manager._handlers.values())

                # Prepara os dados: cada lista interna é uma COLUNA completa
                # handlers[0] é o TimestampHandler, os demais são sensores
                export_data = [list(h.data.samples) for h in handlers]

                # Calcula a latência do lote (atraso de retenção/transporte)
                if export_data and export_data[0]:
                    last_mcu_ts = export_data[0][-1]
                    tf = time.time()
                    app_status["batch_latency"] = tf - last_mcu_ts

                # Avança o cursor e exporta usando COLUMNS
                with sheets_lock:
                    export_cursor.major_row(batch_size, len(handlers))
                    sheet.export(export_data, export_cursor, major_mode='COLUMNS')
                    acq_gate.signal(True)
                    time.sleep(1)

                # Limpa os buffers locais
                for h in handlers:
                    h.data.clear()

                # Limpa o buffer da serial para garantir que o próximo lote comece com dados recentes
                # ser.reset_input_buffer()

                # Reset manual do contador interno do manager local
                local_manager._count = 0

    except Exception as e:
        logger.error(f"Erro crítico na aquisição Serial: {e}")
    finally:
        ser.close()
        logger.info("Coleta Serial finalizada.")


def sheets_reading(
    stream_manager: StreamManager, timeout: float = 1.0
) -> None:
    """Realiza a leitura do Google Sheets de forma síncrona e autônoma."""
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

    # Cursor de leitura local, iniciando na linha 2 (após cabeçalho)
    read_cursor = SpreadSheetRange(row=2)
    cols = len(stream_manager)

    # Batch size configurável via TOML (padrão 200)
    batch_size = config["acquisition"].get("serial_batch_size", 200)

    logger.info("Iniciando monitoramento da planilha...")

    while stream_manager.is_active:
        try:
            if acq_gate.wait(5):
                # Avança o cursor para o próximo lote
                read_cursor.major_row(batch_size, cols)

                # Busca dados diretamente
                with sheets_lock:
                    result = sheet.fetch_data(read_cursor)

                value_ranges = result.get('valueRanges', [])
                lines = value_ranges[0].get('values', []) if value_ranges else []

                if lines:
                    app_status["fetch_time"] = time.time()
                    for line in lines:
                        stream_manager.dispatch(iter(line))

                    # Se leu menos do que o lote, recua o cursor para a posição da última linha lida
                    if len(lines) < batch_size:
                        unread = batch_size - len(lines)
                        read_cursor.revert_rows(unread)
                else:
                    # Nenhuma linha nova encontrada, recua e tenta na próxima iteração
                    read_cursor.revert_rows(batch_size)
                time.sleep(1)

        except Exception as e:
            if "429" in str(e):
                logger.warning(
                    "Cota da API excedida (429). Aguardando 15 segundos para cooldown...")
                time.sleep(15)
            else:
                logger.error("Erro crítico durante a leitura do Google Sheets: {e}")

            read_cursor.revert_rows(batch_size)

    logger.info(
        f"Monitoramento Sheets finalizado. Total: {stream_manager.count_samples}")
