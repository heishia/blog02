import time, json, csv
from pathlib import Path
from typing import Dict, List

def new_run_dir(root: str = "artifacts") -> Path:
	run_id = time.strftime("%Y%m%d_%H%M%S")
	p = Path(root) / run_id
	(p / "02_articles").mkdir(parents=True, exist_ok=True)
	return p

def write_json(path: Path, obj):
	path.parent.mkdir(parents=True, exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(obj, f, ensure_ascii=False, indent=2)

def save_keywords_csv(path: Path, rows: List[Dict]):
	with open(path, "w", newline="", encoding="utf-8") as f:
		w = csv.DictWriter(f, fieldnames=["keyword","S","D","C"])
		w.writeheader()
		for r in rows:
			w.writerow(r)

def read_keywords_csv(path: Path) -> List[Dict]:
	with open(path, "r", encoding="utf-8") as f:
		return list(csv.DictReader(f))