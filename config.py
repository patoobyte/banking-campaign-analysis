from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITEMAPS = DATA / "sitemaps"
RAW = DATA / "raw"
CLEAN = DATA / "clean"
BACKUPS = DATA / "backups"
RUNS = DATA / "campaign-runs"
GRAPHS = DATA / "graphs"
PROMPTS = ROOT / "prompts"
FILTERS = DATA / "url-filters"

BANKS = {
    "ING": {"seeds": ["https://www.ing.be/"], "signature_color": "#FF6200"},
    "BNP Paribas Fortis": {"seeds": ["https://www.bnpparibasfortis.be/fr/public/particuliers"], "signature_color": "#00965E"},
    "Revolut": {"seeds": ["https://www.revolut.com/"], "signature_color": "#191C1F"},
}
LANGUAGES = {"French": "fr", "Dutch / Flemish": "nl", "English": "en", "Unknown": "unknown"}
AUDIENCES = ["Below 18", "Youth 18-25", "Adult", "Senior", "Professional", "Not identifiable"]

for folder in (DATA, SITEMAPS, RAW, CLEAN, BACKUPS, RUNS, GRAPHS, PROMPTS, FILTERS):
    folder.mkdir(parents=True, exist_ok=True)

def slug(value: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in value).strip("-").replace("--", "-")

def bank_dir(root: Path, bank: str) -> Path:
    path = root / slug(bank)
    path.mkdir(parents=True, exist_ok=True)
    return path
