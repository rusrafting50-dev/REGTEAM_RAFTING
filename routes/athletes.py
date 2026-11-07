# routes/athletes.py — CRUD спортсменов
import re
from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import references
from models import (
    Athlete, AnthropometryRecord, Award, ChangeLog, CompetitionParticipation, GtoRecord,
    MedicalClearance, NormFulfillment, Penalty, TransferRecord, YearlySummary, db,
)
from organizations import субъект_по_организации, текущая_организация
from subjects import текущий_субъект_id
from sync_to_rafting_cfo import отправить_всех, отправить_спортсмена, удалить_спортсмена

bp = Blueprint("athletes", __name__, url_prefix="/athletes")


def _синхронизировать(athlete):
    """Отправляет спортсмена/тренера на RAFTING_CFO — только по нажатию
    кнопки «Отправить на сайт» (athletes_send_to_site), не автоматически
    при сохранении/включении/исключении. Не бросает исключение — при
    ошибке только предупреждаем flash-сообщением."""
    success, message = отправить_спортсмена(athlete)
    if success:
        flash("Отправлено на сайт.", "success")
    else:
        flash(f"Не удалось синхронизировать с сайтом: {message}", "warning")

PER_PAGE = 20

# Варианты поля "Спортивная дисциплина или группа дисциплин" в формах
# добавления/редактирования спортсмена и тренера
DISCIPLINE_SELECT_OPTIONS = ["Все дисциплины", "Группа дисциплин R4", "Группа дисциплин R6"]

# Кнопки на странице / ("Список сборной команды") — по группам возрастных категорий.
# Последний элемент каждого кортежа — заголовок H1 страницы категории
# («Спортсмены: <возрастная категория>»), второй — подпись самой кнопки
# на главной странице (без префикса «Спортсмены:»).
TEAM_AGE_CATEGORY_TYPES = [
    ("/team/men-women", "Мужчины, женщины", "athletes.athletes_team_men_women", ["Мужчины", "Женщины"], "Спортсмены: Мужчины, женщины"),
    ("/team/juniors", "Юниоры, юниорки", "athletes.athletes_team_juniors", ["Юниоры", "Юниорки"], "Спортсмены: Юниоры, юниорки"),
    ("/team/youth", "Юноши, девушки", "athletes.athletes_team_youth", ["Юноши", "Девушки"], "Спортсмены: Юноши, девушки"),
]

# Тот же ряд кнопок показывается на ВСЕХ связанных страницах (общий
# список, каждая возрастная категория, тренеры) — какая из них сейчас
# активна, определяется в шаблоне по request.endpoint (см.
# templates/athletes/list.html), а не передаётся отдельным флагом.
LIST_BUTTONS = (
    [("", "Все возрастные категории", "athletes.athletes_list", [], "Все возрастные категории")]
    + TEAM_AGE_CATEGORY_TYPES
    + [("", "Тренеры", "athletes.athletes_trainers_list", [], "Тренеры")]
)

# Тренер / Главный тренер / тренер — без учёта регистра
TRAINER_CATEGORY_PATTERN = r"(?i)тренер"

# Варианты категории для формы добавления тренера
TRAINER_CATEGORY_OPTIONS = ["Главный тренер", "Тренер", "Специалист"]

# Категория для формы добавления спортсмена
ATHLETE_CATEGORY_OPTIONS = ["Спортсмен"]

# Варианты возрастной категории для формы добавления тренера
TRAINER_AGE_CATEGORY_OPTIONS = [
    "Все возрастные категории",
    "Мужчины",
    "Женщины",
    "Мужчины, женщины",
    "Мужчины, юниоры",
    "Женщины, юниорки",
    "Юниоры",
    "Юниорки",
    "Юниоры, юниорки",
    "Юноши",
    "Девушки",
    "Юноши, девушки",
]


def _apply_common_filters(query):
    age_category = request.args.get("age_category", "")
    territory = request.args.get("territory", "")
    organization = request.args.get("organization", "")

    if age_category:
        query = query.filter(Athlete.age_category == age_category)
    if territory:
        query = query.filter(Athlete.territory == territory)
    if organization:
        query = query.filter(Athlete.organization == organization)

    filters = {
        "age_category": age_category,
        "territory": territory,
        "organization": organization,
    }
    return query, filters


def _scope_to_organization(query):
    """Сужает запрос до текущей выбранной в шапке организации (сессия,
    organizations.py) — применяется ко ВСЕМ списочным страницам
    (главный список, страницы возрастных категорий, тренеры), чтобы
    выбор организации оставался «приклеенным» при переходах между ними
    по кнопкам, а не только на том же экране, где её выбрали."""
    organization = текущая_организация()
    if organization:
        query = query.filter(Athlete.organization == organization.name)
    return query


def _with_current_value(options, current_value):
    """Список options, дополненный current_value, если его там ещё нет (чтобы не потерять при сохранении)."""
    if current_value and current_value not in options:
        return options + [current_value]
    return options


def _distinct_organizations():
    rows = (
        db.session.query(Athlete.organization)
        .filter(
            Athlete.subject_id == текущий_субъект_id(),
            Athlete.organization.isnot(None), Athlete.organization != "",
        )
        .distinct()
        .order_by(Athlete.organization)
        .all()
    )
    return [row[0] for row in rows]


def _get_athlete_or_404(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)
    if athlete.subject_id != текущий_субъект_id():
        abort(404)
    return athlete


def _render_athletes_list(
    query, heading="Спортсмены", show_add_button=True, discipline_preset=None,
    link_fio_to_new=False, link_fio_to_edit=False, discipline_group=None,
    add_button_label="Добавить спортсмена", add_form_variant=None, age_category_filter_options=None,
    highlight_active=True, **extra_context,
):
    query, filters = _apply_common_filters(query)
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(Athlete.last_name).paginate(page=page, per_page=PER_PAGE, error_out=False)
    return render_template(
        "athletes/list.html",
        athletes=pagination.items,
        pagination=pagination,
        filters=filters,
        references=references,
        organizations=_distinct_organizations(),
        heading=heading,
        show_add_button=show_add_button,
        discipline_preset=discipline_preset,
        link_fio_to_new=link_fio_to_new,
        link_fio_to_edit=link_fio_to_edit,
        age_category_filter_options=age_category_filter_options or references.AGE_CATEGORIES,
        discipline_group=discipline_group,
        add_button_label=add_button_label,
        add_form_variant=add_form_variant,
        highlight_active=highlight_active,
        **extra_context,
    )


@bp.route("/")
def athletes_list():
    organization = текущая_организация()
    query = Athlete.query.filter_by(subject_id=текущий_субъект_id())
    if organization:
        # Страница клуба — все его спортсмены, а не только уже включённые
        # в сборную (is_active): новый спортсмен сначала просто числится
        # за клубом, включение в сборную — отдельное действие.
        query = _scope_to_organization(query)
    else:
        # Все спортсмены «в списке»: в сборной (зелёные) и просто числящиеся.
        query = query.filter_by(in_list=True)
    heading = f"Спортсмены и специалисты: {organization.name}" if organization else "Список сборной команды"
    pending_count = Athlete.query.filter_by(
        subject_id=текущий_субъект_id(), imported_pending=True
    ).count()
    return _render_athletes_list(
        query, list_buttons=LIST_BUTTONS,
        heading=heading,
        show_add_button=False, highlight_active=True,
        pending_count=pending_count,
    )


@bp.route("/pending")
def athletes_pending():
    """Импортированные из COREZ спортсмены (imported_pending=True) — на рассмотрении."""
    query = Athlete.query.filter_by(subject_id=текущий_субъект_id(), imported_pending=True)
    return _render_athletes_list(
        query,
        heading="На рассмотрении (импортированные из COREZ)",
        show_add_button=False, highlight_active=False,
        list_buttons=None,
        pending_count=0,
        show_activate_button=True,
    )


@bp.route("/trainers")
def athletes_trainers_list():
    query = Athlete.query.filter(
        Athlete.subject_id == текущий_субъект_id(),
        Athlete.category.op("REGEXP")(TRAINER_CATEGORY_PATTERN),
    )
    query = _scope_to_organization(query)
    return _render_athletes_list(
        query, heading="Тренеры", list_buttons=LIST_BUTTONS,
        add_button_label="Добавить тренера", add_form_variant="trainer",
        age_category_filter_options=TRAINER_AGE_CATEGORY_OPTIONS,
    )


def _make_age_category_view(age_categories, heading):
    def view():
        query = Athlete.query.filter(
            Athlete.subject_id == текущий_субъект_id(),
            Athlete.age_category.in_(age_categories),
        )
        query = _scope_to_organization(query)
        return _render_athletes_list(
            query, heading=heading, list_buttons=LIST_BUTTONS,
            age_category_filter_options=age_categories,
            highlight_active=True,
        )
    return view


for _path, _label, _endpoint, _age_categories, _heading in TEAM_AGE_CATEGORY_TYPES:
    bp.add_url_rule(
        _path,
        endpoint=_endpoint.split(".")[1],
        view_func=_make_age_category_view(_age_categories, _heading),
    )


@bp.route("/new", methods=["GET", "POST"])
def athletes_new():
    if request.method == "POST":
        athlete = Athlete(subject_id=текущий_субъект_id())
        _fill_athlete_from_form(athlete, request.form)
        db.session.add(athlete)
        db.session.commit()
        flash("Спортсмен добавлен", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))

    discipline_options = DISCIPLINE_SELECT_OPTIONS
    if request.args.get("form_variant") == "trainer":
        category_options = TRAINER_CATEGORY_OPTIONS
        age_category_options = TRAINER_AGE_CATEGORY_OPTIONS
        entity_label = "тренера"
    else:
        category_options = ATHLETE_CATEGORY_OPTIONS
        age_category_options = None
        entity_label = "спортсмена"

    preset_discipline = request.args.get("discipline", "")
    if discipline_options and not preset_discipline:
        preset_discipline = discipline_options[0]

    return render_template(
        "athletes/form.html", athlete=None, references=references,
        preset_discipline=preset_discipline, discipline_options=discipline_options,
        category_options=category_options, age_category_options=age_category_options,
        entity_label=entity_label,
    )


@bp.route("/<int:athlete_id>")
def athletes_detail(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)
    organization_subject = субъект_по_организации(athlete.organization, athlete.subject_id)

    records_by_cell = {(r.metric, r.column_index): r for r in athlete.anthropometry_records}
    anthropometry_headers = [""] * 5
    for r in athlete.anthropometry_records:
        if r.year_label and 1 <= r.column_index <= 5:
            anthropometry_headers[r.column_index - 1] = r.year_label
    anthropometry_rows = []
    for i, metric in enumerate(references.ANTHROPOMETRY_METRICS):
        values = [
            (records_by_cell[(metric, col)].value or "") if (metric, col) in records_by_cell else ""
            for col in range(1, 6)
        ]
        anthropometry_rows.append((i, metric, values))

    return render_template(
        "athletes/detail.html", athlete=athlete, organization_subject=organization_subject,
        references=references,
        anthropometry_headers=anthropometry_headers, anthropometry_rows=anthropometry_rows,
    )


@bp.route("/<int:athlete_id>/edit", methods=["GET", "POST"])
def athletes_edit(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)

    if request.method == "POST":
        _fill_athlete_from_form(athlete, request.form)
        db.session.commit()
        flash("Изменения сохранены", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))

    is_trainer = bool(athlete.category and re.search(TRAINER_CATEGORY_PATTERN, athlete.category))
    if is_trainer:
        # Текущее значение спортсмена может не совпадать буквально ни с одним
        # из готовых вариантов (регистр, кавычки и т.п.) — добавляем его в список,
        # чтобы оно корректно подставлялось и не терялось при сохранении без изменений.
        category_options = _with_current_value(TRAINER_CATEGORY_OPTIONS, athlete.category)
        age_category_options = _with_current_value(TRAINER_AGE_CATEGORY_OPTIONS, athlete.age_category)
        entity_label = "тренера"
    else:
        category_options = None
        age_category_options = None
        entity_label = "спортсмена"
    discipline_options = _with_current_value(DISCIPLINE_SELECT_OPTIONS, athlete.discipline)

    return render_template(
        "athletes/form.html", athlete=athlete, references=references,
        category_options=category_options, age_category_options=age_category_options,
        discipline_options=discipline_options, entity_label=entity_label,
    )


@bp.route("/<int:athlete_id>/deactivate", methods=["POST"])
def athletes_deactivate(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)
    athlete.is_active = False
    db.session.add(
        ChangeLog(athlete_id=athlete.id, change_type="исключён", change_date=date.today())
    )
    db.session.commit()
    flash("Спортсмен исключён из списка", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))


@bp.route("/<int:athlete_id>/include-in-list", methods=["POST"])
def athletes_include_in_list(athlete_id):
    """Включить импортированного из COREZ спортсмена в список (без добавления в сборную)."""
    athlete = _get_athlete_or_404(athlete_id)
    athlete.imported_pending = False
    athlete.in_list = True
    db.session.commit()
    flash(f"{athlete.full_name} добавлен в список.", "success")
    next_url = request.form.get("next") or url_for("athletes.athletes_list")
    return redirect(next_url)


@bp.route("/<int:athlete_id>/activate", methods=["POST"])
def athletes_activate(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)
    is_first_add = not athlete.change_logs
    athlete.is_active = True
    athlete.in_list = True
    athlete.imported_pending = False
    db.session.add(
        ChangeLog(athlete_id=athlete.id, change_type="включён", change_date=date.today())
    )
    db.session.commit()
    flash("Спортсмен добавлен в список" if is_first_add else "Спортсмен возвращён в список", "success")
    next_url = request.form.get("next") or url_for("athletes.athletes_detail", athlete_id=athlete.id)
    return redirect(next_url)


@bp.route("/<int:athlete_id>/send-to-site", methods=["POST"])
def athletes_send_to_site(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)
    _синхронизировать(athlete)
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))


@bp.route("/send-all-to-site", methods=["POST"])
def athletes_send_all_to_site():
    """Отправляет на RAFTING_CFO всех спортсменов и тренеров текущего
    субъекта РФ разом (и включённых, и исключённых из состава) — см.
    отправить_всех."""
    athletes = Athlete.query.filter_by(subject_id=текущий_субъект_id()).all()
    success, message = отправить_всех(athletes)
    if success:
        flash(f"Отправлено на сайт: {len(athletes)}.", "success")
    else:
        flash(f"Не удалось синхронизировать с сайтом: {message}", "warning")
    return redirect(request.referrer or url_for("athletes.athletes_list"))


@bp.route("/<int:athlete_id>/delete", methods=["POST"])
def athletes_delete(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)
    is_trainer = bool(athlete.category and re.search(TRAINER_CATEGORY_PATTERN, athlete.category))
    db.session.delete(athlete)
    db.session.commit()
    success, message = удалить_спортсмена(athlete_id)
    if not success:
        flash(f"Не удалось синхронизировать удаление с сайтом: {message}", "warning")
    flash("Тренер удалён" if is_trainer else "Спортсмен удалён", "success")
    return redirect(url_for("athletes.athletes_trainers_list" if is_trainer else "athletes.athletes_list"))


@bp.route("/change-logs/<int:log_id>/edit", methods=["POST"])
def change_log_edit(log_id):
    log = ChangeLog.query.get_or_404(log_id)
    if log.athlete.subject_id != текущий_субъект_id():
        abort(404)
    date_raw = request.form.get("change_date", "").strip()
    if date_raw:
        try:
            log.change_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Некорректная дата", "error")
            return redirect(url_for("athletes.athletes_detail", athlete_id=log.athlete_id))
    log.document_number = request.form.get("document_number", "").strip() or None
    db.session.commit()
    flash("Запись о членстве в сборной команде обновлена", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=log.athlete_id))


@bp.route("/change-logs/<int:log_id>/delete", methods=["POST"])
def change_log_delete(log_id):
    log = ChangeLog.query.get_or_404(log_id)
    if log.athlete.subject_id != текущий_субъект_id():
        abort(404)
    athlete_id = log.athlete_id
    db.session.delete(log)
    db.session.commit()
    flash("Запись о членстве в сборной команде удалена", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete_id))


def _register_athlete_subtable_routes(model, slug, field_types, label):
    """Регистрирует POST-маршруты добавления/изменения/удаления записи простой
    CRUD-таблицы раздела разрядной книжки (одинаковой структуры для разных разделов)."""

    def _apply_fields(record, form):
        for name, kind in field_types.items():
            raw = form.get(name, "").strip()
            if kind == "date":
                setattr(record, name, datetime.strptime(raw, "%Y-%m-%d").date() if raw else None)
            else:
                setattr(record, name, raw or None)

    def add_view(athlete_id):
        athlete = _get_athlete_or_404(athlete_id)
        record = model(athlete_id=athlete.id)
        _apply_fields(record, request.form)
        db.session.add(record)
        db.session.commit()
        flash(f"{label}: запись добавлена", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))

    def edit_view(record_id):
        record = model.query.get_or_404(record_id)
        if record.athlete.subject_id != текущий_субъект_id():
            abort(404)
        _apply_fields(record, request.form)
        db.session.commit()
        flash(f"{label}: запись обновлена", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=record.athlete_id))

    def delete_view(record_id):
        record = model.query.get_or_404(record_id)
        if record.athlete.subject_id != текущий_субъект_id():
            abort(404)
        athlete_id = record.athlete_id
        db.session.delete(record)
        db.session.commit()
        flash(f"{label}: запись удалена", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete_id))

    bp.add_url_rule(f"/<int:athlete_id>/{slug}", endpoint=f"{slug}_add", view_func=add_view, methods=["POST"])
    bp.add_url_rule(f"/{slug}/<int:record_id>/edit", endpoint=f"{slug}_edit", view_func=edit_view, methods=["POST"])
    bp.add_url_rule(f"/{slug}/<int:record_id>/delete", endpoint=f"{slug}_delete", view_func=delete_view, methods=["POST"])


_register_athlete_subtable_routes(
    MedicalClearance, "medical_clearances",
    {"date": "date", "valid_until": "date", "doctor_name": "text"},
    "Разрешение врача",
)
_register_athlete_subtable_routes(
    TransferRecord, "transfer_records",
    {"left_organization": "text", "joined_organization": "text"},
    "Отметка о переходе",
)
_register_athlete_subtable_routes(
    Penalty, "penalties",
    {"date": "date", "description": "text", "responsible_person": "text"},
    "Взыскание",
)
_register_athlete_subtable_routes(
    GtoRecord, "gto_records",
    {"date": "date", "result": "text", "responsible_person": "text"},
    "Сдача норм ГТО",
)
_register_athlete_subtable_routes(
    NormFulfillment, "norm_fulfillments",
    {"requirement_level": "text", "date": "date", "result": "text", "responsible_person": "text"},
    "Выполнение норм",
)
_register_athlete_subtable_routes(
    YearlySummary, "yearly_summaries",
    {"year": "text", "competitions_count": "text", "best_result": "text"},
    "Итоговые данные об участии в соревнованиях",
)
_register_athlete_subtable_routes(
    Award, "awards",
    {"date": "date", "reason": "text", "awarded_by": "text"},
    "Награждение",
)
_register_athlete_subtable_routes(
    CompetitionParticipation, "competition_participations",
    {"date": "date", "competition_name": "text", "result": "text", "responsible_person": "text"},
    "Данные об участии в соревнованиях",
)


@bp.route("/<int:athlete_id>/anthropometry", methods=["POST"])
def anthropometry_save(athlete_id):
    athlete = _get_athlete_or_404(athlete_id)
    AnthropometryRecord.query.filter_by(athlete_id=athlete.id).delete()
    headers = [request.form.get(f"header_{col}", "").strip() for col in range(1, 6)]
    for i, metric in enumerate(references.ANTHROPOMETRY_METRICS):
        for col in range(1, 6):
            value = request.form.get(f"value_{i}_{col}", "").strip()
            db.session.add(AnthropometryRecord(
                athlete_id=athlete.id, metric=metric, column_index=col,
                year_label=headers[col - 1] or None, value=value or None,
            ))
    athlete.doctor_notes = request.form.get("doctor_notes", "").strip() or None
    db.session.commit()
    flash("Антропометрические данные сохранены", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))


def _fill_athlete_from_form(athlete, form):
    athlete.last_name = form.get("last_name", "").strip()
    athlete.first_name = form.get("first_name", "").strip()
    athlete.middle_name = form.get("middle_name", "").strip() or None

    birth_date = form.get("birth_date", "")
    athlete.birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date() if birth_date else None

    athlete.gender = form.get("gender", "")
    athlete.discipline = form.get("discipline", "")
    athlete.category = form.get("category", "")
    athlete.age_category = form.get("age_category", "")
    athlete.rank = form.get("rank", "")
    athlete.organization = form.get("organization", "").strip()
    athlete.territory = form.get("territory", "")
    athlete.trainer = form.get("trainer", "").strip()
    athlete.result_regional = form.get("result_regional", "").strip()
    athlete.result_national = form.get("result_national", "").strip()
    athlete.result_international = form.get("result_international", "").strip()
    athlete.national_team = form.get("national_team", "").strip()
