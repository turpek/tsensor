from flask import Blueprint, render_template, jsonify, request
from tsensor.extensions import data_stream, buffer_stream, config, app_status
from tsensor.core.utils import save_config, MCU_PRESETS
from tsensor.core.acquisition import start_acquisition, stop_acquisition
from tsensor.core.exporters import CSVExporter

api_route = Blueprint("api", __name__, url_prefix="/api")


@api_route.route("/export", methods=["POST"])
def export_data():
    """Exporta os dados atuais para um arquivo CSV local."""
    try:
        # Usa a pasta de exportação do sistema ou uma pasta 'exports' por padrão
        export_dir = "exports"

        exporter = CSVExporter(
            directory=export_dir,
            header=["timestamp", "temperatura"]
        )

        # Garante que a pasta existe
        exporter.setup()

        # Obtém os dados atuais do stream
        data = data_stream.sample

        if not data:
            return jsonify({"error": "Não há dados para exportar."}), 400

        # Realiza a exportação (usa um nome baseado no timestamp)
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
    old_mcu = config["hardware"]["mcu"]
    new_mcu = data.get("mcu", config["hardware"]["mcu"])
    config["hardware"]["port"] = data.get("port", config["hardware"]["port"])
    config["hardware"]["mcu"] = new_mcu
    config["hardware"]["baudrate"] = int(
        data.get("baudrate", config["hardware"]["baudrate"])
    )

    # Se o MCU mudou, aplica presets automáticos se não houver sobrescrita no payload
    if new_mcu != old_mcu and new_mcu in MCU_PRESETS:
        preset = MCU_PRESETS[new_mcu]
        config["sensor"]["v_ref"] = float(data.get("v_ref", preset["v_ref"]))
        config["sensor"]["adc_max"] = int(
            data.get("adc_max", preset["adc_max"]),
        )
    else:
        # Mantém lógica atual para quando o MCU não muda
        config["sensor"]["v_ref"] = float(
            data.get("v_ref", config["sensor"]["v_ref"]),
        )
        config["sensor"]["adc_max"] = int(
            data.get("adc_max", config["sensor"]["adc_max"]),
        )

    # Atualiza configurações de aquisição e apresentação
    config["acquisition"]["total_samples"] = int(
        data.get("total_samples", config["acquisition"]["total_samples"])
    )
    config["presentation"]["update_interval_ms"] = int(
        data.get(
            "update_interval_ms",
            config["presentation"]["update_interval_ms"],
        )
    )
    config["presentation"]["decimal_places"] = int(
        data.get("decimal_places", config["presentation"]["decimal_places"])
    )

    try:
        save_config(config)

        # Atualiza status visual
        app_status["port"] = config["hardware"]["port"]
        app_status["mcu"] = config["hardware"]["mcu"]

        # SÓ inicia a aquisição se NÃO estiver conectado
        # Se já estiver conectado, apenas salvamos para o próximo boot/restart manual
        if not app_status.get("connected"):
            start_acquisition()

        return jsonify({"success": True, "message": "Configurações salvas."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_route.route("/restart", methods=["POST"])
def restart_acquisition_route():
    """Rota específica para reinicializar manualmente o hardware."""
    try:
        stop_acquisition()
        data_stream.clear()
        buffer_stream.clear()
        start_acquisition()
        return jsonify({"success": True, "message": "Hardware reiniciado."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_route.route("/stats", methods=["GET"])
def get_stats():
    stats_data = {
        "n": len(data_stream),
        "mean": data_stream.mean,
        "std": data_stream.std,
        "min": data_stream.min if str(data_stream.min) != "inf" else 0,
        "max": data_stream.max if str(data_stream.max) != "-inf" else 0,
    }
    return render_template("stats_cards.html", stats=stats_data)


@api_route.route("/histogram", methods=["GET"])
def get_histogram():
    # Calcula a resolução térmica: (V_ref / ADC_max) * 100
    # O fator 100 vem da sensibilidade do LM35 (10mV/ºC -> 1V = 100ºC)
    v_ref = config["sensor"]["v_ref"]
    adc_max = config["sensor"]["adc_max"]
    res_c = (v_ref / adc_max) * 100

    decimals = config["presentation"]["decimal_places"]

    hist_dict = data_stream.histogram(res_c, decimal_label=decimals)

    response_data = {
        "labels": list(hist_dict.keys()),
        "values": list(hist_dict.values()),
    }

    return jsonify(response_data)
