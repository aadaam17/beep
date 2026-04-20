from core.object import BeepObject
from storage.objects import save_object


def create_post(author_pubkey, content, *, post_type="post", shared_from=None, quote=False, parent_id=None):
    obj = BeepObject.create_object(
        type_=post_type,
        author_pubkey=author_pubkey,
        content=content,
        meta={
            "shared_from": shared_from,
            "quote": quote,
            "parent_id": parent_id,
        },
    )
    save_object(obj.to_dict())
    return obj.id
