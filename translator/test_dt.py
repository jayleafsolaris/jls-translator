import sys
from deep_translator import GoogleTranslator

def test_google_translator():
    try:
        # Fast test translation call
        result = GoogleTranslator(source="auto", target="es").translate("test")
        
        # Verify valid string return (catches empty HTML or bad response payloads)
        if not result or not isinstance(result, str):
            print("GoogleTranslator Error: Returned empty or invalid payload", file=sys.stderr)
            
    except Exception as e:
        # Print only the exception error details
        print(f"GoogleTranslator Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    test_google_translator()