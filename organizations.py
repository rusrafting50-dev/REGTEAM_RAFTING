# organizations.py — физкультурно-спортивные организации в рамках субъекта РФ
#
# Организация — такой же справочник-переключатель, как субъект РФ
# (subjects.py), но на уровень ниже: список сборной команды конкретной
# организации внутри текущего субъекта. В отличие от субъекта она НЕ
# меняет область видимости всего приложения (это по-прежнему текущий
# субъект из сессии) — организация лишь ФИЛЬТРУЕТ список спортсменов,
# реиспользуя уже существующий параметр ?organization= на странице
# /athletes (см. routes/athletes.py, _apply_common_filters). Athlete.
# organization остаётся свободным текстовым полем (как и было) —
# справочник Organization лишь даёт готовые пункты меню для перехода,
# точное совпадение по имени.
#
# Текущая выбранная организация хранится в сессии (как и текущий
# субъект) — только чтобы шапка показывала её наименование вместо
# статичной надписи «Сборная команда» (она же — пункт сброса фильтра
# на существующую страницу /athletes/ без фильтра).
from flask import session

from models import Organization


def организации_субъекта(subject_id):
    return Organization.query.filter_by(subject_id=subject_id).order_by(Organization.name).all()


def текущая_организация_id():
    return session.get("organization_id")


def текущая_организация():
    organization_id = текущая_организация_id()
    return Organization.query.get(organization_id) if organization_id else None


def субъект_по_организации(organization_name, subject_id=None):
    """Субъект РФ организации спортсмена (по точному совпадению имени) —
    для строки «Субъект Российской Федерации» на карточке спортсмена.
    Сначала ищет в пределах subject_id (обычно — свой же субъект
    спортсмена), затем — среди всех субъектов (на случай, если
    организация почему-то зарегистрирована не под тем же субъектом)."""
    if not organization_name:
        return None
    query = Organization.query.filter_by(name=organization_name)
    org = query.filter_by(subject_id=subject_id).first() if subject_id else None
    if org is None:
        org = query.first()
    return org.subject if org else None
