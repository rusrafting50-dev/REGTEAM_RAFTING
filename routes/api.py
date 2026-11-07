# routes/api.py — поиск спортсменов для COREZ (предварительные заявки на
# соревнования, routes/заявка.py там же). Формат выдачи специально сделан
# идентичным локальному поиску COREZ по спортсменам прошлых соревнований
# (routes/спортсмены.py /поиск) — ключи фио, дата_рождения, пол, разряд,
# номер_в_базе — чтобы его JS не пришлось переписывать. Защищено заголовком
# X-API-Key (значение — в .env, API_KEY).
import os
from datetime import date
from functools import wraps

from flask import Blueprint, jsonify, request

from models import Athlete, CompetitionParticipation, db

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


@bp.route("/competition/import", methods=["POST"])
@require_api_key
def competition_import():
    """Принимает список участников из предварительной заявки COREZ
    и записывает CompetitionParticipation для найденных в базе спортсменов.

    Тело запроса (JSON):
      competition_name  — название соревнования
      competition_date  — дата в ISO-формате (опционально, иначе null)
      athletes          — [{last_name, first_name, middle_name,
                            birth_date (ISO), gender, rank}, …]

    Ответ: {matched, unmatched, participations_created}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Ожидается JSON."}), 400

    competition_name = (data.get("competition_name") or "").strip()
    competition_date_str = (data.get("competition_date") or "").strip()
    athletes_data = data.get("athletes") or []

    try:
        competition_date = date.fromisoformat(competition_date_str) if competition_date_str else None
    except ValueError:
        competition_date = None

    matched = 0
    unmatched = 0
    participations_created = 0

    for a in athletes_data:
        last_name  = (a.get("last_name")  or "").strip()
        first_name = (a.get("first_name") or "").strip()
        birth_date_str = (a.get("birth_date") or "").strip()

        if not last_name and not first_name:
            continue

        try:
            birth_date = date.fromisoformat(birth_date_str) if birth_date_str else None
        except ValueError:
            birth_date = None

        q = Athlete.query.filter(
            Athlete.last_name.ilike(last_name),
            Athlete.first_name.ilike(first_name),
        )
        if birth_date:
            q = q.filter(Athlete.birth_date == birth_date)
        athlete = q.first()

        if athlete:
            matched += 1
            exists = CompetitionParticipation.query.filter_by(
                athlete_id=athlete.id,
                competition_name=competition_name,
            ).first()
            if not exists:
                p = CompetitionParticipation(
                    athlete_id=athlete.id,
                    competition_name=competition_name,
                    date=competition_date,
                )
                db.session.add(p)
                participations_created += 1
        else:
            unmatched += 1

    db.session.commit()
    return jsonify({
        "matched": matched,
        "unmatched": unmatched,
        "participations_created": participations_created,
    })


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
