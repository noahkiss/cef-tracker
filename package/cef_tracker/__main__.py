from pathlib import Path

from .main import run

if __name__ == "__main__":
    run(Path(__file__).parent.parent / "config.toml")
