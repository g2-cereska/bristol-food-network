import requests
from django.conf import settings


def fetch_json(path: str) -> dict:
    """
    Call the AI microservice over HTTP and return the parsed JSON response.

    This is the integration point between Django (the marketplace backend)
    and FastAPI (the AI service) — two separate containers communicating
    over the Docker network using the service name as hostname.
    """
    url = f'{settings.AI_SERVICE_URL}{path}'
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()
