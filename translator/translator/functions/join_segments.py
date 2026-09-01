def join_segments(parts):
    """Inverse of split_segments() when given (kind, literal_text) pairs."""
    return "".join(content for _, content in parts)
