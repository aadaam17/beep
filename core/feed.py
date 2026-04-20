from storage.objects import list_objects, get_object


def get_all_posts():
    """
    Return all feed objects sorted by timestamp DESC.
    """
    posts = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if not obj:
            continue

        if obj.get("type") in {"post", "share", "quote"}:
            posts.append(obj)

    # sort newest first
    posts.sort(key=lambda x: x["timestamp"], reverse=True)
    return posts

def get_followed_posts(following_pubkeys: set):
    posts = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if not obj:
            continue

        if obj.get("type") in {"post", "share", "quote"} and obj.get("author") in following_pubkeys:
            posts.append(obj)

    posts.sort(key=lambda x: x["timestamp"], reverse=True)
    return posts
