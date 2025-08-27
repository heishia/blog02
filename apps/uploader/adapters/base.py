from dataclasses import dataclass
from typing import List

@dataclass
class UploadItem:
	platform: str
	title: str
	content_path: str
	images: List[str]
	meta_path: str

class Uploader:
	def upload(self, item: UploadItem) -> dict:
		raise NotImplementedError