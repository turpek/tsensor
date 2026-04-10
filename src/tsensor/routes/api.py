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
    # Usa os valores dinâmicos do TOML
    res_adc = config["sensor"]["v_ref"] / config["sensor"]["adc_max"]
    decimals = config["presentation"]["decimal_places"]

    hist_dict = data_stream.histogram(res_adc, decimal_label=decimals)

    response_data = {
        "labels": list(hist_dict.keys()),
        "values": list(hist_dict.values()),
    }

    return jsonify(response_data)
