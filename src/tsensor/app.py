from flask import Flask
from tsensor.routes.home import home_route
from tsensor.routes.api import api_route


app = Flask(__name__)
app.secret_key = 'SUA_CHAVE_SECRETA'

app.register_blueprint(home_route)
app.register_blueprint(api_route)

if __name__ == '__main__':
    app.run(debug=True)
