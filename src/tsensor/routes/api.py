import numpy as np
from flask import Blueprint, render_template, jsonify, request
from tsensor.extensions import manager, config, app_status
from tsensor.core.utils import save_config, detrend, Stat, numpy_histogram
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

    hist_dict = numpy_histogram(res_array, decimals=6)

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
    """Exporta os dados atuais para um arquivo CSV local."""
    handler = _get_main_handler()
    if not handler:
        return jsonify({"error": "Nenhum sensor configurado."}), 400

    try:
        export_dir = "exports"
        exporter = CSVExporter(
            directory=export_dir,
            header=["timestamp", "temperatura"]
        )
        exporter.setup()

        data = handler.data.sample
        if not data:
            return jsonify({"error": "Não há dados para exportar."}), 400

        from datetime import datetime
        file_name = f"sessao_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        success = exporter.export(data, file_name)

        if success:
            return jsonify({"success": True, "message": f"Dados salvos em {export_dir}/{file_name}.csv"})
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
        data = np.array(ds.data)
        hist_dict = numpy_histogram(data, decimals=4)

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
