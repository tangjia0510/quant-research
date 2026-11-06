"""All new CLI-generated data stays in repository-root fin_data/ (Git-ignored)."""
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIN_DATA = REPOSITORY_ROOT / 'fin_data'


def output_path(value):
    path = Path(value).expanduser().resolve()
    root = FIN_DATA.resolve()
    if not path.is_relative_to(root):
        raise ValueError('Output must stay under repository-root fin_data/: ' + str(root))
    return path
