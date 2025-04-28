from decouple import config
import requests
import re
import unicodedata

BASE_URL = config("URL")

def canvas_request(session, method, endpoint, payload=None, paginated=False):
    """
    Realiza peticiones a la API de Canvas y maneja la paginación si es necesario.
    
    :param session: Sesión de requests.Session() configurada previamente.
    :param method: Método HTTP ('get', 'post', 'put', 'delete').
    :param endpoint: Endpoint de la API (por ejemplo, "/courses/123/assignments").
    :param payload: Datos a enviar (para POST/PUT).
    :param paginated: Si es True, recorre todas las páginas y devuelve una lista con todos los resultados.
    :return: La respuesta en formato JSON o None en caso de error.
    """
    if not BASE_URL:
        raise ValueError("BASE_URL no está configurada. Usa set_base_url() para establecerla.")

    url = f"{BASE_URL}{endpoint}"
    results = []
    
    try:
        while url:
            if method.lower() == "get":
                response = session.get(url, json=payload)
            elif method.lower() == "post":
                response = session.post(url, json=payload)
            elif method.lower() == "put":
                response = session.put(url, json=payload)
            elif method.lower() == "delete":
                response = session.delete(url)
            else:
                print("Método HTTP no soportado")
                return None

            if not response.ok:
                print(f"Error en la petición a {url} ({response.status_code}): {response.text}")
                return None

            data = response.json()
            if paginated:
                results.extend(data)
                
                url = response.links.get("next", {}).get("url") 
            else:
                return data 

        return results if paginated else None

    except requests.exceptions.RequestException as e:
        print(f"Excepción en la petición a {url}: {e}")
        return None
    
def clean_string(input_string: str) -> str:
    cleaned = input_string.strip().lower()
    cleaned = unicodedata.normalize('NFD', cleaned)
    cleaned = re.sub(r'[^\w\s.,!?-]', '', cleaned)
    cleaned = re.sub(r'[\u0300-\u036f]', '', cleaned)
    return cleaned

def parse_course_ids(input_text):
    """Limpia y procesa el input para extraer los course IDs."""
    cleaned = input_text.replace(",", "\n").replace(" ", "\n")
    return list(filter(None, map(lambda x: x.strip(), cleaned.split("\n"))))

def format_rut(rut_raw: str) -> str:
    """
    Formatea un RUT chileno: 193745040 -> 19.374.504-0
    Si la entrada no cumple el patrón [cuerpo+dígito_verificador], lo devuelve sin cambios.
    """
    # 1) Eliminar puntos y guiones existentes
    clean = re.sub(r"[.\-]", "", rut_raw).upper()
    # 2) Validar: al menos 2 chars, cuerpo dígitos y DV dígito o K
    if re.fullmatch(r"\d{1,8}[0-9K]", clean):
        cuerpo, dv = clean[:-1], clean[-1]
        # 3) Separar miles en el cuerpo
        rev = cuerpo[::-1]
        grupos = [rev[i : i+3] for i in range(0, len(rev), 3)]
        cuerpo_fmt = ".".join(g[::-1] for g in grupos[::-1])
        return f"{cuerpo_fmt}-{dv}"
    # 4) Si no es válido, devolver original
    return rut_raw
