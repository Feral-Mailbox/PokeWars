import yaml
from pathlib import Path

def test_docker_compose_has_required_services():
    base = Path("infrastructure")
    files = {
        "docker-compose.yml": ["postgres", "nginx", "redis", "pgadmin"],
        "docker-compose.dev.yml": ["backend", "frontend"]
    }

    for file, required_services in files.items():
        content = yaml.safe_load((base / file).read_text())
        assert "services" in content, f"No 'services' block in {file}"
        for required in required_services:
            assert required in content["services"], f"{required} missing in {file}"
