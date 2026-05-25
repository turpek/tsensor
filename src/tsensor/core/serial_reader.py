from loguru import logger
from tsensor.core.serial_connection import Serial, SerialException
from tsensor.core.handlers import StreamManager, sync_time, TimestampHandler, RadarAngleHandler, RadarDistanceHandler
from tsensor.core.sheets import SheetsManager, export_header
from tsensor.core.gui_radar import RadarGUI
from tsensor.core.utils import att_latency, service_connection, sheets_export, Timer
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
        ts_mcu = TimestampHandler.convert_raw(line)

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

    try:
        while stream_manager.is_active:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            data_queue.put(line)
    except Exception as e:
        logger.error(f"Erro na thread do Radar: {e}")


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

    msg = f"Conexão serial estabelecida em {port} (Tempo Real)"
    ser = service_connection(Serial, app_status, msg, port=port, baudrate=baudrate)
    if ser is None:
        return None

    local_manager = setup_serial_manager(config)

    batch_size = config["acquisition"].get("serial_batch_size", 50)
    sync_coordinator.batch_size = batch_size
    # Sincroniza o leitor com a posição inicial de escrita da nova sessão
    sync_coordinator.sync_cursors()
    export_cursor = sync_coordinator.write_cursor

    # Gerenciador de exportação local
    sheet = SheetsManager()
    total_samples = local_manager.total_samples
    sheet.setup(row_count=total_samples + 1, col_count=len(local_manager))

    # Exportação do Cabeçalho Dinâmico
    export_header(sheet, local_manager, sheets_lock)

    synchronize_time(ser)
    logger.info(f"Iniciando coleta Serial (Modo ROWS Export: {batch_size})...")

    # Controle de exportação não-bloqueante
    export_timer = Timer()

    try:
        ser.reset_input_buffer()
        while stream_manager.is_active:
            line = ser.readline().decode("utf-8", errors="ignore").strip()

            local_manager.dispatch(line)

            # Verifica se o lote está pronto na tabela interna
            if len(local_manager.table) >= batch_size and export_timer.elapsed(1.0):

                att_latency(local_manager, app_status)
                sheets_export(
                    local_manager, sheet, export_cursor, sheets_lock, sync_coordinator
                )

                # Limpa a tabela para o próximo lote
                local_manager.table.clear()
                export_timer.reset()

    except Exception as e:
        logger.exception(f"Erro crítico na aquisição Serial: {e}")
    finally:
        ser.close()
        logger.info("Coleta Serial finalizada.")


def sheets_reading(
    stream_manager: StreamManager, timeout: float = 1.0
) -> None:
    """Realiza a leitura do Google Sheets de forma síncrona."""
    msg = "Conexão estabelecida no Google Sheets"
    sheet = service_connection(SheetsManager, app_status, msg)
    if sheet is None:
        return None
    sheet.setup()

    # Cursor de leitura coordenado
    read_cursor = sync_coordinator.read_cursor
    cols_count = len(stream_manager)

    logger.info(f"Monitoramento Sheets iniciado ({cols_count} colunas)...")

    # Verifica se os handlers de radar estão configurados
    radar_gui = None
    has_radar = stream_manager.get_handler("angle") and stream_manager.get_handler("dist")
    if has_radar:
        radar_gui = RadarGUI(width=1280, height=720)
    # Mapeamento de índices dos sensores de radar
    h_names = [name for name in stream_manager.handlers.keys()]

    def get_idx(name_list, targets):
        for t in targets:
            if t in name_list:
                return name_list.index(t)
        return -1

    angle_idx = get_idx(h_names, ["angle", "RADAR_ANGLE"])
    dist_idx = get_idx(h_names, ["dist", "RADAR_DISTANCE"])

    try:
        while stream_manager.is_active:
            try:
                # Obtém parâmetros dinâmicos do Coordenador
                batch_size, wait = sync_coordinator.get_read_params()

                if sync_coordinator.wait_for_data(timeout=5):
                    # Avança o cursor para o próximo lote
                    read_cursor.major_row(batch_size, cols_count)

                    # Busca dados diretamente
                    with sheets_lock:
                        result = sheet.fetch_data(read_cursor)

                    value_ranges = result.get('valueRanges', [])
                    lines = value_ranges[0].get('values', []) if value_ranges else []

                    if lines:
                        app_status["fetch_time"] = time.time()
                        for line in lines:
                            # O dispatch agora distribui a lista de valores
                            stream_manager.dispatch(line)

                            # Tenta atualizar o radar
                            if radar_gui and angle_idx != -1 and dist_idx != -1:
                                try:
                                    if len(line) > max(angle_idx, dist_idx):
                                        angle_val = float(line[angle_idx])
                                        dist_val = float(line[dist_idx])
                                        radar_gui.update(int(angle_val), int(dist_val))
                                except (ValueError, TypeError, IndexError):
                                    pass

                            # Inserção direta na memória da IA
                            try:
                                from tsensor.ai.dashboard import data_manager
                                data_manager.add_row(line)
                            except Exception:
                                pass

                        if len(lines) < batch_size:
                            unread = batch_size - len(lines)
                            read_cursor.revert_rows(unread)
                            # Transição para o modo de tempo real se o lote vier incompleto
                            sync_coordinator.switch_to_realtime()
                    else:
                        read_cursor.revert_rows(batch_size)
                        # Se não houver dados, também tenta transicionar (caso a planilha esteja vazia)
                        sync_coordinator.switch_to_realtime()

                    if not wait:
                        time.sleep(0.5)
                    else:
                        time.sleep(1)

            except Exception as e:
                if "429" in str(e):
                    logger.warning("Cota API excedida. Aguardando cooldown...")
                    time.sleep(15)
                else:
                    logger.error(f"Erro na leitura do Sheets: {type(e)}")
                read_cursor.revert_rows(batch_size)
    finally:
        if radar_gui:
            radar_gui.close()
