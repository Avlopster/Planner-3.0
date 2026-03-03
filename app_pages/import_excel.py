# -*- coding: utf-8 -*-
"""Страница «Импорт из Excel»: вкладки по сущностям, шаблоны, загрузка файлов."""
import logging
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

import excel_import_ui
import msproject_import
import repository
from utils.app_logging import get_actions_logger, log_user_facing_error, record_error

actions_log = get_actions_logger()


def render(conn):
    st.header("📥 Импорт данных из Excel")
    st.markdown("Загрузите файл Excel с листами, содержащими данные для импорта. Доступны шаблоны.")

    tabs = st.tabs([
        "Сотрудники", "Отпуска", "Проекты", "Рядовые", "Этапы", "Назначения на этапы",
        "MS Project (XML)",
    ])

    with tabs[0]:
        st.subheader("Импорт сотрудников")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Колонки:** ФИО, Роль")
        with col2:
            template = excel_import_ui.download_template('employees')
            st.download_button("📎 Шаблон", data=template.getvalue(), file_name="template_employees.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        uploaded = st.file_uploader("Выберите файл", type=['xlsx'], key="emp_upload")
        emp_df = None
        if uploaded:
            try:
                emp_df = pd.read_excel(uploaded, sheet_name='Сотрудники')
                if all(c in emp_df.columns for c in ['ФИО', 'Роль']):
                    st.session_state['import_employees_df'] = emp_df
                else:
                    msg = "Неверные колонки"
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            except Exception as e:
                record_error(e, user_message=f"Ошибка: {e}")
                st.error(f"Ошибка: {e}")
        emp_df = emp_df if emp_df is not None else st.session_state.get('import_employees_df')
        if emp_df is not None:
            if st.button("Импортировать", key="import_employees_btn"):
                succ, err = excel_import_ui.import_employees(conn, emp_df)
                actions_log.info("Импорт сотрудников: импортировано %s", succ)
                st.success(f"Импортировано: {succ}")
                if err:
                    err_txt = "\n".join(err)
                    log_user_facing_error(logging.ERROR, err_txt)
                    st.error(err_txt)
                st.cache_data.clear()
                if 'import_employees_df' in st.session_state:
                    del st.session_state['import_employees_df']
                st.rerun()

    with tabs[1]:
        st.subheader("Импорт отпусков")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Колонки:** Сотрудник, Дата начала, Дата окончания")
        with col2:
            template = excel_import_ui.download_template('vacations')
            st.download_button("📎 Шаблон", data=template.getvalue(), file_name="template_vacations.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        uploaded = st.file_uploader("Выберите файл", type=['xlsx'], key="vac_upload")
        vac_df = None
        if uploaded:
            try:
                vac_df = pd.read_excel(uploaded, sheet_name='Отпуска')
                if all(c in vac_df.columns for c in ['Сотрудник', 'Дата начала', 'Дата окончания']):
                    st.session_state['import_vacations_df'] = vac_df
                else:
                    msg = "Неверные колонки"
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            except Exception as e:
                record_error(e, user_message=f"Ошибка: {e}")
                st.error(f"Ошибка: {e}")
        vac_df = vac_df if vac_df is not None else st.session_state.get('import_vacations_df')
        if vac_df is not None:
            if st.button("Импортировать", key="import_vacations_btn"):
                succ, err = excel_import_ui.import_vacations(conn, vac_df)
                actions_log.info("Импорт отпусков: импортировано %s", succ)
                st.success(f"Импортировано: {succ}")
                if err:
                    err_txt = "\n".join(err)
                    log_user_facing_error(logging.ERROR, err_txt)
                    st.error(err_txt)
                st.cache_data.clear()
                if 'import_vacations_df' in st.session_state:
                    del st.session_state['import_vacations_df']
                st.rerun()

    with tabs[2]:
        st.subheader("Импорт проектов")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Колонки:** Название проекта, Компания клиента, Ведущий, Загрузка ведущего %, Дата начала, Дата окончания, Автоопределение дат")
        with col2:
            template = excel_import_ui.download_template('projects')
            st.download_button("📎 Шаблон", data=template.getvalue(), file_name="template_projects.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        uploaded = st.file_uploader("Выберите файл", type=['xlsx'], key="proj_upload")
        proj_df = None
        if uploaded:
            try:
                proj_df = pd.read_excel(uploaded, sheet_name='Проекты')
                required = ['Название проекта', 'Ведущий']
                if all(c in proj_df.columns for c in required):
                    st.session_state['import_projects_df'] = proj_df
                else:
                    msg = "Неверные колонки"
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            except Exception as e:
                record_error(e, user_message=f"Ошибка: {e}")
                st.error(f"Ошибка: {e}")
        proj_df = proj_df if proj_df is not None else st.session_state.get('import_projects_df')
        if proj_df is not None:
            if st.button("Импортировать", key="import_projects_btn"):
                succ, err = excel_import_ui.import_projects(conn, proj_df)
                actions_log.info("Импорт проектов: импортировано %s", succ)
                st.success(f"Импортировано: {succ}")
                if err:
                    err_txt = "\n".join(err)
                    log_user_facing_error(logging.ERROR, err_txt)
                    st.error(err_txt)
                st.cache_data.clear()
                if 'import_projects_df' in st.session_state:
                    del st.session_state['import_projects_df']
                st.rerun()

    with tabs[3]:
        st.subheader("Импорт рядовых")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Колонки:** Проект, Сотрудник, Загрузка %")
        with col2:
            template = excel_import_ui.download_template('juniors')
            st.download_button("📎 Шаблон", data=template.getvalue(), file_name="template_juniors.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        uploaded = st.file_uploader("Выберите файл", type=['xlsx'], key="jun_upload")
        jun_df = None
        if uploaded:
            try:
                jun_df = pd.read_excel(uploaded, sheet_name='Рядовые')
                if all(c in jun_df.columns for c in ['Проект', 'Сотрудник', 'Загрузка %']):
                    st.session_state['import_juniors_df'] = jun_df
                else:
                    msg = "Неверные колонки"
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            except Exception as e:
                record_error(e, user_message=f"Ошибка: {e}")
                st.error(f"Ошибка: {e}")
        jun_df = jun_df if jun_df is not None else st.session_state.get('import_juniors_df')
        if jun_df is not None:
            if st.button("Импортировать", key="import_juniors_btn"):
                succ, err = excel_import_ui.import_juniors(conn, jun_df)
                actions_log.info("Импорт рядовых: импортировано %s", succ)
                st.success(f"Импортировано: {succ}")
                if err:
                    err_txt = "\n".join(err)
                    log_user_facing_error(logging.ERROR, err_txt)
                    st.error(err_txt)
                st.cache_data.clear()
                if 'import_juniors_df' in st.session_state:
                    del st.session_state['import_juniors_df']
                st.rerun()

    with tabs[4]:
        st.subheader("Импорт этапов")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Колонки:** Проект, Название этапа, Тип этапа, Дата начала, Дата окончания")
        with col2:
            template = excel_import_ui.download_template('phases')
            st.download_button("📎 Шаблон", data=template.getvalue(), file_name="template_phases.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        uploaded = st.file_uploader("Выберите файл", type=['xlsx'], key="phase_upload")
        phase_df = None
        if uploaded:
            try:
                phase_df = pd.read_excel(uploaded, sheet_name='Этапы')
                if all(c in phase_df.columns for c in ['Проект', 'Название этапа', 'Тип этапа', 'Дата начала', 'Дата окончания']):
                    st.session_state['import_phases_df'] = phase_df
                else:
                    msg = "Неверные колонки"
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            except Exception as e:
                record_error(e, user_message=f"Ошибка: {e}")
                st.error(f"Ошибка: {e}")
        phase_df = phase_df if phase_df is not None else st.session_state.get('import_phases_df')
        if phase_df is not None:
            if st.button("Импортировать", key="import_phases_btn"):
                def _update_dates(proj_id):
                    st.cache_data.clear()
                    repository.update_project_dates_from_phases(conn, proj_id)
                succ, err = excel_import_ui.import_phases(conn, phase_df, _update_dates)
                actions_log.info("Импорт этапов: импортировано %s", succ)
                st.success(f"Импортировано: {succ}")
                if err:
                    err_txt = "\n".join(err)
                    log_user_facing_error(logging.ERROR, err_txt)
                    st.error(err_txt)
                st.cache_data.clear()
                if 'import_phases_df' in st.session_state:
                    del st.session_state['import_phases_df']
                st.rerun()

    with tabs[5]:
        st.subheader("Импорт назначений на этапы")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Колонки:** Проект, Название этапа, Сотрудник, Загрузка %")
        with col2:
            template = excel_import_ui.download_template('phase_assignments')
            st.download_button("📎 Шаблон", data=template.getvalue(), file_name="template_phase_assignments.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="phase_assign_tpl")
        uploaded = st.file_uploader("Выберите файл", type=['xlsx'], key="phase_assign_upload")
        phase_assign_df = None
        if uploaded:
            try:
                phase_assign_df = pd.read_excel(uploaded, sheet_name='Назначения на этапы')
                required = ['Проект', 'Название этапа', 'Сотрудник', 'Загрузка %']
                if all(c in phase_assign_df.columns for c in required):
                    st.session_state['import_phase_assignments_df'] = phase_assign_df
                else:
                    msg = "Неверные колонки. Требуются: Проект, Название этапа, Сотрудник, Загрузка %"
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            except Exception as e:
                record_error(e, user_message=f"Ошибка: {e}")
                st.error(f"Ошибка: {e}")
        phase_assign_df = phase_assign_df if phase_assign_df is not None else st.session_state.get('import_phase_assignments_df')
        if phase_assign_df is not None:
            if st.button("Импортировать", key="phase_assign_import_btn"):
                succ, err = excel_import_ui.import_phase_assignments(conn, phase_assign_df)
                actions_log.info("Импорт назначений на этапы: импортировано %s", succ)
                st.success(f"Импортировано: {succ}")
                if err:
                    err_txt = "\n".join(err)
                    log_user_facing_error(logging.ERROR, err_txt)
                    st.error(err_txt)
                st.cache_data.clear()
                if 'import_phase_assignments_df' in st.session_state:
                    del st.session_state['import_phase_assignments_df']
                st.rerun()

    with tabs[6]:
        st.subheader("Импорт из MS Project (XML)")
        st.markdown("Загрузите файл XML, экспортированный из Microsoft Project (формат обмена MSPDI). Будет создан один проект, его этапы и назначения ресурсов.")
        only_leaf = st.checkbox(
            "Импортировать только листовые задачи (Summary=0)",
            value=False,
            key="mspdi_only_leaf",
        )
        uploaded = st.file_uploader("Выберите файл XML", type=["xml"], key="mspdi_upload")
        root = None
        if uploaded:
            try:
                root = ET.fromstring(uploaded.getvalue())
            except ET.ParseError as e:
                msg_xml = f"Ошибка разбора XML: {e}"
                log_user_facing_error(logging.ERROR, msg_xml, exc=e)
                st.error(msg_xml)
            except Exception as e:
                msg_read = f"Ошибка чтения файла: {e}"
                record_error(e, user_message=msg_read)
                st.error(msg_read)

        if root is not None:
            try:
                project_dict, phases_list = msproject_import.build_project_and_phases_from_mspdi(root, only_leaf)
                st.markdown("**Предпросмотр**")
                st.write("**Проект:**", project_dict.get("name", "—"))
                st.write("**Даты:**", project_dict.get("start_date", "—"), "—", project_dict.get("finish_date", "—"))
                if phases_list:
                    preview_df = pd.DataFrame(phases_list).rename(columns={
                        "name": "Название этапа",
                        "start_date": "Дата начала",
                        "end_date": "Дата окончания",
                        "completion_percent": "% выполнения",
                    })
                    st.dataframe(
                        preview_df[["Название этапа", "Дата начала", "Дата окончания", "% выполнения"]],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.info("Нет этапов для импорта (проверьте фильтр «только листовые» или структуру файла).")

                if st.button("Импортировать", key="mspdi_import_btn"):
                    project_id, phases_count, err_phases = msproject_import.import_mspdi_project_and_phases(
                        conn, root, only_leaf_tasks=only_leaf
                    )
                    if project_id is None:
                        log_user_facing_error(logging.ERROR, "Не удалось создать проект.")
                        st.error("Не удалось создать проект.")
                        for msg in err_phases:
                            log_user_facing_error(logging.ERROR, msg)
                            st.error(msg)
                    else:
                        actions_log.info("Импорт MS Project: проект id=%s, этапов %s", project_id, phases_count)
                        st.success(f"Проект создан (id={project_id}), этапов: {phases_count}.")
                        for msg in err_phases:
                            log_user_facing_error(logging.WARNING, msg)
                            st.warning(msg)
                        assign_count, err_assign = msproject_import.import_mspdi_assignments(
                            conn, root, project_id, only_leaf_tasks=only_leaf
                        )
                        st.success(f"Назначений на этапы: {assign_count}.")
                        for msg in err_assign:
                            log_user_facing_error(logging.WARNING, msg)
                            st.warning(msg)
                        st.cache_data.clear()
                        st.rerun()
            except Exception as e:
                msg_parse = f"Ошибка при разборе данных: {e}"
                record_error(e, user_message=msg_parse)
                st.error(msg_parse)
