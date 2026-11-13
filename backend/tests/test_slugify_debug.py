import sys
import os


def test_slugify_import():
    print(f"DEBUG: sys.path: {sys.path}")
    print(f"DEBUG: CWD: {os.getcwd()}")
    try:
        import slugify

        print(f"DEBUG: slugify imported from {slugify}")
    except ImportError as e:
        print(f"DEBUG: ImportError: {e}")
        raise e
