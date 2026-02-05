import json
import os
from pathlib import Path

def inspect_and_clean():
    app_data_dir = Path.home() / "AppData" / "Local" / "HukuDok" / "data"
    json_path = app_data_dir / "muvekkil_listesi.json"
    
    print(f"Inspecting: {json_path}")
    
    if not json_path.exists():
        print("File not found.")
        return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        print(f"File size: {len(content)} bytes")
        
        if "\\\\" * 10 in content:
            print("⚠️ DETECTED EXCESSIVE BACKSLASHES! File is likely corrupted.")
            print("Sample content:")
            print(content[:500])
            
            # Attempt to fix (nuclear option: delete it to let it regenerate)
            print("\nAttempting to delete corrupted file to force regeneration...")
            try:
                os.remove(json_path)
                print("✅ File deleted. Restart the backend to regenerate it.")
            except Exception as e:
                print(f"❌ Failed to delete file: {e}")
        else:
            print("✅ File looks normal (no excessive backslashes detected).")
            # Try parsing
            try:
                data = json.loads(content)
                print(f"✅ JSON parsed successfully. Keys: {list(data.keys())}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON Decode Error: {e}")

    except Exception as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    inspect_and_clean()
