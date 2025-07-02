import re
import streamlit as st
import requests
from functions import canvas_request, format_rut, parse_course_ids, clean_string
from config import HEADERS
import pandas as pd
import io
import math
from concurrent.futures import ThreadPoolExecutor
import time
import os

# Configuración general
st.set_page_config(page_title="Diplomado Director ACT Generator", layout="wide", page_icon="🛰️")
st.title("Diplomado Director ACT Generator 🛰️")
st.info("Ingresa los 5 IDs de cursos en orden de dictación (c1, c2, c3, c4, c5). Se calcularán promedios, estado final y tareas pendientes.")

session = requests.Session()
session.headers.update(HEADERS)

NUM_COLS = [f"C{i}" for i in range(1, 6)] + ["Promedio"]


def color_estado(val):
    if val == "Aprobado":
        return "color: lightgreen"
    elif val == "Reprobado":
        return "color: salmon"
    elif val == "Pendiente":
        return "color: orange"
    elif val in ("Sin calcular", "No existe", "Regularizar"):
        return "color: red"
    try:
        num = float(val)
    except:
        return ""
    return "color: salmon" if num < 4.0 else ""

def obtener_info_curso(course_id):
    alumnos = {}
    tareas_pendientes = {}

    enrolls = canvas_request(session, "get", f"/courses/{course_id}/enrollments", payload={"type[]": "StudentEnrollment", "state[]": "active", "per_page": 100}, paginated=True) or []

    for e in enrolls:
        if e.get("type") != "StudentEnrollment":
            continue
        sis_id = e.get("sis_user_id")
        sortable = e["user"].get("sortable_name", "")
        login_id = e["user"].get("login_id", "")
        apellido, nombre = [p.strip() for p in sortable.split(",", 1)] if "," in sortable else ("", "")
        try:
            final = float(e["grades"].get("final_grade"))
        except:
            final = None
        try:
            current = float(e["grades"].get("current_grade"))
        except:
            current = None
            
        alumnos[sis_id] = {
            "first": nombre,
            "last": apellido,
            "final": final,
            "current": current,
            "email": login_id
        }

    students = canvas_request(session, 'get', f'/courses/{course_id}/users', payload={'enrollment_type[]': 'student'}, paginated=True) or []
    student_ids = {s['id']: s.get('sis_user_id') for s in students if s.get('sis_user_id')}
    assignments = canvas_request(session, 'get', f'/courses/{course_id}/assignments', paginated=True) or []

    for assn in assignments:
        if (not assn.get("points_possible") or assn.get("points_possible") == 0 or assn.get("grading_type") == "not_graded" or assn.get("grading_type") == "pass_fail"):
            continue
        if clean_string("Autoevaluación") in clean_string(assn.get("name", "").lower()):
            continue
        assn_id = assn.get('id')
        submissions = canvas_request(session, 'get', f'/courses/{course_id}/assignments/{assn_id}/submissions', paginated=True) or []

        for sub in submissions:
            uid = sub.get('user_id')
            if uid not in student_ids:
                continue

            sis_id = student_ids[uid]
            score = sub.get("score")
            matched_grade = sub.get("grade_matches_current_submission")
            #excused = sub.get("excused", False) SACADO PORQUE NO SE ACEPTAN JUSTIFICACIONES

            if score is None or not matched_grade: #and not excused:
                tareas_pendientes.setdefault(sis_id, []).append(assn.get("name"))

    return course_id, alumnos, tareas_pendientes

def obtener_info_curso_basica(cid):
    try:
        info = canvas_request(session, "get", f"/courses/{cid}")
        if info:
            return {
                "id":            info["id"],
                "account_id":    info["account_id"],
                "name":          info["name"],
                "course_code":   info["course_code"],
                "sis_course_id": info["sis_course_id"],
            }
        else:
            return None
    except Exception:
        return None

#INTERFAZ
curso_input = st.text_area("IDs de cursos (separados por coma, espacio o salto de línea):", height=100)
curso_ids = parse_course_ids(curso_input)[:5]

if st.button("Obtener datos!", use_container_width=True):
    st.session_state["start_time"] = time.time()
    if len(curso_ids) != 5:
        st.error("Debes ingresar exactamente 5 IDs de curso.")
        st.stop()
    
        # Obtener metadatos de cursos en paralelo
    with ThreadPoolExecutor(max_workers=5) as executor:
        cursos_basicos = list(executor.map(obtener_info_curso_basica, curso_ids))

    courses_info = []
    invalid_ids = []
    for idx, result in enumerate(cursos_basicos):
        if result:
            courses_info.append(result)
        else:
            invalid_ids.append(curso_ids[idx])

    if invalid_ids:
        st.error(f"❌ IDs inválidos: {invalid_ids}")
        st.stop()

    # Validar diplomado por firma
    firmas = {
        re.sub(r"-C\d+-", "-CX-", c["sis_course_id"])
        for c in courses_info
    }
    if len(firmas) != 1:
        st.error(f"❌ Cursos de diplomados distintos: {firmas}")
        st.stop()
        
    course_type = next(iter(firmas))
    course_initial = course_type.split("-")
    if course_initial[1][0] != "D":
        st.error(f"❌ {firmas}: Los cursos no pertenecen a un Diplomado, usa la version correcta. Si crees que hay un error contacta a soport (instruccional2.die@uautonoma.cl)")
        st.stop()
        
    firma = firmas.pop()
    st.success(f"✅ Diplomado validado: {firma}")
    account_name = canvas_request(session, "get", f"/accounts/{cursos_basicos[0].get('account_id')}")
    curso_nombres = "\n".join([f"- {curso.get('name')}" for curso in cursos_basicos])
    st.info(f"{account_name.get('name')} \n{curso_nombres}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        resultados = list(executor.map(obtener_info_curso, curso_ids))

    alumnos = {}
    tareas_pendientes_all = {}
    for idx, (cid, datos, pendientes) in enumerate(resultados, start=1):
        col = f"C{idx}"
        for sis, datos_alumno in datos.items():
            if sis not in alumnos:
                alumnos[sis] = {
                    "first": datos_alumno["first"],
                    "last": datos_alumno["last"],
                    "grades": {},
                    "email": datos_alumno["email"]
                }
            alumnos[sis]["grades"][col] = {
                "final": datos_alumno["final"],
                "current": datos_alumno["current"]
            }
        for sis, tareas in pendientes.items():
            if sis not in tareas_pendientes_all:
                tareas_pendientes_all[sis] = {}
            tareas_pendientes_all[sis][col] = tareas

    filas = []
    for sis, info in alumnos.items():
        row = {
            "Nombre": info["first"],
            "Apellido": info["last"],
            "RUT": format_rut(sis)
        }
        notas = []
        pendiente = False
        reprobados = 0

        for i in range(1, 6):
            key = f"C{i}"
            if key not in info["grades"]:
                row[key] = "No existe"
                continue
            gd = info["grades"][key]
            final = gd.get("final")
            current = gd.get("current")
            if tareas_pendientes_all.get(sis, {}).get(key):
                row[key] = "Pendiente"
                pendiente = True
            elif final is not None and current is not None and final != current:
                row[key] = "Pendiente"
                pendiente = True
            else:
                if final is not None:
                    row[key] = final
                    notas.append(final)
                    if final < 4.0:
                        reprobados += 1
                else:
                    row[key] = 0

        if notas:
            avg = sum(notas) / len(notas)
            prom = math.floor(avg * 10 + 0.5) / 10
            row["Promedio"] = prom
        else:
            row["Promedio"] = "Sin calcular"

        missing = sum(1 for i in range(1, 6) if row[f"C{i}"] == "No existe")
        if pendiente:
            row["Estado"] = "Pendiente"
        elif missing > 0:
            row["Estado"] = "Regularizar"
        elif row["Promedio"] == "Sin calcular":
            row["Estado"] = "Sin notas"
        elif reprobados > 0:
            row["Estado"] = "Reprobado"
        else:
            row["Estado"] = "Aprobado"

        if row["Estado"] == "Regularizar":
            row["Observaciones"] = "Regularizar"
        elif reprobados == 1:
            row["Observaciones"] = "Accede a remedial"
        else:
            row["Observaciones"] = ""
        row["Email"] = info["email"]
        filas.append(row)

    # Mostrar tabla
    df = pd.DataFrame(filas)
    for col in NUM_COLS:
        df[col] = df[col].apply(
            lambda v: (
                v if v in ("Pendiente", "Sin calcular", "No existe")
                else f"{v:.1f}" if isinstance(v, (int, float))
                else ""
            )
        )
    df = df.astype(str)

    def parse_cell(v):
        if v in ("Pendiente", "No existe", "Sin calcular", ""):
            return v
        try:
            return float(v.replace(",", "."))
        except:
            return v

    df_export = df.copy()
    for col in NUM_COLS:
        df_export[col] = df[col].apply(parse_cell)
    
    code = courses_info[0].get('course_code').split('-')

    st.session_state["df"] = df
    st.session_state["df_export"] = df_export
    st.session_state["filename"] = f"{account_name.get('name')}-{code[1]}.xlsx"
    st.session_state["tareas_pendientes_all"] = tareas_pendientes_all


if "df" in st.session_state:
    df = st.session_state["df"]
    df_styled = (
        df.style
          .map(color_estado, subset=[*NUM_COLS, "Estado"])
          .set_properties(**{"text-align": "right"})
    )
    st.dataframe(df_styled, use_container_width=True)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        st.session_state["df_export"].to_excel(
            writer, index=False, sheet_name="Actas"
        )
        ws = writer.sheets["Actas"]
        fmt = writer.book.add_format({"num_format": "0.0"})
        ws.set_column("D:I", None, fmt)
    buffer.seek(0)
    st.download_button(
        label="📥 Descargar en Excel",
        data=buffer,
        file_name=st.session_state["filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    if "start_time" in st.session_state:
        end_time = time.time()
        duration = end_time - st.session_state["start_time"]
        st.success(f"Tarea completada en {duration:.2f} segundos.")
        del st.session_state["start_time"]