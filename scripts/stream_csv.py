from tsensor.core.data_stream import DataStream
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import sys
import os
import time

# Adiciona o diretório src ao path para importar tsensor
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../src')))


def run_stream():
    csv_path = 'exports/sessao_20260411_174838.csv'
    if not os.path.exists(csv_path):
        print(f"Erro: Arquivo {csv_path} não encontrado.")
        return

    # Lê o CSV completo
    df = pd.read_csv(csv_path)
    total_len = len(df)

    # Usa um DataStream temporário para calcular os limites globais de Y
    limit_stream = DataStream(total_samples=total_len)
    for val in df['temperatura']:
        limit_stream.add(val, "")

    # Stream real que será usado para a média móvel de 1000 pontos
    stream = DataStream(total_samples=1000)

    fig, ax = plt.subplots(figsize=(10, 6))

    # --- CONFIGURAÇÃO INICIAL COM TAMANHO FINAL ---
    # X: range total de amostras do arquivo
    ax.set_xlim(0, total_len)

    # Y: min/max globais detectados pelo DataStream
    ax.set_ylim(limit_stream.min - 0.5, limit_stream.max + 0.5)

    line_real, = ax.plot([], [], label='Dados Reais (T)',
                         color='blue', alpha=0.3, animated=True)
    line_ma, = ax.plot([], [], label='Média Móvel (1000 pts)',
                       color='red', linewidth=2, animated=True)

    ax.set_title('Stream Otimizado: Eixos Fixos (Tamanho Final do CSV)')
    ax.set_xlabel('Amostras')
    ax.set_ylabel('Temperatura (°C)')
    ax.legend(loc='upper left')
    ax.grid(True)

    data_gen = df.iterrows()
    x_data, y_real, y_ma = [], [], []
    count = 0

    def update(frame):
        nonlocal count
        points_per_update = 5000  # Aumentado para 5000 pts/seg para visualização rápida

        # --- FASE 1: CÁLCULO ---
        start_proc = time.perf_counter()
        new_points = 0
        for _ in range(points_per_update):
            try:
                _, row = next(data_gen)
                stream.add(row['temperatura'], row['timestamp'])

                count += 1
                x_data.append(count)
                y_real.append(row['temperatura'])
                y_ma.append(stream.moving_average)
                new_points += 1
            except StopIteration:
                break
        end_proc = time.perf_counter()

        # --- FASE 2: RENDERIZAÇÃO ---
        start_render = time.perf_counter()
        if new_points > 0:
            line_real.set_data(x_data, y_real)
            line_ma.set_data(x_data, y_ma)
            # Os eixos permanecem fixos, garantindo Blitting puro (sem redesenho de fundo)
        end_render = time.perf_counter()

        if new_points > 0:
            t_proc = (end_proc - start_proc) * 1000
            t_render = (end_render - start_render) * 1000
            print(
                f"[{count:06d}] Cálculo: {t_proc:6.2f}ms | Render: {t_render:6.2f}ms | Total: {t_proc+t_render:6.2f}ms")

        return line_real, line_ma

    # Blitting ativo e eficiente (intervalo de 1 segundo)
    ani = FuncAnimation(fig, update, interval=1000,
                        blit=True, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    run_stream()
