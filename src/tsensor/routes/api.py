from flask import Blueprint, render_template, jsonify
from tsensor.extensions import data_stream, config

api_route = Blueprint("api", __name__, url_prefix="/api")


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
