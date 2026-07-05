# app.py — точка входа, инициализация Flask и БД
import os

from flask import Flask, render_template

from models import db

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "athletes.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()

    # Редирект GET / → /athletes подключается вместе с routes/athletes.py на Этапе 2
    @app.route("/")
    def index():
        return render_template("base.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
