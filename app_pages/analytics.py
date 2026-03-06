# -*- coding: utf-8 -*-
"""Страница «Аналитика»: загрузка по отделам, по сотрудникам, перегрузки, экспорт в Excel."""
import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import config as app_config  # по контракту; в аналитике не используется (ACTIVE_STATUSES — в Ганте)
import capacity as capacity_module
import capacity_ui
import components
import load_calculator
import repository
from utils.chart_theme import COLOR_PALETTE, apply_chart_theme, apply_weekly_date_axis
from components import page_header


def _on_analytics_export():
    st.session_state["_analytics_export_done"] = True


def render(conn):
    """Отрисовка страницы «Аналитика»: загрузка по отделам, перегрузки, экспорт. conn — подключение к БД."""
    page_header("📈", "Аналитика загрузки")
    df_emp = repository.load_employees(conn)
    if df_emp.empty:
        st.warning("Нет данных о сотрудниках.")
    else:
        if st.session_state.get("_analytics_export_done"):
            st.toast("Отчёт сохранён")
            del st.session_state["_analytics_export_done"]

        with st.container():
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.markdown("**Начало периода**")
                start_analytics = components.ru_date_picker("", default=date.today(), key_prefix="analytics_start")
                start_str = start_analytics.isoformat()
            with col2:
                st.markdown("**Конец периода**")
                end_analytics = components.ru_date_picker("", default=date.today() + timedelta(days=90), key_prefix="analytics_end")
                end_str = end_analytics.isoformat()
            with col3:
                st.markdown("**Экспорт**")
                st.write("")

        summary = load_calculator.department_load_summary(conn, start_str, end_str)
        capacity_result = capacity_module.annual_project_capacity(conn)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Всего человеко-дней", f"{summary['total_capacity_days']:.0f}")
        kpi2.metric("Использовано дней", f"{summary['used_days']:.0f}")
        kpi3.metric("Свободно дней", f"{summary['free_days']:.0f}")
        kpi4.metric("Проектов можно взять", f"{capacity_result['projects_possible']}")
        st.caption("Проектов можно взять — по годовой ёмкости (текущий год): макс. проектов в год с учётом состава и активных проектов.")
        _reason = capacity_result.get('capacity_reason', 'ok')
        if _reason == 'no_junior':
            st.error("Для расчёта ёмкости нужны сотрудники с ролями для **технических специалистов**. Назначьте роли в справочнике или настройте привязку ролей в разделе «Конфигурация».")
        elif _reason == 'no_senior':
            st.error("Для расчёта ёмкости нужны сотрудники с ролями для **руководителей**. Назначьте роли в справочнике или настройте привязку ролей в разделе «Конфигурация».")
        elif _reason == 'cycles_zero':
            F_val = capacity_result.get('effective_fund_F', 0)
            T_val = capacity_result.get('typical_days_T', 0)
            st.error(f"Годовая ёмкость нулевая: типовая длительность проекта (**{T_val}** дн.) не помещается в эффективный фонд (**{F_val}** дн.) в году. Уменьшите «Типовую длительность проекта» или увеличьте «Рабочих дней в году» в разделе «Конфигурация».")
        elif capacity_result['missing_employees'] > 0:
            st.error(f"⚠️ Для взятия ещё одного типового проекта не хватает {capacity_result['missing_employees']} сотрудников.")
        shortfall_a = load_calculator.overload_shortfall(conn, start_str, end_str)
        forecast_rows = capacity_ui.build_forecast_table_rows(
            capacity_result, shortfall_a, period_label="выбранном периоде"
        )
        if forecast_rows:
            df_forecast = pd.DataFrame(forecast_rows)
            st.dataframe(df_forecast, column_config={"Блок": st.column_config.TextColumn("Блок", width="medium"), "Содержание": st.column_config.TextColumn("Содержание", width="large")}, hide_index=True)
        overloaded_a = load_calculator.overloaded_employees_in_period(conn, start_str, end_str)
        with st.expander("💡 Подсказка по оптимизации персонала"):
            hint_rows = capacity_ui.build_optimization_hint_rows(
                capacity_result,
                shortfall_a,
                overload_by_employee=overloaded_a,
                period_label="выбранном периоде",
            )
            if hint_rows:
                st.dataframe(
                    pd.DataFrame(hint_rows),
                    column_config={
                        "Блок": st.column_config.TextColumn("Блок", width="medium"),
                        "Содержание": st.column_config.TextColumn("Содержание", width="large"),
                    },
                    hide_index=True,
                )
        cap_j = capacity_result.get('capacity_if_add_1_junior', 0)
        cap_s = capacity_result.get('capacity_if_add_1_senior', 0)
        N_active_a = capacity_result.get('N_active', 0)
        poss_a = capacity_result.get('projects_possible', 0)
        extra_if_1_junior_a = max(0, cap_j - N_active_a) - poss_a
        extra_if_1_senior_a = max(0, cap_s - N_active_a) - poss_a
        with st.expander("📋 Прогноз: если добавить сотрудников"):
            st.caption("С учётом уже запланированных проектов в году.")
            if extra_if_1_junior_a > 0 or extra_if_1_senior_a > 0:
                if extra_if_1_junior_a > 0:
                    st.markdown(f"- **+1 технический специалист:** ёмкость станет {cap_j}, можно взять ещё **{extra_if_1_junior_a}** проект(ов).")
                if extra_if_1_senior_a > 0:
                    st.markdown(f"- **+1 руководитель:** ёмкость станет {cap_s}, можно взять ещё **{extra_if_1_senior_a}** проект(ов).")
            else:
                limited = capacity_result.get('capacity_limited_by')
                n_j = capacity_result.get('n_junior', 0)
                n_s = capacity_result.get('n_senior', 0)
                P_val = capacity_result.get('P', 0)
                if limited == 'juniors':
                    st.markdown(f"При текущем составе дополнительный набор не увеличит число проектов: **ёмкость ограничена числом технических специалистов** ({n_j}). Добавление руководителя не даст новых проектов, пока не вырастет число технических специалистов.")
                elif limited == 'seniors':
                    st.markdown(f"При текущем составе дополнительный набор не увеличит число проектов: **ёмкость ограничена числом руководителей или лимитом одновременных проектов** ({n_s} руководителей, P = {P_val}). По формуле каждый проект ведёт один ведущий (руководитель); максимум одновременных проектов P = min(лимит, руководители/x). Поэтому **найм технических специалистов не даст новых проектов** — нужны именно руководители.")
                else:
                    st.markdown("При текущем составе дополнительный набор не увеличит число проектов (ёмкость ограничена составом или параметрами формулы).")
        st.divider()

        employee_ids = df_emp['id'].dropna().astype(int).tolist()
        load_batch = load_calculator.employee_load_by_day_batch(conn, employee_ids, start_str, end_str)
        emp_load_data = []
        emp_names = df_emp.set_index('id')['name'].to_dict()
        emp_roles = df_emp.set_index('id')['role_name'].to_dict()
        if not load_batch.empty:
            avg_by_emp = load_batch.groupby('employee_id')['load'].mean()
            for eid in employee_ids:
                avg_load = avg_by_emp.get(eid, 0.0)
                emp_load_data.append({
                    'Сотрудник': emp_names.get(eid, '?'),
                    'Роль': emp_roles.get(eid, '—'),
                    'Средняя загрузка, %': avg_load * 100,
                })
        else:
            for _, emp in df_emp.iterrows():
                emp_load_data.append({'Сотрудник': emp['name'], 'Роль': emp['role_name'], 'Средняя загрузка, %': 0.0})
        df_load = pd.DataFrame(emp_load_data)
        fig = px.bar(df_load, x='Сотрудник', y='Средняя загрузка, %', color='Роль',
                     range_y=[0, 120], title='Средняя загрузка за период',
                     labels={'Сотрудник': 'Сотрудник', 'Средняя загрузка, %': 'Загрузка (%)', 'Роль': 'Роль'},
                     color_discrete_sequence=COLOR_PALETTE)
        apply_chart_theme(fig)

        col_avg_load, col_detail_load = st.columns(2)
        with col_avg_load:
            st.subheader("🔥 Средняя загрузка сотрудников")
            st.plotly_chart(fig, width='stretch')
        with col_detail_load:
            st.subheader("📅 Детальная загрузка сотрудника")
            df_emp_sorted = df_emp.sort_values('name')
            emp_choice = st.selectbox("Выберите сотрудника", df_emp_sorted['id'].tolist(),
                                      format_func=lambda x: f"{df_emp_sorted[df_emp_sorted['id'] == x]['name'].values[0]} ({df_emp_sorted[df_emp_sorted['id'] == x]['role_name'].values[0]})")
            if not load_batch.empty:
                load_detail = load_batch[load_batch['employee_id'] == emp_choice][['date', 'load']].copy()
            else:
                load_detail = load_calculator.employee_load_by_day(conn, emp_choice, start_str, end_str)
            fig2 = px.line(load_detail, x='date', y='load',
                           title='Загрузка по дням',
                           labels={'date': 'Дата', 'load': 'Загрузка (доля ставки)'})
            apply_chart_theme(fig2)
            fig2.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Перегрузка")
            apply_weekly_date_axis(fig2, tickfont_size=10, start_date=start_str, end_date=end_str)
            st.plotly_chart(fig2, width='stretch')
        st.divider()

        st.subheader("⚠️ Дни перегрузки (>100%)")
        overload_report = []
        if not load_batch.empty:
            over_rows = load_batch[load_batch['load'] > 1.0]
        else:
            over_rows = pd.DataFrame()
        for _, row in over_rows.iterrows():
            emp_id = row['employee_id']
            day_d = row['date']
            if hasattr(day_d, 'date'):
                day_d = day_d.date() if callable(getattr(day_d, 'date')) else day_d
            sources = load_calculator.get_employee_load_sources_by_day(conn, emp_id, day_d)
            hint_parts = []
            for s in sources:
                if s.get('phase_name'):
                    hint_parts.append(f"{s['project_name']} (этап «{s['phase_name']}»)")
                else:
                    hint_parts.append(s['project_name'])
            hint = "В этот день загрузка идёт из: " + ", ".join(hint_parts) if hint_parts else ""
            if hint_parts:
                hint += ". Рекомендация: снизить долю в одном из проектов или переназначить этап."
            first_project_id = sources[0]['project_id'] if sources else None
            first_phase_id = sources[0].get('phase_id') if sources else None
            overload_report.append({
                'Сотрудник': emp_names.get(emp_id, '?'),
                'Дата': row['date'].strftime("%d.%m.%Y") if hasattr(row['date'], 'strftime') else str(row['date']),
                'Загрузка': f"{row['load']*100:.0f}%",
                'Подсказка': hint,
                'project_id': first_project_id,
                'phase_id': first_phase_id,
                'employee_id': emp_id
            })
        if overload_report:
            display_overload = pd.DataFrame([{k: v for k, v in r.items() if k in ('Сотрудник', 'Дата', 'Загрузка', 'Подсказка')} for r in overload_report])
            st.dataframe(display_overload, width='stretch')
            seen = set()
            st.markdown("**Перейти к проекту:**")
            for r in overload_report:
                pid = r.get('project_id')
                if pid is not None and (pid not in seen):
                    seen.add(pid)
                    proj_name = repository.get_project_name(conn, pid)
                    if st.button(f"📌 {proj_name}", key=f"goto_proj_overload_{pid}"):
                        st.session_state.menu = "Проекты и этапы"
                        st.session_state.open_project_id = pid
                        st.session_state.open_phase_id = r.get('phase_id')
                        st.rerun()
        else:
            st.success("Перегрузок нет!")

        # Кнопка экспорта в Excel
        df_load_export = df_load.copy()
        overload_df = pd.DataFrame([{k: v for k, v in r.items() if k in ('Сотрудник', 'Дата', 'Загрузка', 'Подсказка')} for r in overload_report]) if overload_report else pd.DataFrame(columns=['Сотрудник', 'Дата', 'Загрузка', 'Подсказка'])
        summary_df = pd.DataFrame({
            'Метрика': ['Всего человеко-дней', 'Использовано дней', 'Свободно дней', 'Проектов можно взять', 'Не хватает сотрудников', 'Не хватает технических специалистов', 'Не хватает руководителей', 'Эквивалент недостающих (перегрузки)'],
            'Значение': [summary['total_capacity_days'], summary['used_days'], summary['free_days'], capacity_result['projects_possible'], capacity_result['missing_employees'], capacity_result.get('missing_juniors', 0), capacity_result.get('missing_seniors', 0), shortfall_a.get('equivalent_missing_fte', 0)]
        })
        excel_out = io.BytesIO()
        with pd.ExcelWriter(excel_out, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='Сводка', index=False)
            df_load_export.to_excel(writer, sheet_name='Загрузка по сотрудникам', index=False)
            overload_df.to_excel(writer, sheet_name='Дни перегрузки', index=False)
        excel_out.seek(0)
        st.download_button("📥 Скачать отчёт (Excel)", data=excel_out, file_name=f"analytics_{start_str}_{end_str}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="analytics_export",
                           on_click=_on_analytics_export)
