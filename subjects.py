# subjects.py — текущий выбранный субъект РФ (хранится в сессии) + сиды/бэкфилл
#
# Раньше одна база = один субъект РФ (Московская область, "зашита" в
# .env как RAFTING_CFO_REGION_SUBJECT_NAME для отправки на RAFTING_CFO).
# Теперь один инстанс обслуживает НЕСКОЛЬКО субъектов РФ одновременно —
# переключатель в шапке (см. templates/base.html) хранит выбор в сессии,
# и все страницы (список, импорт, отчёты, настройки) показывают только
# записи текущего субъекта.
from flask import session

from models import Athlete, ListChangeRecord, ReportSettings, Subject, db

DEFAULT_SUBJECT_NAME = "Московская область"
SEED_SUBJECT_NAMES = [
    DEFAULT_SUBJECT_NAME,
    "Белгородская область",
    "Город Москва",
    "Липецкая область",
    "Рязанская область",
]


def обеспечить_субъекты():
    """Создаёт справочные субъекты РФ (если их ещё нет) и переносит
    записи, созданные до этой фичи (subject_id ещё NULL — вся база тогда
    обслуживала только Московскую область), на субъект по умолчанию."""
    for name in SEED_SUBJECT_NAMES:
        if not Subject.query.filter_by(name=name).first():
            db.session.add(Subject(name=name))
    db.session.commit()

    default = Subject.query.filter_by(name=DEFAULT_SUBJECT_NAME).first()
    db.session.query(Athlete).filter(Athlete.subject_id.is_(None)).update({"subject_id": default.id})
    db.session.query(ReportSettings).filter(ReportSettings.subject_id.is_(None)).update({"subject_id": default.id})
    db.session.query(ListChangeRecord).filter(ListChangeRecord.subject_id.is_(None)).update({"subject_id": default.id})
    db.session.commit()


def текущий_субъект_id():
    subject_id = session.get("subject_id")
    if subject_id and Subject.query.get(subject_id):
        return subject_id
    default = Subject.query.filter_by(name=DEFAULT_SUBJECT_NAME).first()
    session["subject_id"] = default.id
    return default.id


def текущий_субъект():
    return Subject.query.get(текущий_субъект_id())
