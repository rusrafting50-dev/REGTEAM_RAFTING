# sync_to_rafting_cfo.py — отправка спортсменов и тренеров сборной на сайт RAFTING_CFO
#
# RAFTING_CFO показывает состав сборной на двух страницах:
#   - раздел «Сборная команда» на персональной странице региональной
#     федерации (сопоставление по совпадению territory с наименованием
#     субъекта РФ этой федерации);
#   - разделы «Тренеры»/«Спортсмены» на странице клуба (сопоставление
#     по совпадению organization с названием клуба).
# Поэтому territory здесь — НЕ внутренний район/город Московской
# области (Athlete.territory в этой базе), а фиксированное наименование
# субъекта РФ, которое обслуживает этот инстанс REGTEAM_RAFTING —
# RAFTING_CFO_REGION_SUBJECT_NAME из .env (напр. "Московская область").
# Внутренний район не отправляется — на сайте ЦФО он не нужен.
#
# Отправка происходит автоматически при каждом изменении спортсмена/
# тренера (routes/athletes.py) — сайт должен быть источником, всегда
# отражающим текущий актуальный состав, а не результатом ручной кнопки.
# Ошибка отправки не должна ломать сохранение в локальной базе — это
# сторонняя система, локальная база REGTEAM_RAFTING остаётся источником
# истины независимо от того, доступен сайт сейчас или нет.
#
# Адрес и ключ — RAFTING_CFO_URL / RAFTING_CFO_API_KEY в .env; ключ
# должен совпадать с API_KEY в .env самого RAFTING_CFO.
#
# Значения читаются из os.environ при каждом вызове (не на уровне
# модуля), чтобы правка .env не требовала полного перезапуска процесса.
import os
import re

import requests

TRAINER_CATEGORY_PATTERN = re.compile(r"(?i)тренер")


def _адрес():
    return os.environ.get("RAFTING_CFO_URL", "http://127.0.0.1:5003").rstrip("/")


def _ключ():
    return os.environ.get("RAFTING_CFO_API_KEY", "")


def _субъект_рф():
    return os.environ.get("RAFTING_CFO_REGION_SUBJECT_NAME", "")


def _роль(category):
    """category здесь — "Спортсмен"/"Тренер"/"Главный тренер"/"Специалист" и
    т.п. (см. references.CATEGORIES, TRAINER_CATEGORY_OPTIONS) — на сайте
    роль всегда либо "тренер", либо исходная категория в нижнем регистре
    (см. Athlete.role в RAFTING_CFO — используется в т.ч. для фильтра по
    ролям спортсмен/тренер)."""
    category = (category or "").strip()
    if TRAINER_CATEGORY_PATTERN.search(category):
        return "тренер"
    return category.lower()


def _собрать_данные(athlete):
    return {
        "source_id": athlete.id,
        "full_name": athlete.full_name,
        "role": _роль(athlete.category),
        "discipline": athlete.discipline,
        "rank": athlete.rank,
        "organization": athlete.organization,
        "territory": _субъект_рф(),
        "national_team": athlete.national_team,
        "is_active": bool(athlete.is_active),
    }


def _отправить(items):
    """Общая отправка POST {"items": [...]} на /api/sync/athletes. Возвращает
    (успех, сообщение) — используется и для upsert, и для удаления."""
    ключ = _ключ()
    if not ключ:
        return False, "RAFTING_CFO_API_KEY не задан в .env — см. .env.example"

    адрес = _адрес()
    try:
        ответ = requests.post(
            f"{адрес}/api/sync/athletes",
            json={"items": items},
            headers={"X-API-Key": ключ},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"Не удалось соединиться с RAFTING_CFO ({адрес}): {exc}"

    if ответ.status_code == 401:
        return False, "RAFTING_CFO отклонил запрос: неверный RAFTING_CFO_API_KEY."
    if ответ.status_code != 200:
        return False, f"RAFTING_CFO ответил ошибкой {ответ.status_code}: {ответ.text[:200]}"

    return True, "Отправлено на RAFTING_CFO."


def отправить_спортсмена(athlete):
    """Отправляет спортсмена/тренера на RAFTING_CFO (создание или
    обновление — сторона RAFTING_CFO определяет это сама по source_id).
    Возвращает (успех, сообщение)."""
    if not _субъект_рф():
        return False, "RAFTING_CFO_REGION_SUBJECT_NAME не задан в .env — см. .env.example"
    return _отправить([_собрать_данные(athlete)])


def удалить_спортсмена(athlete_id):
    """Удаляет спортсмена/тренера на RAFTING_CFO по source_id (вызывать
    ПОСЛЕ athletes_delete — для исключения из состава без удаления
    записи используется отправить_спортсмена с is_active=False, эта
    функция — только для настоящего удаления записи)."""
    return _отправить([{"source_id": athlete_id, "deleted": True}])
