import pytest
from tsensor.extensions import data_stream, buffer_stream

def test_api_restart_clears_data_and_restarts_acquisition(client, mocker):
    """Verifica se /api/restart para a aquisição, limpa dados e reinicia."""
    # Adiciona dados falsos nos streams
    data_stream.add(25.0, "10:00:00")
    buffer_stream.add(25.0, "10:00:00")
    assert len(data_stream) == 1
    assert len(buffer_stream) == 1

    # Mocks das funções de controle
    mock_stop = mocker.patch("tsensor.routes.api.stop_acquisition")
    mock_start = mocker.patch("tsensor.routes.api.start_acquisition")

    response = client.post("/api/restart")

    # Verificações
    assert response.status_code == 200
    assert response.json["success"] is True
    
    # Garante que as funções foram chamadas na ordem correta
    mock_stop.assert_called_once()
    mock_start.assert_called_once()
    
    # Garante que os dados foram limpos
    assert len(data_stream) == 0
    assert len(buffer_stream) == 0
