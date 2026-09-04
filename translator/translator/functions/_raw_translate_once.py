from ..common.text_protect import split_segments, join_segments
from ..common.translate import TranslationUnavailableError, _STOPPED
from ._translate_raw_api_call import _translate_raw_api_call


def _raw_translate_once(google_code, text):
    """
    One real attempt against Google -- no retries, no fallback, raises
    on failure. Also short-circuits immediately if a prior failure streak
    already declared the service unavailable, so threads stop hammering a
    dead service once that's been detected.

    Protected tokens (color codes, %1$s-style placeholders, {key.path}
    cross-references, PUA glyphs) are split OUT of the text entirely
    before anything is sent to Google -- never embedded as an inline
    "@@PHn@@"-style marker for Google to (sometimes) mangle or silently
    drop as noise, which is how a token like a {key.path} cross-reference
    could previously vanish from the translated result. This mirrors the
    same split_segments()/join_segments() approach translate_many() uses
    for its batches.
    """
    if _STOPPED:
        raise TranslationUnavailableError(
            "Google Translate does not appear to be available right now. Please try again later."
        )

    text_clean = text.replace('\n', '__NL__')
    parts = split_segments(text_clean)
    distinct_text = list(dict.fromkeys(content for kind, content in parts if kind == "text"))

    if not distinct_text:
        # Nothing but tokens (e.g. a value that's just one {key.path}
        # cross-reference) -- nothing to actually translate.
        return join_segments(parts).replace('__NL__', '\n')

    combined = "\n".join(distinct_text)
    result = _translate_raw_api_call(google_code, combined)

    lines = [line.replace('\r', '') for line in result.split('\n')]
    if len(lines) == len(distinct_text):
        segment_results = dict(zip(distinct_text, lines))
    else:
        # Google's returned line count didn't line up with what was sent --
        # translate each distinct fragment on its own instead of guessing
        # at an alignment.
        segment_results = {seg: _translate_raw_api_call(google_code, seg) for seg in distinct_text}

    rebuilt = []
    for kind, content in parts:
        rebuilt.append(content if kind == "token" else segment_results.get(content, content))
    return "".join(rebuilt).replace('__NL__', '\n')
