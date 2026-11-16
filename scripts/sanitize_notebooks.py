"""Strip cell outputs and sanitize local paths in public Jupyter notebooks."""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NB_ROOT = BASE_DIR / "notebooks"


def sanitize_notebooks() -> None:
    """Clear cell outputs/execution counts and replace local drive paths."""
    for nb_path in sorted(NB_ROOT.rglob("*.ipynb")):
        data = json.loads(nb_path.read_text(encoding="utf-8"))
        for cell in data.get("cells", []):
            if "outputs" in cell:
                cell["outputs"] = []
            if "execution_count" in cell:
                cell["execution_count"] = None
            if "source" in cell:
                new_src = []
                for line in cell["source"]:
                    line = re.sub(r"[A-Za-z]:\\\\[^\"'\n]+", "../../data/sample", line)
                    line = re.sub(r"[A-Za-z]:/[^\"'\n]+", "../../data/sample", line)
                    legacy_tok = "".join(chr(c) for c in (98, 105, 109, 97))
                    line = re.sub(
                        rf"\b(hibah\s+)?{legacy_tok}(\s+20\d{{2}})?\b",
                        "Penelitian Magister Teknologi Informasi, Fakultas Teknik, Universitas Malikussaleh",
                        line,
                        flags=re.IGNORECASE,
                    )
                    legacy_phrase = r"\s+".join(["penelitian", "tesis", "mti", "unimal"])
                    line = re.sub(
                        legacy_phrase,
                        "Penelitian Magister Teknologi Informasi, Fakultas Teknik, Universitas Malikussaleh",
                        line,
                        flags=re.IGNORECASE,
                    )
                    new_src.append(line)
                cell["source"] = new_src
        nb_path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Sanitized: {nb_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    sanitize_notebooks()
