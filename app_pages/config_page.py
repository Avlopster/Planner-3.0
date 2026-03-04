# -*- coding: utf-8 -*-
"""Страница «Конфигурация»: все настройки приложения (ёмкость, отпуска, даты, статусы)."""
import logging
from datetime import date
import re

import streamlit as st

import config as app_config
import repository
import load_calculator
from utils.app_logging import log_user_facing_error


def _parse_iso_date(s: str):
    """Проверка формата YYYY-MM-DD. Возвращает (True, value) или (False, None)."""
    if not s or not s.strip():
        return False, None
    s = s.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return False, None
    try:
        y, m, d = int(s[:4]), int(s[6:8]), int(s[9:11])
        date(y, m, d)
        return True, s
    except (ValueError, TypeError):
        return False, None


def render(conn):
    """Отрисовка страницы «Конфигурация»: настройки приложения (ёмкость, отпуска, статусы). conn — подключение к БД."""
    st.header("⚙️ Конфигурация")
    st.markdown("Все настройки приложения. Изменения применяются после нажатия **Сохранить** в соответствующем блоке.")

    cfg = repository.load_capacity_config(conn)
    df_roles = repository.load_roles(conn)
    placeholders = repository.get_date_placeholders(conn)
    active_statuses = repository.get_active_statuses(conn)
    gantt_statuses = repository.get_gantt_active_statuses(conn)
    annual_vacation = repository.get_config(conn, 'annual_vacation_days', app_config.ANNUAL_VACATION_DAYS_DEFAULT)
    try:
        annual_vacation = int(float(annual_vacation)) if annual_vacation not in (None, '') else app_config.ANNUAL_VACATION_DAYS_DEFAULT
    except (ValueError, TypeError):
        annual_vacation = app_config.ANNUAL_VACATION_DAYS_DEFAULT

    # ----- Блок: Параметры формулы ёмкости и роли -----
    with st.expander("📐 Параметры формулы ёмкости и привязка ролей", expanded=True):
        st.markdown("Параметры расчёта **годовой ёмкости проектов** и привязка ролей к формуле (n_junior / n_senior).")
        with st.form(key="config_capacity_form"):
            st.subheader("Параметры формулы")
            c1, c2 = st.columns(2)
            with c1:
                annual_working_days = st.number_input(
                    "Рабочих дней в году (D)",
                    min_value=1,
                    max_value=366,
                    value=cfg['annual_working_days'],
                    step=1,
                    help="Эффективный фонд F = D − V. V считается по таблице отпусков (среднее на сотрудника за год)."
                )
                typical_project_days = st.number_input(
                    "Типовая длительность проекта, дней (T)",
                    min_value=1,
                    max_value=365,
                    value=cfg['typical_project_days'],
                    step=1,
                )
            with c2:
                typical_lead_share = st.number_input(
                    "Доля старшего на проект (x)",
                    min_value=0.01,
                    max_value=1.0,
                    value=float(cfg['typical_lead_share']),
                    step=0.05,
                    format="%.2f",
                    help="0.25 = 25% загрузки ведущего на проект."
                )
                max_concurrent_projects = st.number_input(
                    "Макс. одновременных проектов",
                    min_value=1,
                    max_value=20,
                    value=cfg['max_concurrent_projects'],
                    step=1,
                )

            st.subheader("Привязка ролей к расчёту ёмкости")
            st.caption("Выберите роли для подсчёта **младших** (n_junior) и **старших** (n_senior). Если ни одна не выбрана — используются имена «Junior» и «Senior».")

            role_ids = df_roles['id'].astype(int).tolist() if not df_roles.empty else []
            role_id_to_name = df_roles.set_index('id')['name'].to_dict() if not df_roles.empty else {}

            col_j, col_s = st.columns(2)
            with col_j:
                default_junior = [rid for rid in cfg['capacity_role_junior_ids'] if rid in role_ids]
                role_junior_selected = st.multiselect(
                    "Роли для n_junior",
                    options=role_ids,
                    default=default_junior,
                    format_func=lambda rid: role_id_to_name.get(rid, f"ID {rid}"),
                    key="config_roles_junior",
                )
            with col_s:
                default_senior = [rid for rid in cfg['capacity_role_senior_ids'] if rid in role_ids]
                role_senior_selected = st.multiselect(
                    "Роли для n_senior",
                    options=role_ids,
                    default=default_senior,
                    format_func=lambda rid: role_id_to_name.get(rid, f"ID {rid}"),
                    key="config_roles_senior",
                )

            if st.form_submit_button("Сохранить ёмкость и роли"):
                repository.set_config(conn, 'annual_working_days', annual_working_days)
                repository.set_config(conn, 'typical_project_days', typical_project_days)
                repository.set_config(conn, 'typical_lead_share', typical_lead_share)
                repository.set_config(conn, 'max_concurrent_projects', max_concurrent_projects)
                repository.set_config(conn, 'capacity_role_junior_ids', ','.join(str(x) for x in role_junior_selected))
                repository.set_config(conn, 'capacity_role_senior_ids', ','.join(str(x) for x in role_senior_selected))
                st.cache_data.clear()
                st.success("Параметры ёмкости и ролей сохранены.")
                st.rerun()

    # ----- Блок: Отпуска -----
    with st.expander("🏖️ Отпуска по умолчанию"):
        st.markdown("Число **рабочих дней отпуска в году по умолчанию**, если в системе ещё нет записей об отпусках (для расчёта эффективного фонда).")
        with st.form(key="config_vacation_form"):
            annual_vacation_days = st.number_input(
                "Годовой отпуск по умолчанию, рабочих дней",
                min_value=0,
                max_value=365,
                value=annual_vacation,
                step=1,
                key="config_annual_vacation",
            )
            if st.form_submit_button("Сохранить отпуска"):
                repository.set_config(conn, 'annual_vacation_days', annual_vacation_days)
                st.cache_data.clear()
                st.success("Сохранено.")
                st.rerun()

    # ----- Блок: Импорт и даты -----
    with st.expander("📅 Плейсхолдеры дат (импорт и невалидные даты)"):
        st.markdown("Даты, подставляемые при **импорте** или при **невалидных/пустых датах** проекта. Формат: `YYYY-MM-DD`.")
        with st.form(key="config_placeholders_form"):
            ph_start = st.text_input(
                "Дата начала по умолчанию",
                value=placeholders[0],
                key="config_ph_start",
                placeholder="1970-01-01",
            )
            ph_end = st.text_input(
                "Дата окончания по умолчанию",
                value=placeholders[1],
                key="config_ph_end",
                placeholder="2099-12-31",
            )
            if st.form_submit_button("Сохранить плейсхолдеры"):
                ok_start, val_start = _parse_iso_date(ph_start)
                ok_end, val_end = _parse_iso_date(ph_end)
                if not ok_start:
                    msg_start = "Неверный формат даты начала. Используйте YYYY-MM-DD."
                    log_user_facing_error(logging.WARNING, msg_start)
                    st.error(msg_start)
                elif not ok_end:
                    msg_end = "Неверный формат даты окончания. Используйте YYYY-MM-DD."
                    log_user_facing_error(logging.WARNING, msg_end)
                    st.error(msg_end)
                else:
                    repository.set_config(conn, 'date_placeholder_start', val_start)
                    repository.set_config(conn, 'date_placeholder_end', val_end)
                    st.cache_data.clear()
                    st.success("Плейсхолдеры сохранены.")
                    st.rerun()

    # ----- Блок: Статусы проектов -----
    with st.expander("📌 Статусы проектов"):
        st.markdown("**Учитывать в отчётах и ёмкости** — проекты с отмеченным статусом входят в отчёты и расчёт годовой ёмкости. **Показывать в фильтре Ганта «Только активные»** — какие статусы отображать при включённом фильтре на диаграмме Ганта. Настройка в таблице справочника ниже.")
        df_statuses = repository.load_project_statuses(conn)
        if df_statuses.empty:
            st.caption("Справочник статусов пуст. Он заполняется при первом запуске миграций.")
        else:
            with st.form(key="config_statuses_form"):
                updates = []
                for _, row in df_statuses.iterrows():
                    sid = row['id']
                    name = row['name']
                    code = row['code']
                    is_active = bool(row.get('is_active', False))
                    is_gantt = bool(row.get('is_gantt_active', False))
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        st.write(f"**{name}** ({code})")
                    with c2:
                        chk_active = st.checkbox("В отчётах/ёмкости", value=is_active, key=f"config_status_active_{sid}")
                    with c3:
                        chk_gantt = st.checkbox("В фильтре Ганта", value=is_gantt, key=f"config_status_gantt_{sid}")
                    updates.append((sid, chk_active, chk_gantt))
                if st.form_submit_button("Сохранить статусы"):
                    for sid, is_active, is_gantt in updates:
                        repository.update_project_status_flags(conn, sid, is_active, is_gantt)
                    st.cache_data.clear()
                    st.success("Статусы сохранены.")
                    st.rerun()
            st.caption("Текущие активные (отчёты/ёмкость): " + ", ".join(active_statuses) + ". Для Ганта: " + ", ".join(gantt_statuses))

    # ----- Блок: О системе -----
    with st.expander("ℹ️ О системе"):
        _year = date.today().year
        v_computed = load_calculator.get_average_vacation_days_per_employee(conn, _year)
        st.markdown("**Путь к БД:** задаётся переменной окружения `PLANNER_DB_PATH` или по умолчанию `resource_planner.db`. Текущее значение (только для справки):")
        st.code(app_config.DB_PATH, language=None)
        st.markdown("**Текущие значения конфигурации (ёмкость и отпуск):**")
        cur = repository.load_capacity_config(conn)
        st.json({
            'annual_working_days': cur['annual_working_days'],
            'annual_vacation_days_V': f"{v_computed} (расчётное по отпускам за {_year} г.)",
            'typical_project_days': cur['typical_project_days'],
            'typical_lead_share': cur['typical_lead_share'],
            'max_concurrent_projects': cur['max_concurrent_projects'],
            'capacity_role_junior_ids': cur['capacity_role_junior_ids'],
            'capacity_role_senior_ids': cur['capacity_role_senior_ids'],
            'date_placeholder_start': repository.get_config(conn, 'date_placeholder_start', ''),
            'date_placeholder_end': repository.get_config(conn, 'date_placeholder_end', ''),
            'active_statuses': ', '.join(repository.get_active_statuses(conn)),
            'gantt_active_statuses': ', '.join(repository.get_gantt_active_statuses(conn)),
        })
