import sys
import os
import logging
import asyncio

# Add 'backend' to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Configure logging
logging.basicConfig(level=logging.INFO)

try:
    print("Importing api...")
    import api 
    
    print("Running refresh_lists_background()...")
    
    # Run in event loop if async needed, but refresh_lists_background is sync def in api.py
    # (Checking api.py... def refresh_lists_background(): ... it is sync)
    api.refresh_lists_background()
    
    print("\n--- Checking Config State ---")
    config = api.DynamicConfig.get_instance()
    lawyers = config.get_lawyers()
    
    # Check if we got data
    if lawyers:
        print(f"✅ SUCCESS: Loaded {len(lawyers)} lawyers.")
    else:
        print("⚠️ WARNING: Lawyers list is empty (Could be DB empty or sync failed).")

except ImportError as ie:
    print(f"❌ Missing Dependency: {ie}")
except Exception as e:
    print(f"❌ TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
