from pathlib import Path

def test_env_files_have_matching_keys():
    base = Path("infrastructure")
    env_main = (base / ".env.db").read_text().splitlines()
    env_example = (base / ".env.db.example").read_text().splitlines()

    def get_keys(lines):
        return set(line.split('=')[0].strip() for line in lines if '=' in line and not line.startswith("#"))

    assert get_keys(env_main) == get_keys(env_example), "Mismatch between .env.db and .env.db.example keys"
