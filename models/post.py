from dataclasses import dataclass
from typing import Optional

@dataclass
class Post:
    id: str
    author: str
    content: str
    timestamp: int
    comments: Optional[list["Post"]] = None
    revoked: bool = False