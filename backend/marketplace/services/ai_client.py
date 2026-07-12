import requests
from django.conf import settings


class AIServiceUnavailable(Exception):
    """
    Raised when the AI microservice can't be reached or times out.
    Callers should catch this and return a clean error response — the
    point of raising a specific exception here, rather than letting
    requests' own exceptions propagate, is so the view layer has one
    thing to catch regardless of whether the underlying failure was a
    connection error, a timeout, or a non-2xx response.
    """


def fetch_json(path: str) -> dict:
    """
    Call the AI microservice over HTTP and return the parsed JSON response.

    This is the integration point between Django (the marketplace backend)
    and FastAPI (the AI service) — two separate containers communicating
    over the Docker network using the service name as hostname.
    """
    url = f'{settings.AI_SERVICE_URL}{path}'
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise AIServiceUnavailable(f'Could not reach the AI service ({url}): {exc}') from exc