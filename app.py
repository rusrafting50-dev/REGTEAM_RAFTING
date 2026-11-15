# app.py — точка входа, инициализация Flask и БД
import os
import re
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine

from models import Athlete, CompetitionParticipation, ListChangeRecord, Organization, ReportSettings, Subject, db
from organizations import организации_субъекта, текущая_организация
from routes.api import bp as api_bp
from routes.athletes import bp as athletes_bp
from routes.import_export import bp as import_export_bp
from routes.reports import bp as reports_bp
from subjects import обеспечить_субъекты, результат_субъекта_заголовок, текущий_субъект, текущий_субъект_id

# override=True — .env должен побеждать даже если такая переменная уже
# случайно задана на уровне Windows (иначе пустое/старое системное
# значение молча маскирует правильное значение из .env).
load_dotenv(override=True)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

CATEGORY_PATTERN = re.compile(r"\s*(\(\s*\d+\s*-\s*\d+\s*категория\s*\))", re.IGNORECASE)
TRAINER_SEPARATOR = re.compile(r",\s*")


def break_before_category(value):
    """Каждая дисциплина через запятую — на новую строку; внутри — перенос перед '(N-N категория)'."""
    if not value:
        return value
    parts = TRAINER_SEPARATOR.split(str(escape(value)))
    parts = [CATEGORY_PATTERN.sub(r"<br>\1", part) for part in parts]
    return Markup(",<br>".join(parts))


def break_trainers(value):
    """Каждого тренера (через запятую) — на отдельную строку, с запятой после инициалов."""
    if not value:
        return value
    parts = TRAINER_SEPARATOR.split(str(escape(value)))
    return Markup(",<br>".join(parts))


@event.listens_for(Engine, "connect")
def _register_sqlite_regexp(dbapi_connection, connection_record):
    """SQLite не поддерживает REGEXP без явной регистрации функции (нужно для фильтра "Маршруты")."""
    dbapi_connection.create_function(
        "REGEXP", 2, lambda pattern, value: value is not None and re.search(pattern, value) is not None
    )


def _sync_missing_columns():
    """Добавляет в уже существующую БД колонки, которых нет (db.create_all() таблицы не изменяет)."""
    inspector = inspect(db.engine)
    for table in db.metadata.tables.values():
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(db.engine.dialect)
            with db.engine.connect() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                conn.commit()


def _backfill_in_list():
    """Ставит in_list=True всем спортсменам, у которых is_active=True,
    но in_list не True (NULL или False — ALTER TABLE не задаёт DEFAULT)."""
    db.session.query(Athlete).filter(
        Athlete.is_active == True,
        Athlete.in_list.isnot(True),
    ).update({"in_list": True}, synchronize_session=False)
    db.session.commit()


def _backfill_participation_period():
    """«Дата» участия в соревнованиях заменена текстом «Сроки и место
    проведения» — прежние даты переносятся туда (только в пустые)."""
    for record in CompetitionParticipation.query.filter(
        CompetitionParticipation.period_place.is_(None), CompetitionParticipation.date.isnot(None),
    ):
        record.period_place = record.date.strftime("%d.%m.%Y")
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "athletes.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.jinja_env.finalize = lambda value: "" if value is None else value
    app.jinja_env.filters["break_before_category"] = break_before_category
    app.jinja_env.filters["break_trainers"] = break_trainers

    db.init_app(app)
    app.register_blueprint(api_bp)
    app.register_blueprint(athletes_bp)
    app.register_blueprint(import_export_bp)
    app.register_blueprint(reports_bp)

    with app.app_context():
        db.create_all()
        _sync_missing_columns()
        обеспечить_субъекты()
        _backfill_in_list()
        _backfill_participation_period()

    @app.context_processor
    def inject_subjects():
        return {
            "all_subjects": Subject.query.order_by(Subject.id).all(),
            "current_subject": текущий_субъект(),
            "current_subject_organizations": организации_субъекта(текущий_субъект_id()),
            "current_organization": текущая_организация(),
            "regional_result_label": результат_субъекта_заголовок(текущий_субъект()),
        }

    @app.context_processor
    def inject_pending_count():
        def pending_corez_count():
            try:
                return Athlete.query.filter_by(imported_pending=True).count()
            except Exception:
                return 0
        return {"pending_corez_count": pending_corez_count}

    @app.route("/")
    def index():
        return redirect(url_for("athletes.athletes_list"))

    @app.route("/subjects/<int:subject_id>/switch")
    def subjects_switch(subject_id):
        subject = Subject.query.get_or_404(subject_id)
        session["subject_id"] = subject.id
        session.pop("organization_id", None)  # организация прошлого субъекта здесь больше не действует
        return redirect(url_for("athletes.athletes_list"))

    def _to_settings(subject_id):
        """Назад на «Настройки» с раскрытым разделом этого субъекта."""
        return redirect(url_for("settings", open=subject_id) + f"#subject-{subject_id}")

    # Субъекты РФ добавляются и переименовываются только на странице
    # «Настройки»; в шапке — только переключение между ними.
    @app.route("/subjects", methods=["POST"])
    def subjects_add():
        name = request.form.get("name", "").strip()
        if not name:
            flash("Укажите наименование субъекта Российской Федерации", "error")
            return redirect(url_for("settings"))
        if Subject.query.filter_by(name=name).first():
            flash("Такой субъект уже есть в списке", "warning")
            return redirect(url_for("settings"))
        subject = Subject(name=name)
        db.session.add(subject)
        db.session.commit()
        flash(f"Субъект «{name}» добавлен", "success")
        return _to_settings(subject.id)

    @app.route("/subjects/<int:subject_id>/delete", methods=["POST"])
    def subjects_delete(subject_id):
        """Удаляет субъект вместе с его реквизитами, изменениями в список и
        муниципальными образованиями — только если у него нет спортсменов
        и он не последний."""
        subject = Subject.query.get_or_404(subject_id)
        athletes = Athlete.query.filter_by(subject_id=subject.id).count()
        if athletes:
            word = "спортсмен" if athletes % 10 == 1 and athletes % 100 != 11 else (
                "спортсмена" if athletes % 10 in (2, 3, 4) and athletes % 100 not in (12, 13, 14) else "спортсменов")
            flash(f"Нельзя удалить «{subject.name}»: в нём {athletes} {word}. "
                  "Сначала удалите или перенесите их.", "warning")
            return _to_settings(subject.id)
        if Subject.query.count() <= 1:
            flash("Нельзя удалить последний субъект", "warning")
            return _to_settings(subject.id)
        for model in (ReportSettings, ListChangeRecord, Organization):
            model.query.filter_by(subject_id=subject.id).delete(synchronize_session=False)
        if session.get("subject_id") == subject.id:
            session.pop("subject_id", None)
            session.pop("organization_id", None)
        name = subject.name
        db.session.delete(subject)
        db.session.commit()
        flash(f"Субъект «{name}» удалён", "success")
        return redirect(url_for("settings"))

    @app.route("/subjects/<int:subject_id>/rename", methods=["POST"])
    def subjects_rename(subject_id):
        subject = Subject.query.get_or_404(subject_id)
        name = request.form.get("name", "").strip()
        if not name:
            flash("Укажите наименование субъекта Российской Федерации", "error")
        elif Subject.query.filter(Subject.name == name, Subject.id != subject.id).first():
            flash("Субъект с таким наименованием уже есть в списке", "warning")
        else:
            subject.name = name
            db.session.commit()
            flash(f"Субъект переименован в «{name}»", "success")
        return _to_settings(subject.id)

    @app.route("/organizations/<int:organization_id>/switch")
    def organizations_switch(organization_id):
        organization = Organization.query.get_or_404(organization_id)
        session["organization_id"] = organization.id
        return redirect(url_for("athletes.athletes_list"))

    @app.route("/organizations/clear")
    def organizations_clear():
        session.pop("organization_id", None)
        return redirect(request.referrer or url_for("athletes.athletes_list"))

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Все субъекты РФ — по разделу на каждый: наименование, реквизиты для
        отчётов, «Изменения в список», муниципальные образования (сборные)."""
        if request.method == "POST":
            subject = Subject.query.get_or_404(request.form.get("subject_id", type=int))
            report_settings = ReportSettings.query.filter_by(subject_id=subject.id).first()
            if not report_settings:
                report_settings = ReportSettings(subject_id=subject.id)
                db.session.add(report_settings)
            report_settings.organization_name = request.form.get("organization_name", "").strip()
            report_settings.chairman_position = request.form.get("chairman_position", "").strip()
            report_settings.chairman_name = request.form.get("chairman_name", "").strip()
            report_settings.head_coach_name = request.form.get("head_coach_name", "").strip()
            report_settings.sport_name = request.form.get("sport_name", "").strip()
            year_raw = request.form.get("year", "").strip()
            report_settings.year = int(year_raw) if year_raw.isdigit() else None
            approval_date_raw = request.form.get("main_list_approval_date", "").strip()
            report_settings.main_list_approval_date = (
                datetime.strptime(approval_date_raw, "%Y-%m-%d").date() if approval_date_raw else None
            )
            db.session.commit()
            flash(f"Настройки субъекта «{subject.name}» сохранены", "success")
            return _to_settings(subject.id)

        subjects = Subject.query.order_by(Subject.id).all()
        sections = []
        for subject in subjects:
            sections.append({
                "subject": subject,
                "settings": ReportSettings.query.filter_by(subject_id=subject.id).first(),
                "list_changes": ListChangeRecord.query.filter_by(subject_id=subject.id).order_by(
                    ListChangeRecord.date.desc(), ListChangeRecord.id.desc()
                ).all(),
                "organizations": организации_субъекта(subject.id),
            })
        open_id = request.args.get("open", type=int) or текущий_субъект_id()
        return render_template(
            "settings.html", sections=sections, open_id=open_id, today=date.today().isoformat(),
        )

    def _parse_change_form():
        number = request.form.get("number", "").strip()
        date_raw = request.form.get("date", "").strip()
        if not number or not date_raw:
            flash("Укажите номер и дату изменения", "error")
            return None, None
        try:
            return number, datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Некорректная дата", "error")
            return None, None

    @app.route("/settings/list-changes", methods=["POST"])
    def settings_list_changes_add():
        subject = Subject.query.get_or_404(request.form.get("subject_id", type=int))
        number, change_date = _parse_change_form()
        if number:
            db.session.add(ListChangeRecord(subject_id=subject.id, number=number, date=change_date))
            db.session.commit()
            flash(f"Изменение в список добавлено ({subject.name})", "success")
        return _to_settings(subject.id)

    @app.route("/settings/list-changes/<int:record_id>/edit", methods=["POST"])
    def settings_list_changes_edit(record_id):
        record = ListChangeRecord.query.get_or_404(record_id)
        number, change_date = _parse_change_form()
        if number:
            record.number = number
            record.date = change_date
            db.session.commit()
            flash("Изменение в список обновлено", "success")
        return _to_settings(record.subject_id)

    @app.route("/settings/list-changes/<int:record_id>/delete", methods=["POST"])
    def settings_list_changes_delete(record_id):
        record = ListChangeRecord.query.get_or_404(record_id)
        subject_id = record.subject_id
        db.session.delete(record)
        db.session.commit()
        flash("Изменение в список удалено", "success")
        return _to_settings(subject_id)

    # Муниципальные образования (организации) — пункты меню «Сборная команда»
    # в шапке; у каждого свой субъект РФ, меню показывает только образования
    # текущего субъекта.
    @app.route("/settings/organizations", methods=["POST"])
    def settings_organizations_add():
        subject = Subject.query.get_or_404(request.form.get("subject_id", type=int))
        name = request.form.get("name", "").strip()
        if not name:
            flash("Укажите наименование", "error")
        elif Organization.query.filter_by(subject_id=subject.id, name=name).first():
            flash("Такая организация или клуб уже есть у этого субъекта", "warning")
        else:
            db.session.add(Organization(subject_id=subject.id, name=name))
            db.session.commit()
            flash(f"«{name}» добавлено ({subject.name})", "success")
        return _to_settings(subject.id)

    @app.route("/settings/organizations/<int:organization_id>/edit", methods=["POST"])
    def settings_organizations_edit(organization_id):
        organization = Organization.query.get_or_404(organization_id)
        name = request.form.get("name", "").strip()
        if not name:
            flash("Укажите наименование", "error")
        elif Organization.query.filter(Organization.subject_id == organization.subject_id,
                                       Organization.name == name, Organization.id != organization.id).first():
            flash("Такая организация или клуб уже есть у этого субъекта", "warning")
        else:
            # Athlete.organization — свободный текст, совпадающий с названием: переименовываем и у спортсменов
            Athlete.query.filter_by(subject_id=organization.subject_id, organization=organization.name).update(
                {"organization": name}, synchronize_session=False)
            organization.name = name
            db.session.commit()
            flash(f"Переименовано в «{name}»", "success")
        return _to_settings(organization.subject_id)

    @app.route("/settings/organizations/<int:organization_id>/delete", methods=["POST"])
    def settings_organizations_delete(organization_id):
        organization = Organization.query.get_or_404(organization_id)
        subject_id = organization.subject_id
        if session.get("organization_id") == organization.id:
            session.pop("organization_id", None)
        db.session.delete(organization)
        db.session.commit()
        flash(f"«{organization.name}» удалено из списка", "success")
        return _to_settings(subject_id)

    return app


app = create_app()


if __name__ == "__main__":
    # Порт 5001 — на него ведут 1_Запуск.bat (start http://localhost:5001)
    # и адрес по умолчанию в CLAUDE.md; без явного port Flask слушает
    # 5000, и сайт был недоступен по документированному адресу.
    app.run(debug=True, port=5001)
