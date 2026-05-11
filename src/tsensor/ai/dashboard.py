from flask import Blueprint, render_template, request, jsonify
from .data_manager import DataManager

# Criamos o Blueprint para o módulo de IA
ai_bp = Blueprint(
    'ai',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/ai/static'
)

# Inicializamos o DataManager sem configuração fixa
# Ele será configurado via API /api/config
data_manager = DataManager()


@ai_bp.route('/dashboard')
def index():
    return render_template('ai/ai_dashboard.html', sensors=data_manager.sensors)


@ai_bp.route('/api/config', methods=['POST'])
def set_config():
    config_data = request.json
    if not config_data or 'sensors' not in config_data:
        return jsonify({"error": "Invalid config"}), 400

    data_manager.update_config(
        config_data['sensors'],
        config_data.get('max_rows', 1000)
    )
    return jsonify({"status": "config updated"}), 200


@ai_bp.route('/api/data', methods=['POST'])
def receive_data():
    row = request.json
    if not row or not isinstance(row, list):
        return jsonify({"error": "Invalid data"}), 400

    if data_manager.add_row(row):
        return jsonify({"status": "success"}), 200
    return jsonify({"error": "Process error"}), 400


@ai_bp.route('/api/stats')
def get_stats():
    return jsonify(data_manager.get_statistics())


@ai_bp.route('/api/history')
def get_history():
    return jsonify(data_manager.get_all_data())
