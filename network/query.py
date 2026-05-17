# network/query.py

import requests


class QueryEngine:
    def __init__(self, peers):
        self.peers = peers

    def query_recent(self, limit=50):
        results = set()

        for peer in self.peers:
            try:
                res = requests.get(f"{peer}/objects/recent?limit={limit}")
                ids = res.json().get("objects", [])
                results.update(ids)
            except:
                continue

        return list(results)

    def query_by_author(self, author):
        results = set()

        for peer in self.peers:
            try:
                res = requests.get(f"{peer}/objects/by_author/{author}")
                ids = res.json().get("objects", [])
                results.update(ids)
            except:
                continue

        return list(results)