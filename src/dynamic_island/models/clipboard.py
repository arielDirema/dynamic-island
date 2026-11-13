"""Clipboard categories and kind keys shared by the engine and the interface."""

CATEGORIES = (
    ("all", "clipboard.categories.all"),
    ("text", "clipboard.categories.text"),
    ("link", "clipboard.categories.links"),
    ("contact", "clipboard.categories.contacts"),
    ("image", "clipboard.categories.images"),
    ("files", "clipboard.categories.files"),
    ("pinned", "clipboard.categories.pinned"),
)

KIND_LABEL_KEYS = {
    "text": "clipboard.kinds.text",
    "link": "clipboard.kinds.link",
    "email": "clipboard.kinds.email",
    "phone": "clipboard.kinds.phone",
    "image": "clipboard.kinds.image",
    "files": "clipboard.kinds.files",
}

TAG_KEYS = {
    "link": "clipboard.tags.link",
    "lien": "clipboard.tags.link",       # legacy clipboard records
    "email": "clipboard.tags.email",
    "e-mail": "clipboard.tags.email",    # legacy clipboard records
    "phone": "clipboard.tags.phone",
    "numéro": "clipboard.tags.phone",    # legacy clipboard records
}
