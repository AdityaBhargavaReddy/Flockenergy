"""Test runner script."""
import sys
import pytest

if __name__ == "__main__":
    exit_code = pytest.main(["-v", "tests"])
    print(f"\nAll tests completed with status: {exit_code}")
    import os
    os._exit(0 if exit_code == 0 else 1)
