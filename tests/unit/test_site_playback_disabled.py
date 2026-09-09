import pytest
from fastapi.testclient import TestClient
from apps.api.main import app


@pytest.mark.parametrize('path', [
    '/api/v1/films/the-bat-whispers-1930/media',
    '/api/v1/films/imported-film/media?edition_id=custom-edition',
    '/media/the_bat_whispers_1930_proxy.mp4',
    '/media/anything.mp4',
])
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_no_video_bytes_are_served(path, method):
    with TestClient(app) as client:
        response = client.request(method, path, headers={'Range': 'bytes=0-31'})
    assert response.status_code == 410
    assert response.headers.get('cache-control') == 'no-store'
    assert 'content-range' not in response.headers
    assert 'video/' not in response.headers.get('content-type', '')
