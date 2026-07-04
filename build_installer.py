import os
import sys
import subprocess
import shutil
import PyInstaller.__main__

def build():
    print("=== Step 1: Cleaning up previous builds ===")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"Removing {folder}...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Warning: Could not remove {folder}: {e}")

    # Semicolon (;) is used as path separator on Windows, colon (:) on Mac/Linux
    sep = ";" if sys.platform == "win32" else ":"

    # PyInstaller packaging arguments
    pyinstaller_args = [
        "--windowed",                 # Hides terminal/console window
        "--name=OMRTestManager",       # Output application name
        f"--add-data=samples{sep}samples",     # Bundle OMR template files
        f"--add-data=app_config.json{sep}.",   # Bundle default config
        f"--add-data=tests.db{sep}.",         # Bundle default database
        "index.py"
    ]

    # For Windows, bundle into a single standalone executable file (.exe)
    if sys.platform == "win32":
        pyinstaller_args.append("--onefile")

    print("\n=== Step 2: Running PyInstaller ===")
    print("Running command: pyinstaller", " ".join(pyinstaller_args))
    
    try:
        PyInstaller.__main__.run(pyinstaller_args)
    except SystemExit as e:
        if e.code != 0:
            print("Error: PyInstaller build failed with code:", e.code)
            sys.exit(e.code)

    print("\n=== Step 3: PyInstaller build successful! ===")

    # macOS specific DMG packaging
    if sys.platform == "darwin":
        app_path = "dist/OMRTestManager.app"
        dmg_path = "dist/OMRTestManager.dmg"
        
        if os.path.exists(app_path):
            print("\n=== Step 4: Packaging as macOS DMG Installer ===")
            if os.path.exists(dmg_path):
                os.remove(dmg_path)
                
            # Create DMG using native macOS hdiutil
            hdiutil_args = [
                "hdiutil", "create",
                "-volname", "OMR Test Manager",
                "-srcfolder", app_path,
                "-ov",
                "-format", "UDZO",
                dmg_path
            ]
            print("Running command:", " ".join(hdiutil_args))
            
            dmg_result = subprocess.run(hdiutil_args)
            if dmg_result.returncode == 0:
                print(f"\nSuccess! macOS Installer created at: {os.path.abspath(dmg_path)}")
            else:
                print("Error: DMG packaging failed!")
        else:
            print("Error: OMRTestManager.app bundle not found in dist/!")
            
    elif sys.platform == "win32":
        exe_path = "dist/OMRTestManager.exe"
        if os.path.exists(exe_path):
            print(f"\nSuccess! Standalone Windows executable created at: {os.path.abspath(exe_path)}")
        else:
            print("Error: OMRTestManager.exe not found in dist/!")

if __name__ == "__main__":
    build()
