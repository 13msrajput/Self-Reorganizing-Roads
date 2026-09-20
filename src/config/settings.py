"""Config loader. Resolves settings.yaml relative to the project root."""

from pathlib import Path
import yaml


def load_config(config_path: str = "config/settings.yaml") -> dict:
    """
    Load YAML configuration.

    Path is resolved relative to the current working directory
    (expected to be the project root when running via `streamlit run`
    or `pytest` from the project root).
    """
    path = Path(config_path)
    if not path.exists():
        # Fallback: resolve relative to this file's grandparent (project root)
        path = Path(__file__).parent.parent.parent / config_path
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            "Run the app from the project root directory."
        )
    with open(path, "r") as fh:
        return yaml.safe_load(fh)
