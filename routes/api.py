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

from models import Athlete, CompetitionParticipation, Subject, db
from subjects import текущий_субъект_id

bp = Blueprint("api", __name__, url_prefix="/api")

# REGTEAM_RAFTING хранит пол и разряд полным написанием (references.py:
# GENDERS, RANKS), COREZ — короткими кодами ('м'/'ж', 'Iю'/'IIю'/'IIIю').
_GENDER_TO_SHORT = {"Мужской": "м", "Женский": "ж"}
_RANK_TO_COREZ = {"I юн": "Iю", "II юн": "IIю", "III юн": "IIIю"}
_GENDER_FROM_COREZ = {"м": "Мужской", "ж": "Женский"}
_RANK_FROM_COREZ = {"Iю": "I юн", "IIю": "II юн", "IIIю": "III юн"}


def _get_or_create_subject(name):
    name = (name or "Московская область").strip()
    s = Subject.query.filter_by(name=name).first()
    if not s:
        s = Subject(name=name)
        db.session.add(s)
        db.session.flush()
    return s


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
    """Принимает список участников из предварительной заявки COREZ.
    Найденным в базе спортсменам добавляет CompetitionParticipation;
    не найденным — создаёт новую запись Athlete (is_active=False).

    Тело запроса (JSON):
      competition_name  — название соревнования
      competition_date  — дата в ISO-формате (опционально, иначе null)
      athletes          — [{last_name, first_name, middle_name,
                            birth_date (ISO), gender, rank, subject}, …]

    Ответ: {matched, created, participations_created}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Ожидается JSON."}), 400

    competition_name = (data.get("competition_name") or "").strip()
    competition_date_str = (data.get("competition_date") or "").strip()
    period_place = (data.get("competition_period_place") or "").strip() or None
    corez_id = _int_or_none(data.get("competition_id"))
    athletes_data = data.get("athletes") or []

    try:
        competition_date = date.fromisoformat(competition_date_str) if competition_date_str else None
    except ValueError:
        competition_date = None

    matched = 0
    created = 0
    participations_created = 0
    conflicts = 0
    home_subject_id = текущий_субъект_id()

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

        if not athlete:
            subject = _get_or_create_subject(a.get("subject") or "")
            gender_raw = (a.get("gender") or "").strip()
            rank_raw   = (a.get("rank")   or "").strip()
            athlete = Athlete(
                last_name        = last_name,
                first_name       = first_name,
                middle_name      = (a.get("middle_name") or "").strip(),
                birth_date       = birth_date,
                gender           = _GENDER_FROM_COREZ.get(gender_raw, gender_raw),
                rank             = _RANK_FROM_COREZ.get(rank_raw, rank_raw),
                subject_id       = subject.id,
                is_active        = False,
                is_imported      = True,
                imported_pending = True,
            )
            db.session.add(athlete)
            db.session.flush()
            created += 1
        else:
            matched += 1
            if not athlete.imported_pending:
                needs_requeue = (
                    bool(athlete.is_imported)                     # создан предыдущим COREZ-импортом
                    or not athlete.in_list                        # не числится ни в одном списке
                    or athlete.subject_id != home_subject_id      # числится в другом регионе
                )
                if needs_requeue:
                    athlete.imported_pending = True
                    # in_list НЕ сбрасываем: спортсмен может быть активным членом
                    # другой региональной сборной — исключать его решает пользователь
                    if not athlete.in_list:
                        athlete.is_imported = True
                    if athlete.subject_id != home_subject_id and athlete.in_list:
                        conflicts += 1

        exists = CompetitionParticipation.query.filter_by(
            athlete_id=athlete.id,
            competition_name=competition_name,
        ).first()
        if not exists:
            db.session.add(CompetitionParticipation(
                athlete_id=athlete.id,
                competition_name=competition_name,
                date=competition_date,
                period_place=period_place,
                corez_competition_id=corez_id,
            ))
            participations_created += 1

    db.session.commit()
    return jsonify({
        "matched": matched,
        "created": created,
        "participations_created": participations_created,
        "conflicts": conflicts,
    })


def _int_or_none(value):
    return int(value) if str(value or "").isdigit() else None


def _norm(text):
    return " ".join((text or "").replace("ё", "е").replace("Ё", "Е").lower().split())


def _find_athlete(last_name, first_name, birth_date):
    """Спортсмен по фамилии и имени (без учёта регистра и ё/е) и, если
    известна, дате рождения."""
    query = Athlete.query
    if birth_date:
        query = query.filter(Athlete.birth_date == birth_date)
    for athlete in query.all():
        if _norm(athlete.last_name) == _norm(last_name) and _norm(athlete.first_name) == _norm(first_name):
            return athlete
    return None


@bp.route("/competition/results", methods=["POST"])
@require_api_key
def competition_results():
    """Лучшие результаты спортсменов на соревновании COREZ (кнопка «Результаты
    в карточки спортсменов» на странице «Отчёты» COREZ) — в раздел «Данные об
    участии в соревнованиях» карточки спортсмена. Запись участия этого
    соревнования (созданная, например, при импорте заявки) обновляется,
    иначе добавляется. Спортсмены, которых нет в базе, не создаются.

    Тело запроса (JSON):
      competition_id, competition_name, competition_period_place («Сроки и место проведения»),
      athletes — [{last_name, first_name, middle_name, birth_date (ISO), result}, …]

    Ответ: {updated, created, not_found: [ФИО, …]}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Ожидается JSON."}), 400

    corez_id = _int_or_none(data.get("competition_id"))
    competition_name = (data.get("competition_name") or "").strip()
    period_place = (data.get("competition_period_place") or "").strip() or None
    updated, created, not_found = 0, 0, []

    for a in data.get("athletes") or []:
        last_name = (a.get("last_name") or "").strip()
        first_name = (a.get("first_name") or "").strip()
        try:
            birth_date = date.fromisoformat(a.get("birth_date")) if a.get("birth_date") else None
        except ValueError:
            birth_date = None
        athlete = _find_athlete(last_name, first_name, birth_date)
        if athlete is None:
            not_found.append(" ".join(x for x in (last_name, first_name, a.get("middle_name") or "") if x))
            continue

        record = None
        if corez_id is not None:
            record = CompetitionParticipation.query.filter_by(
                athlete_id=athlete.id, corez_competition_id=corez_id).first()
        if record is None and competition_name:
            record = CompetitionParticipation.query.filter_by(
                athlete_id=athlete.id, competition_name=competition_name).first()
        if record is None:
            record = CompetitionParticipation(athlete_id=athlete.id, competition_name=competition_name)
            db.session.add(record)
            created += 1
        else:
            updated += 1
        record.corez_competition_id = corez_id
        record.competition_name = record.competition_name or competition_name
        record.period_place = period_place or record.period_place
        record.result = (a.get("result") or "").strip() or record.result

    db.session.commit()
    return jsonify({"updated": updated, "created": created, "not_found": not_found})


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
