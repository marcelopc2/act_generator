import re
import streamlit as st
import requests
from functions import canvas_request, format_rut
from config import HEADERS
import pandas as pd

st.set_page_config(page_title="Director ACT Generator", page_icon="👮‍♂️", layout="wide")
st.title("Director ACT Generator 👮‍♂️")
st.write("Generador de actas para los directores de diplomados. Ingresa los IDs de los cursos en orden (c1, c2, c3, c4, c5) y has clic en el boton Obtener Datos.")

session = requests.Session()
session.headers.update(HEADERS)

def color_estado(val):
    if val == "Aprobado":
        return "color: lightgreen"
    elif val == "Reprobado":
        return "color: salmon"
    return ""

def color_nota(val):
    if val < 4:
        return "color: salmon"
    return ""

# 1) Input de los 5 IDs de curso
curso_input = st.text_area(
    "Ingresa los 5 IDs de cursos en orden de dictación:",
    height=100
)
# Parseo y limpieza
curso_ids = [c for c in re.split(r"[,\s]+", curso_input.strip()) if c]

if st.button("Obtener Datos"):
    if len(curso_ids) != 5:
        st.error("Debes ingresar exactamente 5 IDs de curso.")
    else:
        # 2) Función helper para obtener {sis_user_id: {first, last, final_grade}}
        def obtener_notas_finales(session, course_id):
            params = {
                "type[]": "StudentEnrollment",
                "state[]": "active",
                "per_page": 100
            }
            # NOTA: usamos endpoint SIN /api/v1 porque BASE_URL ya lo incluye
            enrolls = canvas_request(
                session, "get",
                f"/courses/{course_id}/enrollments",
                payload=params,
                paginated=True
            )
            resultado = {}
            if not enrolls:
                return resultado
            for e in enrolls:
                if e.get("type") != "StudentEnrollment":
                    continue
                sis_id = e.get("sis_user_id")
                sortable = e.get("user").get("sortable_name","")
                login_id   = e.get("user").get("login_id")
                # separa "Apellido, Nombre"
                partes = [p.strip() for p in sortable.split(",",1)]
                apellido = partes[0] if len(partes)>0 else ""
                nombre   = partes[1] if len(partes)>1 else ""
                final_grade = float(e.get("grades",{}).get("final_grade"))
                resultado[sis_id] = {
                    "first": nombre,
                    "last":  apellido,
                    "grade": final_grade,
                    "email": login_id
                }
            return resultado

        # 3) Recolectar datos de los 5 cursos
        alumnos = {}  # sis_id → {"first","last","grades":{idx:grade}}
        for idx, cid in enumerate(curso_ids, start=1):
            notas_curso = obtener_notas_finales(session, cid)
            for sis, info in notas_curso.items():
                if sis not in alumnos:
                    alumnos[sis] = {
                        "first": info["first"],
                        "last":  info["last"],
                        "grades": {},
                        "email":  info["email"]
                    }
                alumnos[sis]["grades"][f"C{idx}"] = info["grade"]

        # 4) Construir lista de filas con promedio
        filas = []
        for sis, info in alumnos.items():
            row = {
                "Nombre":    info["first"],
                "Apellido":  info["last"],
                "RUT":       format_rut(sis)
            }
            # agregar cada nota de curso
            grades = []
            for i in range(1,6):
                campo = f"C{i}"
                val = info["grades"].get(campo) or 0
                row[campo] = val
                if isinstance(val,(int,float)):
                    grades.append(val)
            # promedio numérico (None si no hay notas)
            row["Promedio"] = round(sum(grades)/len(grades),1) if grades else None
            row["Estado"] = (
                "Sin notas" if row["Promedio"] is None else
                "Aprobado" if row["Promedio"] >= 4 else
                "Reprobado"
            )
            row["Email"] = info["email"]
            filas.append(row)
            
        df = pd.DataFrame(filas)
        float_cols = df.select_dtypes(include="float").columns
        fmt = {col: "{:.1f}" for col in float_cols}
        df_styled = (
            df.style
            .map(color_estado, subset=["Estado"]).map(color_nota, subset=["C1", "C2", "C3", "C4", "C5"])
            .format(fmt)
        )
        st.dataframe(df_styled, use_container_width=True, hide_index=False)
