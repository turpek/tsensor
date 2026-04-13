from flask import Blueprint, render_template
from tsensor.extensions import config
from tsensor.core.utils import get_sensor_models

home_route = Blueprint("home", __name__)


@home_route.route("/")
def home():
    return render_template(
        "index.html",
        config=config,
        sensor_categories=get_sensor_models()
    )
