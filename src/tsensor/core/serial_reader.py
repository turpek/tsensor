from loguru import logger
from tsensor.core.serial_connection import Serial, SerialException
from tsensor.core.handlers import StreamManager
from tsensor.core.sheets import SheetsManager, SpreadSheetRange
from tsensor.extensions import app_status, config, setup_serial_manager
from time import sleep


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

    logger.info(
        f"Iniciando coleta Serial (Modo Batch Export: {batch_size})...")

    try:
        while stream_manager.is_active:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Despacha APENAS para o manager local (acumulação para Sheets)
            local_manager.dispatch(line)

            # Assume que todos os handlers têm o mesmo tamanho
            first_handler = next(iter(local_manager._handlers.values()))

            if len(first_handler.data) >= batch_size:
                logger.info(f"Exportando lote de {batch_size} amostras...")

                # Prepara os dados: [ [TS, V1, V2...], [...] ]
                export_data = []
                handlers = list(local_manager._handlers.values())

                # timestamps e amostras do lote atual
                tss = handlers[0].data.timestamp
                samples_matrix = [h.data.samples for h in handlers]

                for i in range(batch_size):
                    row = [tss[i]]
                    for sensor_samples in samples_matrix:
                        row.append(sensor_samples[i])
                    export_data.append(row)

                # Avança e exporta
                export_cursor.major_row(batch_size, 1 + len(handlers))
                sheet.export(export_data, export_cursor)

                # Limpa os buffers locais
                for h in handlers:
                    h.data.clear()

                # Reset manual do contador interno do manager local para evitar acúmulo infinito
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
    cols = 1 + len(stream_manager)

    # Batch size configurável via TOML (padrão 200)
    batch_size = config["acquisition"].get("serial_batch_size", 200)

    # Tempo de segurança para não estourar a cota de 60 req/min do Google
    # Valor mínimo de 1.5s entre requisições
    safe_interval = max(1.5, timeout)

    logger.info("Iniciando monitoramento da planilha...")

    while stream_manager.is_active:
        try:
            # Avança o cursor para o próximo lote
            read_cursor.major_row(batch_size, cols)

            # Busca dados diretamente
            result = sheet.fetch_data(read_cursor)
            value_ranges = result.get('valueRanges', [])
            lines = value_ranges[0].get('values', []) if value_ranges else []

            if lines:
                for line in lines:
                    stream_manager.dispatch_sheets(line)

                # Se leu menos do que o lote, recua o cursor para a posição da última linha lida
                if len(lines) < batch_size:
                    unread = batch_size - len(lines)
                    read_cursor.revert_rows(unread)
            else:
                # Nenhuma linha nova encontrada, recua e tenta na próxima iteração
                read_cursor.revert_rows(batch_size)

        except Exception as e:
            if "429" in str(e):
                logger.warning(
                    "Cota da API excedida (429). Aguardando 15 segundos para cooldown...")
                sleep(15)
            else:
                logger.error(f"Erro durante a leitura do Sheets: {e}")
            read_cursor.revert_rows(batch_size)

        # O SLEEP SEMPRE DEVE OCORRER PARA RESPEITAR A COTA
        sleep(safe_interval)

    logger.info(
        f"Monitoramento Sheets finalizado. Total: {stream_manager.count_samples}")
