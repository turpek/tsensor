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

    # NOVO: Gerenciador Serial focado em tabelas assíncronas
    from tsensor.core.handlers import SerialManager
    local_manager = SerialManager()

    # Re-configura o local_manager com base no config
    local_manager.configure(
        timeout=config["acquisition"].get("max_runtime_sec"))

    # Adiciona os handlers ao local_manager (mesma lógica do setup_serial_manager)
    # mas focada no novo manager que gerencia a 'table'
    temp_manager = setup_serial_manager(config)
    for name, handler in temp_manager._handlers.items():
        local_manager.add_handler(name, handler)

    batch_size = config["acquisition"].get("serial_batch_size", 50)
    sync_coordinator.batch_size = batch_size

    # Gerenciador de exportação local
    sheet = SheetsManager()
    total_samples = config["acquisition"].get("total_samples", 1000)
    col_count = 1 + len(config.get('sensors', []))
    sheet.setup(row_count=total_samples + 1, col_count=col_count)
    export_cursor = sync_coordinator.write_cursor

    # Exportação do Cabeçalho Dinâmico
    from tsensor.core.sheets import SpreadSheetRange
    header = ["timestamp[tempo]"]
    for s in config.get('sensors', []):
        header.append(f"{s.get('type', 'sensor')}[{s.get('name', 's')}]")

    with sheets_lock:
        header_cursor = SpreadSheetRange(row=1, col=1)
        header_cursor.major_row(1, len(header))
        sheet.export([header], header_cursor)

    # Fila para comunicação entre threads
    data_queue = Queue()

    synchronize_time(ser)
    logger.info(f"Iniciando coleta Serial (Modo ROWS Export: {batch_size})...")

    # Dispara a thread do Radar
    start_radar_thread(ser, stream_manager, data_queue)

    # Controle de exportação não-bloqueante
    export_timer = Timer()

    try:
        ser.reset_input_buffer()
        while stream_manager.is_active:
            try:
                line = data_queue.get(timeout=0.1)
            except Empty:
                continue

            # Despacha para o manager local que monta a tabela
            local_manager.dispatch(line)

            # Verifica se o lote está pronto na tabela interna
            if len(local_manager.table) >= batch_size and export_timer.elapsed(1.0):
                actual_batch = len(local_manager.table)
                num_handlers = len(local_manager)

                # Janela Deslizante
                sync_coordinator.on_write_batch(
                    sheet, actual_batch, sheets_lock)

                logger.info(
                    f"Exportando {actual_batch} linhas para o Sheets...")

                # Calcula latência (baseada no último timestamp da tabela)
                if actual_batch > 0:
                    last_row = local_manager.table[-1]
                    if isinstance(last_row[0], (int, float)):
                        app_status["batch_latency"] = time.time() - last_row[0]

                # Exporta usando ROWS (mais robusto para frequências variadas)
                with sheets_lock:
                    export_cursor.major_row(actual_batch, num_handlers)
                    sheet.export(local_manager.table,
                                 export_cursor, major_mode='ROWS')

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
    cols_count = len(stream_manager)

    logger.info(f"Monitoramento Sheets iniciado ({cols_count} colunas)...")

    # Verifica se os handlers de radar estão configurados
    radar_gui = None
    has_radar = stream_manager.get_handler("angle") and stream_manager.get_handler("dist")
    if has_radar:
        try:
            radar_gui = RadarGUI(width=1280, height=720)
            logger.info("RadarGUI iniciado via Google Sheets.")
        except Exception as e:
            logger.warning(f"Não foi possível iniciar o RadarGUI: {e}")

    # Mapeamento de índices dos sensores de radar
    h_names = [name for name in stream_manager._handlers.keys()] if hasattr(stream_manager, "_handlers") else []
    
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
                    else:
                        read_cursor.revert_rows(batch_size)

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

