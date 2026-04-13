import numpy as np
from flask import Blueprint, render_template, jsonify, request
from tsensor.extensions import manager, config, app_status
from tsensor.core.utils import save_config, MCU_PRESETS, detrend, Stat, histogram
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
    """Realiza a análise residual das amostras atuais e retorna o histograma."""
    handler = _get_main_handler()
    if not handler:
        return jsonify({"error": "Nenhum sensor configurado."}), 400

    temps = handler.data.data
    if not temps:
        return jsonify({"error": "Não há dados para análise."}), 400

    # Extrai apenas as temperaturas e aplica detrend
    residuals = detrend(temps)
    res_array = np.array(residuals)

    # Usa a classe Stat com inicialização atômica
    stat = Stat(total_samples=len(res_array), initial_data=res_array)

    # Calibração do primeiro sensor
    cal = config["sensors"][0]["calibration"]
    v_ref = cal["v_ref"]
    adc_max = cal["adc_max"]
    res_c = (v_ref / adc_max) * 100

    decimals = config["presentation"]["decimal_places"] + 1

    hist_dict = histogram(
        res_array,
        stat.amplitude,
        stat.moving_average,
        resolucao_adc=res_c,
        decimal_label=decimals,
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
    handler = _get_main_handler()
    if not handler:
        return render_template("stats_cards.html", stats={})

    ds = handler.data
    stats_data = {
        "n": len(ds),
        "mean": ds.mean,
        "std": ds.std,
        "min": ds.min if ds.min != float("inf") else 0,
        "max": ds.max if ds.max != -float("inf") else 0,
    }
    return render_template("stats_cards.html", stats=stats_data)


@api_route.route("/histogram", methods=["GET"])
def get_histogram():
    handler = _get_main_handler()
    if not handler:
        return jsonify({"labels": [], "values": []})

    cal = config["sensors"][0]["calibration"]
    v_ref = cal["v_ref"]
    adc_max = cal["adc_max"]
    res_c = (v_ref / adc_max) * 100

    decimals = config["presentation"]["decimal_places"]

    hist_dict = handler.data.histogram(res_c, decimal_label=decimals)

    return jsonify({
        "labels": list(hist_dict.keys()),
        "values": list(hist_dict.values()),
    })
