"""
clear.py - Delete all files in the outputs/ folder.

Usage:
    python clear.py
"""
 
from pathlib import Path
 
outputs_dir = Path(__file__).parent / "outputs"
 
if not outputs_dir.exists():
    print("outputs/ folder doesn't exist — nothing to clear.")
else:
    files = list(outputs_dir.iterdir())
    if not files:
        print("outputs/ is already empty.")
    else:
        for f in files:
            if f.is_file():
                f.unlink()
                print(f"  Deleted  {f.name}")
        print("Done.")