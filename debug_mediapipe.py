import sys
print(f"Python Executable: {sys.executable}")
print(f"Path: {sys.path}")

try:
    import mediapipe as mp
    print(f"MediaPipe File: {mp.__file__}")
    print(f"MediaPipe Dir: {dir(mp)}")
    
    if hasattr(mp, 'solutions'):
        print("✅ mp.solutions exists")
        print(f"Solutions: {dir(mp.solutions)}")
    else:
        print("❌ mp.solutions does NOT exist")
        
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
