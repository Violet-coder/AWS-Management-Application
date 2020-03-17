from flask import Flask

webapp = Flask(__name__)
webapp.config["SECRET_KEY"] = '1779'

from app.Services import Manager_app

from app import main