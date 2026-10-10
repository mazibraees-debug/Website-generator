class ValidationError(Exception):
    pass


def validate_files(files: dict) -> dict[str, str]:
    if not isinstance(files, dict) or not files:
        raise ValidationError("Generated response empty ya invalid format mein hai.")

    # In case the model returns "html", "css", "js"
    html = files.get("html", "")
    css = files.get("css", "")
    js = files.get("js", "")

    # In case the model returns a file map like "/index.html", "/style.css"
    if not html:
        for k, v in files.items():
            if k.endswith(".html") or k.lower() in ("index.html", "html"):
                html = v
                break
        if not html and any("<html" in str(v).lower() or "<!doctype" in str(v).lower() for v in files.values()):
            for v in files.values():
                if isinstance(v, str) and ("<html" in v.lower() or "<!doctype" in v.lower()):
                    html = v
                    break

    if not html:
        raise ValidationError("Website HTML structure generate nahi ho paayi.")

    return {
        "html": str(html),
        "css": str(css) if css else "",
        "js": str(js) if js else "",
    }
