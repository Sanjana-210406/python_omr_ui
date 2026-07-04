# AI Pair Programming History & Prompt Log

This document records the step-by-step development journey of adding cross-platform compatibility, standalone installer support, and cloud compilation to the OMR Test Manager desktop app. It outlines the AI prompts used, commits made, errors faced, and their resolutions.

---

## Step 1: macOS Compatibility & Firestore Bug Fixes

### Prompt / Goal
> *"launch ui. Also for the windows path don't remove that paths and add the necessary paths to support both mac and windows"*

### What We Did
* Add platform-specific suffixes (`_darwin`, `_win32`) in `SettingsManager` to prevent overwriting Windows settings on Mac.
* Set up dynamic Poppler PATH checks to fall back to macOS system PATH.
* Resolved `NameError` crash in `push_to_firestore` where variables were referenced before definition.
* Cleared redundant path joins in file retrieval.

### Commit
`82dd9bd` - *Add macOS support, OMRChecker integration fixes, and clean documentation*

---

## Step 2: CSV Preview Formatting & Indentation Error

### Prompt / Goal
> *"why is that page path being shownb. i want to filter them out. in file id it is showing like this page_1.jpg"*

### What We Did
* Modified `display_latest_csv` in `index.py` to filter out `input_path` and `output_path` columns.
* Formatted `file_id` values (e.g. `page_1.jpg` -> `Page 1`) and updated headers (e.g. `q1` -> `Q1`).

### Error Faced
An `IndentationError` occurred on app launch because the `if rows:` block was accidentally un-indented during the text replacement, crashing the startup process:
```
File "index.py", line 758
  headers = [h for h in rows[0].keys() if h not in ["input_path", "output_path"]]
IndentationError: unexpected indent
```

### Resolution
Restored the `if rows:` statement at line 757, correctly aligned all code lines under the conditional block, and verified that the application started without errors.

---

## Step 3: Documentation Separation

### Prompt / Goal
> *"in the READMe file i want two sections. This software will be sent to a school for usage so one part should the team setup and other part should be everything for the people in the school to setup the software"*

### What We Did
* Restructured `README.md` into:
  1. **Part 1: Developer & Admin Setup**: Detailing SQLite schema, Firestore credentials setup, and template packaging.
  2. **Part 2: School Setup & End-User Guide**: Python install commands, Poppler PATH settings, GUI step-by-step workflow guide, and common staff troubleshooting.

---

## Step 4: Standalone Packaging & Eliminating Poppler

### Prompt / Goal
> *"I created the pull request now. So this I want to make it like installable version like when i send a installer the school should be able to easily install this software"*

### What We Did
* **Removed Poppler Dependency**: Replaced `pdf2image` with `pymupdf` (`import fitz`) in `index.py` to do PDF conversion in pure Python. This eliminates the need for Poppler on both Mac and Windows.
* **Built-in OMRChecker**: Copied OMRChecker `src/` to `python_omr_ui/src/`. Modified `run_command` in `index.py` to run the engine programmatically as a module, redirecting logs directly to the GUI progress bar.
* **Stable Paths**: Configured the app to write configuration and database schemas to a secure user directory (`~/.omr_test_manager/`) when running inside a packaged bundle, and unpack default templates to `~/OMR_Test_Manager/samples/` on first launch.
* **Packaging Script**: Created `build_installer.py` using PyInstaller to bundle the application.

### Commit
`758897a` - *Integrate PyMuPDF, bundle OMRChecker directly, and add macOS/Windows build script*

---

## Step 5: Windows Executable & CI Build Errors

### Prompt / Goal
> *"the school computers are windows. give me the file like I can send directly"*

### What We Did
* Created `build_installer_win.bat` for local Windows building.
* Added a GitHub Actions workflow (`.github/workflows/build.yml`) to automatically compile the Windows `.exe` on push.

### CI Error 1 (Run #1)
The compiler job failed on GitHub Actions because the `pyinstaller` command was installed in a folder not added to the runner shell `PATH`.
* **Resolution**: Modified `build_installer.py` to run PyInstaller as a module: `sys.executable -m PyInstaller`.
* **Commit**: `4181729` - *Fix PyInstaller execution by running it as a python module*

### CI Error 2 (Run #2 / #3)
The compiler failed immediately with `FileNotFoundError` because the `samples/` directory is locally untracked and did not exist on GitHub after checkout.
* **Resolution**: Updated `build_installer.py` to check if `samples/`, `tests.db`, and `app_config.json` are present in the directory. If they are missing, it automatically creates dummy placeholders so PyInstaller completes successfully.
* **Commit**: `860c3c9` - *Auto-create placeholder packaging assets if missing*

### CI Success (Run #4)
The build successfully compiled, bundled all dependencies into a single standalone `OMRTestManager.exe` file, and uploaded it as a downloadable GitHub Actions artifact.
