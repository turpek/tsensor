from loguru import logger
from tsensor.core.serial_connection import Serial, SerialException
from tsensor.core.handlers import StreamManager, sync_time, TimestampHandler, RadarAngleHandler, RadarDistanceHandler
from tsensor.core.sheets import SheetsManager
from tsensor.core.gui_radar import RadarGUI
from tsensor.core.utils import Timer
from tsensor.extensions import app_status, sync_coordinator, config, setup_serial_manager, sheets_lock
from queue import Queue, Empty
import time
import threading


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
        logger.info(
            f"Tempo sincronizado! Offset: {sync_time.offset:.4f}s (baseado em {len(offsets)} amostras)")
    else:
        logger.error(
            "Falha ao sincronizar tempo: nenhum timestamp válido recebido.")


def radar_thread_loop(ser: Serial, stream_manager: StreamManager, data_queue: Queue) -> None:
    """Thread dedicada para leitura serial e atualização do Radar GUI."""
    angle_h = RadarAngleHandler()
    dist_h = RadarDistanceHandler()
    radar_gui = RadarGUI(width=1280, height=720)

    try:
        while stream_manager.is_active:
            line = ser.readline().decode("utf-8", errors="ignore").strip()

            angle_h.handle(line)
            dist_h.handle(line)
            radar_gui.update(angle_h.value, dist_h.value)

            data_queue.put(line)
    except Exception as e:
        logger.error(f"Erro na thread do Radar: {e}")
    finally:
        radar_gui.close()


def start_radar_thread(ser: Serial, stream_manager: StreamManager, data_queue: Queue) -> threading.Thread:
    """Instancia e inicia a thread do radar."""
    thread = threading.Thread(
        target=radar_thread_loop,
        args=(ser, stream_manager, data_queue),
        daemon=True
    )
    thread.start()
    return thread


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

    # Sincroniza o batch_size para o modo Tempo Real
    sync_coordinator.batch_size = batch_size

    # Gerenciador de exportação local
    sheet = SheetsManager()
    total_samples = config["acquisition"].get("total_samples", 1000)
    col_count = 1 + len(config.get('sensors', []))
    sheet.setup(row_count=total_samples + 1, col_count=col_count)
    export_cursor = sync_coordinator.write_cursor

    # Fila para comunicação entre threads
    data_queue = Queue()

    synchronize_time(ser)
    logger.info(
        f"Iniciando coleta Serial (Modo Batch Export: {batch_size})...")

    # Dispara a thread do Radar
    start_radar_thread(ser, stream_manager, data_queue)

    # Controle de exportação não-bloqueante
    export_timer = Timer()

    try:
        ser.reset_input_buffer()
        while stream_manager.is_active:
            try:
                # Consome da fila com timeout para não travar o loop de interrupção
                line = data_queue.get(timeout=0.1)
            except Empty:
                continue

            if not local_manager.validate(line):
                continue

            # Despacha APENAS para o manager local (acumulação para Sheets)
            local_manager.dispatch(line)

            # Assume que todos os handlers têm o mesmo tamanho
            first_handler = next(iter(local_manager._handlers.values()))

            if len(first_handler.data) >= batch_size and export_timer.elapsed(1.0):
                handlers = list(local_manager._handlers.values())
                actual_batch = len(first_handler.data)

                # Janela Deslizante e Sincronia centralizadas no Coordinator
                sync_coordinator.on_write_batch(
                    sheet, actual_batch, sheets_lock)

                logger.info(
                    f"Exportando lote de {actual_batch} amostras (Modo COLUMNS)...")

                # Prepara os dados: cada lista interna é uma COLUNA completa
                export_data = [list(h.data.samples) for h in handlers]

                # Calcula a latência do lote
                if export_data and export_data[0]:
                    last_mcu_ts = export_data[0][-1]
                    app_status["batch_latency"] = time.time() - last_mcu_ts

                # Avança o cursor e exporta usando COLUMNS
                with sheets_lock:
                    export_cursor.major_row(actual_batch, len(handlers))
                    sheet.export(export_data, export_cursor,
                                 major_mode='COLUMNS')

                # Limpa os buffers locais
                for h in handlers:
                    h.data.clear()

                # Marca o tempo da última exportação para o cooldown
                export_timer.reset()

                # Reset manual do contador interno do manager local
                local_manager._count = 0

    except Exception as e:
        logger.exception(f"Erro crítico na aquisição Serial: {e}")
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

    # Cursor de leitura coordenado
    read_cursor = sync_coordinator.read_cursor
    cols = len(stream_manager)

    logger.info("Iniciando monitoramento da planilha...")

    while stream_manager.is_active:
        try:
            # Obtém parâmetros dinâmicos do Coordenador
            batch_size, wait = sync_coordinator.get_read_params()

            if sync_coordinator.wait_for_data(timeout=5):
                # Avança o cursor para o próximo lote
                read_cursor.major_row(batch_size, cols)

                # Busca dados diretamente
                with sheets_lock:
                    result = sheet.fetch_data(read_cursor)

                value_ranges = result.get('valueRanges', [])
                lines = value_ranges[0].get(
                    'values', []) if value_ranges else []

                if lines:
                    app_status["fetch_time"] = time.time()
                    for line in lines:
                        if len(line) != cols:
                            print(f'A1 -> {read_cursor.to_a1()}')
                            print(f'Sensores {len(line)}: {line}')
                        stream_manager.dispatch(iter(line))

                    # Se leu menos do que o lote, recua o cursor para a posição da última linha lida
                    if len(lines) < batch_size:
                        unread = batch_size - len(lines)
                        read_cursor.revert_rows(unread)
                else:
                    # Nenhuma linha nova encontrada, recua e tenta na próxima iteração
                    read_cursor.revert_rows(batch_size)

                # Cooldown para não estourar cota no modo história sem espera
                if not wait:
                    time.sleep(0.5)
                else:
                    time.sleep(1)

        except Exception as e:
            if "429" in str(e):
                logger.warning(
                    "Cota da API excedida (429). Aguardando 15 segundos para cooldown...")
                time.sleep(15)
            else:
                logger.error(
                    f"Erro crítico durante a leitura do Google Sheets: {type(e)}")

            read_cursor.revert_rows(batch_size)

    logger.info(
        f"Monitoramento Sheets finalizado. Total: {stream_manager.count_samples}")
