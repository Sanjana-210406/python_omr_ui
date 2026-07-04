import os
import sys
import subprocess
import shutil

def build():
    print("=== Step 1: Cleaning up previous builds ===")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"Removing {folder}...")
            shutil.rmtree(folder)

    # PyInstaller packaging arguments
    pyinstaller_args = [
        "pyinstaller",
        "--windowed",              # macOS app bundle, hides console
        "--name=OMRTestManager",    # Output application name
        "--add-data=samples:samples", # Bundle OMR template files
        "--add-data=app_config.json:.", # Bundle default config
        "--add-data=tests.db:.",      # Bundle default database
        "index.py"
    ]

    print("\n=== Step 2: Running PyInstaller ===")
    print("Running command:", " ".join(pyinstaller_args))
    
    result = subprocess.run(pyinstaller_args, capture_output=False)
    if result.returncode != 0:
        print("Error: PyInstaller build failed!")
        sys.exit(result.returncode)

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

if __name__ == "__main__":
    build()
