"""Identify uploads by their original bytes, independent of filename/category."""
import hashlib


def document_hash(data):
    return hashlib.sha256(data).hexdigest()


def remove_duplicate_documents(documents):
    seen = set()
    unique = []
    for document in documents:
        digest = document_hash(document['data'])
        if digest not in seen:
            seen.add(digest)
            unique.append(document)
    return unique
