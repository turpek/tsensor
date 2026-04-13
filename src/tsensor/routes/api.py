from scipy.interpolate import make_interp_spline
import matplotlib.pyplot as plt
import matplotlib
from datetime import datetime
import zipfile
import io
import numpy as np
from flask import Blueprint, render_template, jsonify, request
from tsensor.extensions import manager, config, app_status
from tsensor.core.utils import save_config, detrend, Stat, hybrid_histogram
from tsensor.core.acquisition import start_acquisition, stop_acquisition
from tsensor.core.exporters import CSVExporter

api_route = Blueprint("api", __name__, url_prefix="/api")


def _get_main_handler():
    """Retorna o primeiro handler configurado ou levanta erro."""
    if not manager or len(manager) == 0:
        return None
    # Pega o primeiro sensor da lista de configuração
    name = config["sensors"][0]["name"]
    return manager.get_handler(name)


@api_route.route("/residual-analysis", methods=["GET"])
def get_residual_analysis():
    """Realiza a análise residual das amostras atuais e retorna o histograma via NumPy."""
    sensor_name = request.args.get("sensor")

    if sensor_name:
        handler = manager.get_handler(sensor_name)
    else:
        handler = _get_main_handler()

    if not handler:
        return jsonify({"error": "Sensor não encontrado ou não configurado."}), 400

    temps = handler.data.data
    if not temps:
        return jsonify({"error": "Não há dados para análise."}), 400

    # Extrai apenas as temperaturas e aplica detrend
    residuals = detrend(temps)
    res_array = np.array(residuals)

    # Usa a classe Stat com inicialização atômica para estatísticas básicas
    stat = Stat(total_samples=len(res_array), initial_data=res_array)

    hist_dict = hybrid_histogram(
        res_array, stat.amplitude, stat.mean, resolucao_adc=0.01, decimal_label=6
    )

    return jsonify({
        "labels": list(hist_dict.keys()),
        "values": list(hist_dict.values()),
        "stats": {
            "mean": stat.mean,
            "std": stat.std,
            "n": len(stat)
        }
    })


@api_route.route("/export", methods=["POST"])
def export_data():
    """Exporta os dados de todos os sensores em colunas paralelas (Wide Format)."""
    if not manager or len(manager) == 0:
        return jsonify({"error": "Nenhum sensor configurado."}), 400

    try:
        export_dir = "exports"

        # Coleta dados por sensor e identifica o tamanho máximo
        sensor_data = {}
        max_len = 0
        sensor_names = list(manager._handlers.keys())

        for name in sensor_names:
            samples = manager._handlers[name].data.sample
            sensor_data[name] = samples
            if len(samples) > max_len:
                max_len = len(samples)

        if max_len == 0:
            return jsonify({"error": "Não há dados para exportar."}), 400

        # Constrói o cabeçalho dinâmico e a linha de comentário para identificação
        header = []
        comment_parts = []
        for name in sensor_names:
            # Pega o tipo para o cabeçalho (ex: temperature, pressure)
            sensor_config = next(
                (s for s in config["sensors"] if s["name"] == name), {})
            s_type = sensor_config.get("type", "valor")

            header.extend(["timestamp", s_type])
            # Espaçamento para as duas colunas
            comment_parts.append(f"{name}; ")

        comment_line = "; ".join(comment_parts)

        # Prepara as linhas alinhando as amostras
        rows = []
        for i in range(max_len):
            row = []
            for name in sensor_names:
                samples = sensor_data[name]
                if i < len(samples):
                    row.extend([samples[i][0], samples[i][1]])
                else:
                    # Padding para sensores com menos amostras
                    row.extend(["", ""])
            rows.append(row)

        exporter = CSVExporter(directory=export_dir, header=header)
        exporter.setup()

        from datetime import datetime
        file_name = f"sessao_paralela_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Exporta com separador ';' e linha de comentário
        success = exporter.export(
            rows, file_name, sep=";", comment=comment_line)

        if success:
            n = len(sensor_names)
            sensor_str = "sensor" if n == 1 else "sensores"
            msg = f"Dados de {n} {sensor_str} exportados lado a lado em {export_dir}/{file_name}.csv"
            return jsonify({"success": True, "message": msg})
        else:
            return jsonify({"error": "Falha ao salvar arquivo CSV."}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_route.route("/status", methods=["GET"])
def get_status():
    """Retorna o estado da conexão e configurações atuais."""
    return jsonify(app_status)


@api_route.route("/config", methods=["POST"])
def update_config():
    """Recebe novas configurações do frontend e salva no TOML."""
    data = request.json
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    # Atualiza configurações de hardware
    config["hardware"]["port"] = data.get("port", config["hardware"]["port"])
    config["hardware"]["mcu"] = data.get("mcu", config["hardware"]["mcu"])
    config["hardware"]["baudrate"] = int(
        data.get("baudrate", config["hardware"]["baudrate"])
    )

    # Se sensors vier no payload, sobrescreve a lista completa
    if "sensors" in data:
        if not data["sensors"] or len(data["sensors"]) == 0:
            return jsonify({"error": "A configuração deve conter pelo menos um sensor."}), 400
        config["sensors"] = data["sensors"]

    # Atualiza configurações de aquisição
    if data.get("enable_limit_samples") in ["on", True]:
        config["acquisition"]["total_samples"] = int(
            data.get("total_samples", 1000000))
    else:
        config["acquisition"].pop("total_samples", None)

    if data.get("enable_limit_time") in ["on", True]:
        config["acquisition"]["max_runtime_sec"] = int(
            data.get("max_runtime_sec", 1800))
    else:
        config["acquisition"].pop("max_runtime_sec", None)

    config["presentation"]["update_interval_ms"] = int(
        data.get("update_interval_ms",
                 config["presentation"]["update_interval_ms"])
    )
    config["presentation"]["decimal_places"] = int(
        data.get("decimal_places", config["presentation"]["decimal_places"])
    )

    config["presentation"]["debug_mode"] = data.get("debug_mode") in [
        "on", True]
    config["presentation"]["log_level"] = data.get(
        "log_level", config["presentation"]["log_level"])

    try:
        save_config(config)

        # Atualiza status visual
        app_status["port"] = config["hardware"]["port"]
        app_status["mcu"] = config["hardware"]["mcu"]

        if not app_status.get("connected"):
            start_acquisition()

        return jsonify({"success": True, "message": "Configurações salvas."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_route.route("/stop", methods=["POST"])
def stop_acquisition_route():
    """Interrompe a aquisição de dados manualmente."""
    try:
        stop_acquisition()
        return jsonify({"success": True, "message": "Aquisição interrompida."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_route.route("/restart", methods=["POST"])
def restart_acquisition_route():
    """Rota específica para reinicializar manualmente o hardware."""
    try:
        stop_acquisition()
        start_acquisition()
        return jsonify({"success": True, "message": "Hardware reiniciado."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_route.route("/stats", methods=["GET"])
def get_stats():
    all_stats = {}
    for name, handler in manager._handlers.items():
        ds = handler.data

        # Busca o tipo do sensor no config
        sensor_config = next(
            (s for s in config["sensors"] if s["name"] == name), {})
        sensor_type = sensor_config.get("type", "Sensor")

        all_stats[name] = {
            "type": sensor_type,
            "n": len(ds),
            "mean": ds.mean,
            "std": ds.std,
            "min": ds.min if ds.min != float("inf") else 0,
            "max": ds.max if ds.max != -float("inf") else 0,
        }
    return render_template("stats_cards.html", all_stats=all_stats)


@api_route.route("/histogram", methods=["GET"])
def get_histogram():
    all_histograms = {}

    for name, handler in manager._handlers.items():
        buffer = handler.data_buffer

        # Só move para o histórico (time_series) se o buffer atingiu o limite configurado (is_full)
        if buffer.is_full:
            # Extrai o timestamp da última amostra do buffer
            last_ts = buffer.sample[-1][0] if buffer.sample else None
            # Adiciona a média do bloco ao histórico temporal
            handler.time_series.add(buffer.mean, timestamp=last_ts)
            # Limpa o buffer para o próximo bloco
            buffer.clear()

        ds = handler.data
        hist_dict = ds.histogram(resolucao_adc=0.01, decimal_label=4)

        all_histograms[name] = {
            "labels": [s[0] for s in handler.time_series.sample],
            "values": [s[1] for s in handler.time_series.sample],
            "histogram": {
                "labels": list(hist_dict.keys()),
                "values": list(hist_dict.values()),
            },
            "stats": {
                "n": len(ds),
                "mean": ds.mean,
                "std": ds.std,
                "min": ds.min if ds.min != float("inf") else 0,
                "max": ds.max if ds.max != -float("inf") else 0,
            }
        }

    return jsonify(all_histograms)


matplotlib.use("Agg")  # Backend não interativo para web


@api_route.route("/download-charts-zip", methods=["GET"])
def download_charts_zip():
    """Gera todos os gráficos no backend usando Matplotlib e retorna um ZIP com unidades e suavização."""
    if not manager or len(manager) == 0:
        return jsonify({"error": "Nenhum sensor configurado."}), 400

    # Mapeamento de unidades
    units = {"temperature": "°C", "pressure": "kPa"}

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for name, handler in manager._handlers.items():
            safe_name = name.replace(" ", "_")

            # Busca o tipo do sensor no config para determinar a unidade
            sensor_config = next(
                (s for s in config["sensors"] if s["name"] == name), {})
            s_type = sensor_config.get("type", "sensor")
            unit = units.get(s_type, "")

            # 1. Gráfico de Série Temporal (Suavizado com Spline)
            data_points = handler.time_series.sample
            if data_points:
                labels = [p[0] for p in data_points]
                values = np.array([p[1] for p in data_points])
                indices = np.arange(len(values))

                plt.figure(figsize=(10, 6), dpi=100)

                # Se houver pontos suficientes (mín 4 para cubic spline), suavizamos a linha
                if len(values) >= 4:
                    indices_new = np.linspace(
                        indices.min(), indices.max(), 300)
                    spline = make_interp_spline(indices, values, k=3)
                    values_smooth = spline(indices_new)

                    # Desenha a linha suave e os pontos reais (como marcadores discretos)
                    plt.plot(indices_new, values_smooth, color="#6366f1",
                             linewidth=2.5, alpha=0.8, label="Tendência")
                    plt.scatter(indices, values, color="#4f46e5",
                                s=25, zorder=5, label="Amostras")
                else:
                    # Fallback para linha simples com marcadores
                    plt.plot(indices, values, color="#6366f1",
                             linewidth=2, marker="o", markersize=6)

                plt.title(f"Série Temporal: {name}",
                          fontsize=14, fontweight="bold")
                plt.xlabel("Tempo", fontsize=10)
                plt.ylabel(f"Valor ({unit})" if unit else "Valor", fontsize=10)

                # Ajusta os ticks do eixo X (tempo) para não encavalar
                step = max(1, len(labels) // 10)
                plt.xticks(indices[::step], [labels[i] for i in range(
                    0, len(labels), step)], rotation=45, fontsize=8)

                plt.grid(True, linestyle="--", alpha=0.5)
                plt.tight_layout()

                img_io = io.BytesIO()
                plt.savefig(img_io, format="png", facecolor="white")
                plt.close()
                zf.writestr(
                    f"serie_temporal_{safe_name}_{timestamp}.png", img_io.getvalue())

            # 2. Histograma Global
            data_raw = np.array(handler.data.data)
            if len(data_raw) > 0:
                plt.figure(figsize=(10, 6), dpi=100)
                plt.hist(data_raw, bins="auto", color="#3b82f6",
                         alpha=0.7, edgecolor="white")
                plt.title(
                    f"Distribuição de Dados: {name}", fontsize=14, fontweight="bold")
                plt.xlabel(f"Valor ({unit})" if unit else "Valor", fontsize=10)
                plt.ylabel("Frequência", fontsize=10)
                plt.grid(axis="y", linestyle="--", alpha=0.7)
                plt.tight_layout()

                img_io = io.BytesIO()
                plt.savefig(img_io, format="png", facecolor="white")
                plt.close()
                zf.writestr(
                    f"histograma_{safe_name}_{timestamp}.png", img_io.getvalue())

            # 3. Gráfico de Resíduos (Detrended)
            if len(data_raw) > 1:
                residuals = detrend(handler.data.data)
                plt.figure(figsize=(10, 6), dpi=100)
                plt.hist(residuals, bins="auto", color="#818cf8",
                         alpha=0.7, edgecolor="white")
                plt.title(
                    f"Análise Residual (Ruído): {name}", fontsize=14, fontweight="bold")
                plt.xlabel(
                    f"Desvio ({unit})" if unit else "Desvio", fontsize=10)
                plt.ylabel("Frequência", fontsize=10)
                plt.grid(axis="y", linestyle="--", alpha=0.7)
                plt.tight_layout()

                img_io = io.BytesIO()
                plt.savefig(img_io, format="png", facecolor="white")
                plt.close()
                zf.writestr(
                    f"residuos_{safe_name}_{timestamp}.png", img_io.getvalue())

    zip_buffer.seek(0)
    from flask import send_file
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"tsensor_charts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    )
