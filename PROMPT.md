# AI Pair Programming History & Prompt Log

This document records the step-by-step development journey of adding cross-platform compatibility, standalone installer support, and cloud compilation to the OMR Test Manager desktop app. It outlines the AI prompts used, commits made, errors faced, and their resolutions.

---

# 🚀 QUICK START & USER MANUAL (For School Staff & Non-Technical Users)

If you are a school administrator or teacher, you do not need to understand the programming details below. Here is everything you need to install, configure, and use the OMR Test Manager.

## 📦 1. How to Install the App
* **Windows Users**: 
  1. Go to the GitHub repository: **`https://github.com/Sanjana-210406/python_omr_ui`**.
  2. Click on the **Actions** tab, select the latest run of **"Build Windows Executable"**, scroll down to the bottom, and download the **`OMRTestManager-Windows`** artifact.
  3. Extract the downloaded ZIP file.
  4. Double-click the **`OMRTestManager.exe`** file to start the app.
* **Mac Users**:
  1. Open your project folder and go to the `dist` directory: `/Users/sunil_kadam/Desktop/python_omr_ui/dist`
  2. Double-click the **`OMRTestManager.dmg`** file.
  3. Drag the **OMRTestManager** app icon into your **Applications** folder.
  4. To open it the first time: **Right-click** (or hold `Control` and click) the app icon in Applications, select **Open**, and click **Open** on the security warning.

---

## ⚙️ 2. First-Time Setup (Preferences)
1. Run the application and log in using the default PIN: **`123456`**.
2. Go to **Settings → Preferences** in the menu bar.
3. Configure these five directories and settings:
   * **Input Directory**: Create an empty folder on your computer (e.g., `inputs`) and choose it. This is where your exam sheet images will be loaded.
   * **Output Directory**: Create an empty folder on your computer (e.g., `outputs`) and choose it. This is where graded results will be saved.
   * **Templates Folder**: Select the folder containing your layouts (e.g., `samples`).
   * **Python Command**: Enter the path to your OMR script. 
     * *Windows Example:* `py C:\OMRChecker-master\main.py --inputDir {input} --outputDir {output}`
     * *Mac Example:* `python3 /Users/yourusername/OMRChecker-master/main.py --inputDir {input} --outputDir {output}`
   * **Firestore Auth Key**: Select the Google Cloud service account JSON key file provided by your technical coordinator.
4. Click **Save**.

---

## 📝 3. How to Grade Exams (Daily Workflow)
* **Step A: Add the Test**: Click **Add Test** on the left. Enter the Test Name, the Date (format: `YYYY-MM-DD`), and select the template format from the dropdown menu. Click **Save**.
* **Step B: Load scanned PDF**: Select the test on the left sidebar. Click **Input PDF**, choose your scanned exam PDF, and let the app split it into images automatically.
* **Step C: Grade the Exam**: Click **Run Command** to start grading. The progress bar will load, and your student results table will automatically display on the right panel when finished.
* **Step D: Save to Cloud**: Click **Push to Firestore** to sync your results to the online database.

---

## 🛠️ 4. Quick Troubleshooting
* **"Template folder not found"**: Go to **Settings → Preferences** and verify that your **Templates Folder** points to the correct location.
* **Results Table not updating**: Click another test on the left sidebar and then click back on the current test to reload the table.
* **"Firestore Auth Key not found"**: Verify you selected your credentials JSON file in Preferences.

---

# 🛠️ DEVELOPER LOG & PAIR PROGRAMMING HISTORY
The sections below detail the step-by-step programming progress for technical teams:

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

---

## Step 6: OMR Refinements, Directory Isolation, and Crash Fixes

### What We Did
* **Isolated Directories**: Appended test ID suffixes to inputs/outputs folders to prevent multiple exams from overwriting each other's files.
* **Path Standardizing**: Converted path management internally to absolute paths to prevent runtime engine failures due to relative execution paths.
* **PDF Verification**: Added a warning popup to prompt the user if they attempt to run OMR grading before importing/processing a scanned PDF.
* **Cocoa GUI Crash Fix**: Disabled OpenCV/OMR debug window popups when OMRChecker is running in background threads, resolving thread-safety Cocoa GUI crashes on macOS.
* **Recursive Templates**: Programmed the template selection dropdown to scan directories recursively, finding all folders that contain `template.json`.
* **Bug Fixes**: Resolved a `NameError` inside `process_pdf` by properly returning the computed `page_count`.

### Commits
* `7f76f8f` - *Isolate test input/output directories by test ID to fix shared outputs bug*
* `5d893e7` - *Auto-create test subfolders if they do not exist*
* `1f4da3b` - *Convert relative paths to absolute internally to align shell and GUI executions*
* `a568430` - *Show warning if user runs command without loading a PDF first*
* `a2e90a6` - *Auto-import sample images from template folder if input directory is empty*
* `0c6a26e` - *Copy template config files (template.json) when auto-importing sample images*
* `bde338e` - *Disable OMR debug window popups in background thread to prevent Cocoa crashes*
* `1e33460` - *Disable OMR graphical debug windows globally in GUI mode*
* `727559c` - *Populate template dropdown recursively with folders containing template.json*
* `8f2a2ca` - *Fix NameError in process_pdf by returning page_count*

---

## Step 7: Packaging and Distributing Installers

### What We Did
* Built and verified the macOS standalone disk image installer (`dist/OMRTestManager.dmg`) using the local `build_installer.py` script.
* Verified that the automated CI/CD pipeline on GitHub successfully compiled the corresponding Windows standalone `.exe` installer.

---

## Step 8: Project Completion & Installer Distribution

### Goal
Deliver both the updated Mac and Windows installers to the school to finalize the project deployment.

### What We Did
* **Mac App Distribution**: Located and prepared `dist/OMRTestManager.dmg` built locally on the macOS system.
* **Windows App Distribution**: Downloaded the compiled `OMRTestManager.exe` executable from the GitHub Actions CI pipeline.
* **Documentation & Submission**: Updated `README.md` and `PROMPT.md` with final release notes, pushed all updates, and created the final upstream Pull Request (`PR #4`). Both cross-platform installers are ready to be sent to the school.

---

## Step 9: Option Analysis, 60Q Template, and Robust Answer Key Validation

### Goal
Implement a pixel-perfect 60-question template for the school's IIT sheet, resolve question-count validation crashes with 120-question CSVs, and generate Option Analysis reports.

### What We Did
* **60Q Standard Template**: Configured exact bubble mapping for Mathematics (Q1-Q20), Physics (Q21-Q35), Chemistry (Q36-Q50), and MAT (Q51-Q60).
* **Option Analysis report**: Programmed `generate_option_analysis` in `src/entry.py` to compile student response frequencies and correctness rates, saving the report as `Option_Analysis.csv`.
* **Key Validation Filtering**: Programmed `src/evaluation.py` to automatically filter answer key questions lists to only match the template's output columns, preventing crashes when using a 120-question CSV with a 60-question template.
* **Release & Pushing**: Pushed all updates to the remote GitHub fork repository to trigger automated cloud compilation of the Windows installer.

### Commit
`2fa619b`

---

## Step 10: PyInstaller Frozen Dynamic Loader Fix

### Goal
Resolve execution failures of compiled standalone binaries caused by dynamic walking of processors failing in frozen/bundled PyInstaller mode.

### What We Did
* **Explicit Processor Registration**: Updated `walk_package` fallback in `src/processors/manager.py` to catch loading exceptions and manually import and register the key built-in processor classes (`CropOnMarkers`, `CropPage`, `FeatureBasedAlignment`, `Levels`, `MedianBlur`, `GaussianBlur`). This ensures the OMRChecker workflow functions correctly inside single-file executables.

### Commit
`93b6345`

---

## Step 11: Auto-Extract Answer Key, Option Analysis Filtering, & GUI/Firestore Exclusions

### Goal
Allow the application to dynamically extract the answer key from the first page of the input PDF (which is the teacher's key sheet), fix key-value analysis processing errors, and ensure helper reports like `Option_Analysis.csv` are not misidentified as student submissions.

### What We Did
* **Dynamic Answer Key Extraction**: Programmed `src/entry.py` to parse the first page (`page_1.pdf`) of the scanned document, extract its responses, update the evaluation configuration dynamically, write the parsed answers to `answer_key.csv`, and output the entry with Roll Number set to `"KEY"` and File ID to `"Answer Key"`.
* **Clean Option Analysis**: Filtered columns processed in `generate_option_analysis` to only target question fields (excluding identifiers/metadata columns).
* **GUI & Database Exclusions**: Updated `index.py` to exclude `Option_Analysis.csv` from the student results table list and from Google Firestore push actions.

### Commit
`8ee0a0a`

---

## Step 12: FCM Push Notifications for Parents

### Goal
Implement a one-click "Notify All Parents" button in the Python OMR software dashboard. When clicked, it should retrieve parent FCM device tokens from Firestore and send push notifications directly to all parents belonging to the selected test.

### What We Did
* **FCM Push Notification UI & Defaults**: Added a default configuration setting `parent_tokens_collection` (default: `parent_tokens`) and added a configurable "Parent Tokens Collection" field in the Preferences GUI window.
* **GUI Button & Flow Controls**: Added a "Notify All Parents" action button next to "Push to Firestore" that is enabled when a test is selected and disabled during long-running tasks.
* **Concurrent Push Service**: Implemented background thread orchestrator `notify_parents` that fetches parent device tokens from Google Firestore (supporting roll number matching by document ID or query fields) and sends push notifications using a `ThreadPoolExecutor` targeting the official FCM v1 REST API. It reports a complete transmission summary containing counts for success, failure, and missing device registrations.

---

## Step 13: Auto-create Default Directories on Startup

### Goal
Resolve PDF upload and processing crashes caused by missing input/output base directories on fresh repository clones (since Git does not track empty folders).

### What We Did
* **Startup Directory Verification**: Added dynamic creation of default directories (inputs, outputs, templates) during settings initialization in `SettingsManager.__init__` of `index.py`.
* **Clean PR Rebasing**: Resolved git branch conflicts by rebasing onto the latest upstream `origin/main` commit to produce a clean, ready-to-merge Pull Request.


