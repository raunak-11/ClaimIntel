"""Quick test: verify Gemini API is reachable and ask_json works."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from services.gemini_client import ask_text, ask_json

print("Testing ask_text...")
try:
    r = ask_text("Reply with exactly the word: hello")
    print(f"  OK: '{r}'")
except Exception as e:
    print(f"  FAIL: {e}")

print("Testing ask_json...")
try:
    r = ask_json('Return a JSON object with a single key "status" set to "ok".')
    print(f"  OK: {r}")
except Exception as e:
    print(f"  FAIL: {e}")
