import yaml
from typing import Dict

def load_yaml(path: str) -> Dict:
	with open(path, "r", encoding="utf-8") as f:
		return yaml.safe_load(f)

def load_merged(base_path: str, override_path: str | None = None) -> Dict:
	base = load_yaml(base_path)
	if not override_path:
		return base
	over = load_yaml(override_path)
	def merge(a, b):
		for k, v in b.items():
			if isinstance(v, dict) and isinstance(a.get(k), dict):
				a[k] = merge(a[k], v)
			else:
				a[k] = v
		return a
	return merge(base, over)