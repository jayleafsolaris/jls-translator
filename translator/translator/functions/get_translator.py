from deep_translator import GoogleTranslator


def get_translator(google_code):
    return GoogleTranslator(source="en", target=google_code)
