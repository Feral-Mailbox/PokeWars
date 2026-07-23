from pathlib import Path


def test_nginx_config_contains_expected_blocks():
    conf = Path("infrastructure/nginx/default.conf").read_text()

    # Edge nginx proxies API/WS to backend and everything else to the frontend
    # container (which serves Vite bundles and /game-assets/).
    required_locations = ["/", "/api/", "/api/ws/"]
    for loc in required_locations:
        assert f"location {loc}" in conf, f"Missing location block: {loc}"

    # SSL config present
    assert "ssl_certificate" in conf and "ssl_certificate_key" in conf
    assert "listen 443 ssl;" in conf
