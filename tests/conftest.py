import os
import sys

# Make backend/ importable the same way the app imports it (flat module names)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
