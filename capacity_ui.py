# -*- coding: utf-8 -*-
"""Формирование данных для отображения аналитики и прогнозов (таблица)."""
from typing import Any, Dict, List


def build_forecast_table_rows(
    capacity: Dict[str, Any],
    shortfall: Dict[str, Any],
    period_label: str = "выбранном периоде",
) -> List[Dict[str, str]]:
    """
    Строит список строк для таблицы «Аналитика и прогнозы».
    capacity — результат annual_project_capacity(conn);
    shortfall — результат overload_shortfall(conn, start_str, end_str);
    period_label — подпись периода для сообщения о перегрузках (напр. «30 дней» или «выбранном периоде»).
    Терминология: Технический специалист (вместо n_junior/младший), Руководитель (вместо n_senior/старший).
    """
    rows: List[Dict[str, str]] = []
    _cap = capacity.get("N_capacity", 0)
    _limited = capacity.get("capacity_limited_by")
    _n_j = capacity.get("n_junior", 0)
    _n_s = capacity.get("n_senior", 0)
    _P = capacity.get("P", 0)

    if _cap > 0 and _limited:
        if _limited == "juniors":
            text = (
                f"Для увеличения числа проектов целесообразно нанять технических специалистов. "
                f"Сейчас ёмкость ограничена числом технических специалистов ({_n_j}); "
                f"каждый новый технический специалист при сохранении числа руководителей может дать дополнительный проект."
            )
        else:
            text = (
                f"Для увеличения числа проектов целесообразно нанять руководителей. "
                f"Сейчас ёмкость ограничена числом руководителей или лимитом одновременных проектов "
                f"({_n_s} руководителей, P = {_P}). По формуле каждый проект ведёт ведущий (руководитель); "
                f"пока P не вырастет, найм технических специалистов не увеличит число проектов."
            )
        rows.append({"Блок": "Рекомендация по набору", "Содержание": text})

    mj = capacity.get("missing_juniors", 0)
    ms = capacity.get("missing_seniors", 0)
    if (mj + ms) > 0:
        text = (
            f"Для взятия новых или реализации текущих проектов не хватает: "
            f"{mj} технических специалистов, {ms} руководителей."
        )
        rows.append({"Блок": "Прогноз (нехватка специалистов)", "Содержание": text})

    equiv = shortfall.get("equivalent_missing_fte", 0)
    if equiv > 0:
        text = (
            f"В {period_label} из-за перегрузок эквивалентно не хватает {equiv} сотрудников."
        )
        rows.append({"Блок": "Прогноз (перегрузки)", "Содержание": text})

    return rows


def build_optimization_hint_rows(
    capacity: Dict[str, Any],
    shortfall: Dict[str, Any],
    overload_by_employee: List[Dict[str, Any]] = None,
    period_label: str = "выбранном периоде",
) -> List[Dict[str, str]]:
    """
    Строит строки для интерактивной подсказки по оптимизации персонала.
    Использует существующую логику прогноза и добавляет краткий итог по перегруженным сотрудникам.
    """
    rows: List[Dict[str, str]] = []
    rows.append(
        {
            "Блок": "Текущая картина",
            "Содержание": (
                f"В расчёте ёмкости сейчас учтено проектов: {capacity.get('N_active', 0)}. "
                f"Проектов можно взять дополнительно: {capacity.get('projects_possible', 0)}."
            ),
        }
    )

    rows.extend(build_forecast_table_rows(capacity, shortfall, period_label=period_label))

    overloaded = overload_by_employee or []
    if overloaded:
        top = overloaded[:3]
        top_text = ", ".join(
            f"{item.get('employee_name', '—')} ({item.get('overload_days', 0)} дн.; +{item.get('overload_ftedays', 0)} FTE-дн.)"
            for item in top
        )
        rows.append(
            {
                "Блок": "Точки перегрузки",
                "Содержание": (
                    f"Наибольшая перегрузка в {period_label}: {top_text}."
                ),
            }
        )

    if len(rows) == 1:
        rows.append(
            {
                "Блок": "Рекомендация",
                "Содержание": "По текущим данным явных рекомендаций по оптимизации персонала не требуется.",
            }
        )
    return rows
