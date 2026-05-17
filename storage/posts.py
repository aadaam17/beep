# storage/posts.py

from core.types import PostView

from .fs import BeepFS

fs = BeepFS()

def list_posts() -> list[str]:
    return fs.list_posts()

def get_post(post_id: str) -> PostView:
    return fs.read_post(post_id)
