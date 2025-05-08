import re
import streamlit as st
import requests
from functions import canvas_request, format_rut
from config import HEADERS
import pandas as pd
import io
import math

st.set_page_config(
    page_title="Director ACT Generator",
    page_icon="👮‍♂️",
    layout="wide"
)

session = requests.Session()
session.headers.update(HEADERS)

# columnas de nota + promedio
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

def obtener_notas_finales(session, course_id):
    params = {"type[]": "StudentEnrollment", "state[]": "active", "per_page": 100}
    enrolls = canvas_request(
        session, "get",
        f"/courses/{course_id}/enrollments",
        payload=params,
        paginated=True
    )
    resultado = {}
    for e in enrolls or []:
        if e.get("type") != "StudentEnrollment":
            continue
        sis_id   = e.get("sis_user_id")
        sortable = e["user"].get("sortable_name", "")
        login_id = e["user"].get("login_id", "")
        apellido, nombre = [p.strip() for p in sortable.split(",",1)] if "," in sortable else ("","")
        try:
            final_grade   = float(e["grades"].get("final_grade"))
        except:
            final_grade = None
        try:
            current_grade = float(e["grades"].get("current_grade"))
        except:
            current_grade = None
        resultado[sis_id] = {
            "first":   nombre,
            "last":    apellido,
            "final":   final_grade,
            "current": current_grade,
            "email":   login_id
        }
    return resultado

st.title("Director ACT Generator 👮‍♂️")
st.info(
    "ℹ️ Generador de actas para los directores de diplomados. "
    "Ingresa los IDs de los cursos en orden (c1, c2, c3, c4, c5) "
    "y haz clic en el botón Obtener Datos."
)

curso_input = st.text_area(
    "IDs de cursos (c1 c2 c3 c4 c5) en orden:",
    height=150
)
curso_ids = [c for c in re.split(r"[,\s]+", curso_input.strip()) if c]

if st.button("Obtener Datos", use_container_width=True):
    if len(curso_ids) != 5:
        st.error("Debes ingresar exactamente 5 IDs de curso.")
        st.stop()

    alumnos = {}
    courses_info = []
    invalid_ids = []

    for idx, cid in enumerate(curso_ids, start=1):
        course_info = canvas_request(session, "get", f"/courses/{cid}")
        if course_info:
            courses_info.append({
                "id":            course_info["id"],
                "account_id":    course_info["account_id"],
                "name":          course_info["name"],
                "course_code":   course_info["course_code"],
                "sis_course_id": course_info["sis_course_id"],
            })
        else:
            invalid_ids.append(cid)

        for sis, info in obtener_notas_finales(session, cid).items():
            if sis not in alumnos:
                alumnos[sis] = {
                    "first":  info["first"],
                    "last":   info["last"],
                    "grades": {},
                    "email":  info["email"]
                }
            alumnos[sis]["grades"][f"C{idx}"] = {
                "final":   info.get("final"),
                "current": info.get("current")
            }

    if invalid_ids:
        st.error(f"❌ IDs inválidos: {invalid_ids}")
        st.stop()

    firmas = {
        re.sub(r"-C\d+-", "-CX-", c["sis_course_id"])
        for c in courses_info
    }
    if len(firmas) != 1:
        st.error(f"❌ Cursos de diplomados distintos: {firmas}")
        st.stop()

    firma = firmas.pop()
    st.success(f"✅ Diplomatdo: {firma}")
    sub_acc = canvas_request(session, "get",
                             f"/accounts/{courses_info[0]['account_id']}")
    if sub_acc:
        try:
            code = courses_info[0]["course_code"].split("-")[1]
        except:
            code = "Versión desconocida"
        st.success(f"{sub_acc['name']} - {code}")

    filas = []
    for sis, info in alumnos.items():
        row = {
            "Nombre":   info["first"],
            "Apellido": info["last"],
            "RUT":      format_rut(sis)
        }
        notas = []
        pendiente = False
        reprobados = 0

        for i in range(1, 6):
            key = f"C{i}"
            if key not in info["grades"]:
                row[key] = "No existe"
                continue
            gd      = info["grades"][key]
            final   = gd.get("final")
            current = gd.get("current")
            if final is not None and current is not None and final != current:
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

        missing = sum(1 for i in range(1,6) if row[f"C{i}"]=="No existe")
        if pendiente:
            row["Estado"] = "Pendiente"
        elif missing > 0:
            row["Estado"] = "Regularizar"
        elif row["Promedio"] == "Sin calcular":
            row["Estado"] = "Sin notas"
        elif row["Promedio"] >= 4.0:
            row["Estado"] = "Aprobado"
        else:
            row["Estado"] = "Reprobado"

        if reprobados == 1:
            row["Observaciones"] = "Puede recursar"
        elif reprobados >= 2:
            row["Observaciones"] = "Perdido"
        else:
            row["Observaciones"] = ""

        row["Email"] = info["email"]
        filas.append(row)

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

    st.session_state["df"] = df
    st.session_state["df_export"] = df_export
    st.session_state["filename"] = f"{sub_acc.get('name')} - {code}.xlsx"


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
