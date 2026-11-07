# models.py — модели SQLAlchemy
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Subject(db.Model):
    """Субъект Российской Федерации, обслуживаемый этим инстансом —
    переключатель в шапке делит базу на независимые разделы (каждый
    субъект видит только свои записи)."""
    __tablename__ = "subject"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Organization(db.Model):
    """Физкультурно-спортивная организация в рамках субъекта РФ — такой
    же переключатель в шапке, как Subject, но на уровень ниже: список
    сборной команды конкретной организации (внутри текущего субъекта)."""
    __tablename__ = "organization"
    __table_args__ = (db.UniqueConstraint("subject_id", "name", name="uq_organization_subject_name"),)

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    subject = db.relationship("Subject")
    name = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Athlete(db.Model):
    __tablename__ = "athlete"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    subject = db.relationship("Subject")

    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))

    birth_date = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(20), nullable=False)

    discipline = db.Column(db.String(300))
    category = db.Column(db.String(50))
    age_category = db.Column(db.String(50))
    rank = db.Column(db.String(50))

    organization = db.Column(db.String(300))
    territory = db.Column(db.String(100))
    trainer = db.Column(db.String(200))
    doctor_notes = db.Column(db.Text)

    result_regional = db.Column(db.String(100))
    result_national = db.Column(db.String(100))
    result_international = db.Column(db.String(100))

    national_team = db.Column(db.String(200))

    is_active = db.Column(db.Boolean, default=False, nullable=False)
    in_list = db.Column(db.Boolean, default=False, nullable=False)
    is_imported = db.Column(db.Boolean, default=False, nullable=False)
    imported_pending = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    change_logs = db.relationship(
        "ChangeLog", backref="athlete", lazy=True, order_by="ChangeLog.change_date.desc()",
        cascade="all, delete-orphan",
    )
    medical_clearances = db.relationship(
        "MedicalClearance", backref="athlete", lazy=True, order_by="MedicalClearance.id",
        cascade="all, delete-orphan",
    )
    anthropometry_records = db.relationship(
        "AnthropometryRecord", backref="athlete", lazy=True, order_by="AnthropometryRecord.id",
        cascade="all, delete-orphan",
    )
    transfer_records = db.relationship(
        "TransferRecord", backref="athlete", lazy=True, order_by="TransferRecord.id",
        cascade="all, delete-orphan",
    )
    penalties = db.relationship(
        "Penalty", backref="athlete", lazy=True, order_by="Penalty.id",
        cascade="all, delete-orphan",
    )
    gto_records = db.relationship(
        "GtoRecord", backref="athlete", lazy=True, order_by="GtoRecord.id",
        cascade="all, delete-orphan",
    )
    norm_fulfillments = db.relationship(
        "NormFulfillment", backref="athlete", lazy=True, order_by="NormFulfillment.id",
        cascade="all, delete-orphan",
    )
    yearly_summaries = db.relationship(
        "YearlySummary", backref="athlete", lazy=True, order_by="YearlySummary.id",
        cascade="all, delete-orphan",
    )
    awards = db.relationship(
        "Award", backref="athlete", lazy=True, order_by="Award.id",
        cascade="all, delete-orphan",
    )
    competition_participations = db.relationship(
        "CompetitionParticipation", backref="athlete", lazy=True, order_by="CompetitionParticipation.id",
        cascade="all, delete-orphan",
    )

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)


class ChangeLog(db.Model):
    __tablename__ = "change_log"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    change_type = db.Column(db.String(20), nullable=False)  # 'включён' / 'исключён'
    change_date = db.Column(db.Date, nullable=False)
    document_number = db.Column(db.String(50))
    reason = db.Column(db.String(300))


class ReportSettings(db.Model):
    __tablename__ = "report_settings"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    organization_name = db.Column(db.String(300))
    chairman_position = db.Column(db.String(200))
    chairman_name = db.Column(db.String(200))
    head_coach_name = db.Column(db.String(200))
    sport_name = db.Column(db.String(200))
    year = db.Column(db.Integer)
    main_list_approval_date = db.Column(db.Date)


class ListChangeRecord(db.Model):
    __tablename__ = "list_change_record"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    number = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)


# --- Разделы разрядной книжки спортсмена -----------------------------------

class MedicalClearance(db.Model):
    """Разрешение врача на участие в соревнованиях."""
    __tablename__ = "athlete_medical_clearance"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    date = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    doctor_name = db.Column(db.String(200))


class AnthropometryRecord(db.Model):
    """Основные антропометрические данные — сетка показатель × год."""
    __tablename__ = "athlete_anthropometry"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    metric = db.Column(db.String(100), nullable=False)
    column_index = db.Column(db.Integer, nullable=False)
    year_label = db.Column(db.String(20))
    value = db.Column(db.String(50))


class TransferRecord(db.Model):
    """Отметки о переходе в другую спортивную организацию."""
    __tablename__ = "athlete_transfer_record"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    left_organization = db.Column(db.String(300))
    joined_organization = db.Column(db.String(300))


class Penalty(db.Model):
    """Взыскания."""
    __tablename__ = "athlete_penalty"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    date = db.Column(db.Date)
    description = db.Column(db.String(300))
    responsible_person = db.Column(db.String(200))


class GtoRecord(db.Model):
    """Сдача норм ГТО."""
    __tablename__ = "athlete_gto_record"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    date = db.Column(db.Date)
    result = db.Column(db.String(200))
    responsible_person = db.Column(db.String(200))


class NormFulfillment(db.Model):
    """Выполнение норм спортивного разряда/звания."""
    __tablename__ = "athlete_norm_fulfillment"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    requirement_level = db.Column(db.String(200))
    date = db.Column(db.Date)
    result = db.Column(db.String(200))
    responsible_person = db.Column(db.String(200))


class YearlySummary(db.Model):
    """Итоговые данные об участии в соревнованиях (по годам)."""
    __tablename__ = "athlete_yearly_summary"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    year = db.Column(db.String(20))
    competitions_count = db.Column(db.String(50))
    best_result = db.Column(db.String(200))


class Award(db.Model):
    """Награждения."""
    __tablename__ = "athlete_award"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    date = db.Column(db.Date)
    reason = db.Column(db.String(300))
    awarded_by = db.Column(db.String(300))


class CompetitionParticipation(db.Model):
    """Данные об участии в соревнованиях."""
    __tablename__ = "athlete_competition_participation"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.id"), nullable=False)

    date = db.Column(db.Date)
    competition_name = db.Column(db.String(300))
    result = db.Column(db.String(200))
    responsible_person = db.Column(db.String(200))
