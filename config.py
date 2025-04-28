from decouple import config

BASE_URL = config("URL")
API_TOKEN = config("TOKEN")
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}