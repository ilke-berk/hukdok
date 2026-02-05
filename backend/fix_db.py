import json
import sqlite3
import os

def fix_db_clients():
    # PATH FIX: The script is in backend/, so data/ is relative to it
    # BUT we run it from root, so backend/data/hukudok.db
    db_path = os.path.join("backend", "data", "hukudok.db")
    
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("Scanning clients table for corrupted source_ids...")
        cursor.execute("SELECT id, name, source_ids FROM clients")
        rows = cursor.fetchall()
        
        fixed_count = 0
        
        for row in rows:
            cid, name, source_ids = row
            
            if not source_ids:
                continue
                
            # Aggressive recursive unwrapping
            original = source_ids
            current = source_ids
            
            # Helper to decode
            def recursive_decode(val):
                if isinstance(val, str):
                    try:
                        # Try to parse as JSON
                        decoded = json.loads(val)
                        if isinstance(decoded, (list, str)):
                            return recursive_decode(decoded)
                    except:
                        pass
                
                if isinstance(val, list):
                    # Flatten list and decode items
                    new_list = []
                    for item in val:
                        new_list.extend(recursive_flatten(item))
                    return new_list
                
                return [str(val)]

            def recursive_flatten(val):
                # Returns a list of strings
                if isinstance(val, list):
                    res = []
                    for x in val:
                        res.extend(recursive_flatten(x))
                    return res
                
                if isinstance(val, str):
                    # Check if string is actually a JSON list
                    try:
                        if val.startswith("[") and val.endswith("]"):
                            decoded = json.loads(val)
                            if isinstance(decoded, list):
                                return recursive_flatten(decoded)
                    except:
                        pass
                    # Check if string is JSON string (doubly encoded)
                    try:
                        if val.startswith('"') and val.endswith('"'):
                             decoded = json.loads(val)
                             return recursive_flatten(decoded)
                    except:
                        pass
                        
                return [str(val)]

            # Simplified approach: Just keep loading until we hit a list or non-json string
            temp = source_ids
            decoded_any = False
            
            while isinstance(temp, str):
                try:
                    loaded = json.loads(temp)
                    if loaded != temp:
                        temp = loaded
                        decoded_any = True
                    else:
                        break
                except:
                    break
            
            # If we ended up with a list, verify its contents
            final_ids = []
            if isinstance(temp, list):
                 for x in temp:
                     final_ids.extend(recursive_flatten(x))
            else:
                 final_ids.extend(recursive_flatten(temp))
            
            # Remove duplicates and empty
            final_ids = sorted(list(set([f for f in final_ids if f])))
            
            current_clean = json.dumps(final_ids)
            
            # Update if different or if we detected decoding
            # Check length: if original was huge and new is small, definitely fixed
            if len(current_clean) < len(original) or (decoded_any and current_clean != original):
                print(f"Fixing client {cid} ({name}):\n   Size: {len(original)} -> {len(current_clean)}")
                # print(f"   Sample: {original[:50]}... -> {current_clean}")
                cursor.execute("UPDATE clients SET source_ids = ? WHERE id = ?", (current_clean, cid))
                fixed_count += 1
        
        conn.commit()
        print(f"✅ Fixed {fixed_count} corrupted client records.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_db_clients()
