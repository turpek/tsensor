from flask import Blueprint, render_template, jsonify
from tsensor.extensions import data_stream

api_route = Blueprint('api', __name__, url_prefix='/api')


@api_route.route('/stats', methods=['GET'])
def get_stats():
    # Coleta snapshot do estado atual em O(1)
    stats_data = {
        "n": len(data_stream),
        "mean": data_stream.mean,
        "std": data_stream.std,
        "min": data_stream.min if str(data_stream.min) != 'inf' else 0,
        "max": data_stream.max if str(data_stream.max) != '-inf' else 0,
    }
    # Retorna HTML renderizado
    return render_template('stats_cards.html', stats=stats_data)


@api_route.route('/histogram', methods=['GET'])
def get_histogram():
    hist_dict = data_stream.histogram(decimal_label=2)

    response_data = {
        "labels": list(hist_dict.keys()),
        "values": list(hist_dict.values())
    }

    # Retorna JSON
    return jsonify(response_data)
