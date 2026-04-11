import pytest


def test_route_index_status_code(client):
    """Verifica se a página principal (Home) carrega corretamente."""
    response = client.get("/")
    assert response.status_code == 200
