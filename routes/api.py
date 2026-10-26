# routes/api.py — поиск спортсменов для COREZ (предварительные заявки на
# соревнования, routes/заявка.py там же). Формат выдачи специально сделан
# идентичным локальному поиску COREZ по спортсменам прошлых соревнований
# (routes/спортсмены.py /поиск) — ключи фио, дата_рождения, пол, разряд,
# номер_в_базе — чтобы его JS не пришлось переписывать. Защищено заголовком
# X-API-Key (значение — в .env, API_KEY).
import os
from functools import wraps

from flask import Blueprint, jsonify, request

from models import Athlete, db

bp = Blueprint("api", __name__, url_prefix="/api")

# REGTEAM_RAFTING хранит пол и разряд полным написанием (references.py:
# GENDERS, RANKS), COREZ — короткими кодами ('м'/'ж', 'Iю'/'IIю'/'IIIю').
_GENDER_TO_SHORT = {"Мужской": "м", "Женский": "ж"}
_RANK_TO_COREZ = {"I юн": "Iю", "II юн": "IIю", "III юн": "IIIю"}


def require_api_key(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected_key = os.environ.get("API_KEY")
        provided_key = request.headers.get("X-API-Key")

        if not expected_key:
            return jsonify({"error": "API-ключ не настроен на сервере."}), 500
        if not provided_key or provided_key != expected_key:
            return jsonify({"error": "Неверный или отсутствующий X-API-Key."}), 401

        return view(*args, **kwargs)
    return wrapped


def _athlete_to_corez_dict(athlete):
    return {
        "фио": athlete.full_name,
        "дата_рождения": athlete.birth_date.isoformat() if athlete.birth_date else "",
        "пол": _GENDER_TO_SHORT.get(athlete.gender, ""),
        "разряд": _RANK_TO_COREZ.get(athlete.rank, athlete.rank) or "",
        "номер_в_базе": athlete.id,
    }


@bp.route("/athletes/search", methods=["GET"])
@require_api_key
def athletes_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])

    athletes = (
        Athlete.query.filter(db.or_(
            Athlete.last_name.ilike(f"%{q}%"),
            Athlete.first_name.ilike(f"%{q}%"),
            Athlete.middle_name.ilike(f"%{q}%"),
        ))
        .order_by(Athlete.last_name)
        .limit(50)
        .all()
    )
    return jsonify([_athlete_to_corez_dict(a) for a in athletes])
