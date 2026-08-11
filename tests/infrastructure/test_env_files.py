from pathlib import Path

REQUIRED_DB_KEYS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}


def _env_keys(path: Path) -> set[str]:
    return {
        line.split("=", 1)[0].strip()
        for line in path.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def test_env_files_have_matching_keys():
    """Example env files are committed; live .env files are gitignored."""
    example = Path("infrastructure/.env.db.example")
    live = Path("infrastructure/.env.db")

    assert example.is_file(), "Missing infrastructure/.env.db.example"
    example_keys = _env_keys(example)
    assert REQUIRED_DB_KEYS <= example_keys, (
        f".env.db.example is missing keys: {sorted(REQUIRED_DB_KEYS - example_keys)}"
    )

    if not live.is_file():
        return

    assert _env_keys(live) == example_keys, "Mismatch between .env.db and .env.db.example keys"
