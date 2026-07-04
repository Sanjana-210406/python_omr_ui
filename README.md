# Test Manager Application - Setup & User Manual

This repository contains a cross-platform desktop GUI application (Tkinter) for managing OMR test forms, converting scanned PDFs into images, executing OMR evaluations, and syncing results with Google Firestore.

This guide is structured into two parts:
1. **Developer & Admin Setup**: For the technical team preparing, configuring, and maintaining the software.
2. **School Setup & End-User Guide**: For school administrators and teachers running the software daily to process OMR sheets.

---

# PART 1: Developer & Admin Setup (Technical Team)

This section explains the code architecture, how to configure Firestore, prepare OMR templates, and package settings.

## 1. Local Database & Config Architecture
* **SQLite Database (`tests.db`)**: Holds exam metadata (ID, test name, date, template folder name) in a flat table named `tests`.
* **Config File (`app_config.json`)**: Stores file paths, execution commands, and the default PIN. 
  * The configuration supports platform-specific keys (e.g. `python_command_win32` vs `python_command_darwin`) to allow seamless usage across both Windows and macOS machines.

## 2. Google Cloud Firestore Setup
To enable cloud synchronization of OMR results, configure Google Firestore:
1. Create a Firebase/Google Cloud Project.
2. Enable **Firestore Database** in Native mode.
3. Go to **IAM & Admin → Service Accounts** in the GCP Console.
4. Create a service account and assign the role **Cloud Datastore User** or **Firestore Data Owner**.
5. Generate and download a new private key in **JSON** format.
6. Provide this JSON file to the school administrators to load into their preferences.

## 3. Creating & Packaging OMR Templates
OMR Checker templates must be placed inside the `samples` (or `templates_dir`) folder. Each template must be a subdirectory containing:
* `template.json`: Configures bubble layout coordinate maps.
* `evaluation.json`: Configures the grading weights. Make sure it uses `"marking_schemes"` (plural) to comply with OMRChecker specifications.
* `answer_key.csv`: A CSV map containing correct answers for all questions.
* `omr_marker.jpg`: Alignment marker asset.

## 4. Administrative Security (PIN Hashing)
The login screen is protected by a 6-digit PIN.
* PIN salt is set via `PIN_SALT` inside `index.py`.
* The hash is computed using SHA-256 and stored as `pin_hash` inside `app_config.json`.
* Default PIN is `123456`. You can update it using the GUI's **Settings → Change PIN** option.

## 5. Building Standalone Installers
You can package this application into a standalone executable that runs without requiring Python or other libraries installed on the target machine.

* **macOS Installer (`.dmg`)**:
  Run the build script on a Mac computer:
  ```bash
  python3 build_installer.py
  ```
  This creates `dist/OMRTestManager.app` and packages it into `dist/OMRTestManager.dmg`.
* **Windows Executable (`.exe`)**:
  Run the batch script on a Windows computer:
  ```cmd
  build_installer_win.bat
  ```
  This installs packages and compiles the app into a single executable `dist/OMRTestManager.exe`.
* **Automated Cloud Builds (GitHub Actions)**:
  Every push to the `main` or `mac-compatibility-and-fixes` branches triggers a GitHub Actions workflow. You can download the pre-compiled `OMRTestManager.exe` directly from the **Actions** tab of your repository.

---

# PART 2: School Setup & End-User Guide (School Staff)

Welcome! This guide will help you install and run the Test Manager software on your school computers.

## 1. Prerequisites (Installation)

### Python Installation
* Make sure Python 3.7 or higher is installed on your computer.

### Package Installation
Open your terminal (macOS) or Command Prompt (Windows) and install the required modules:
```bash
pip install Pillow pymupdf google-cloud-firestore opencv-python deepmerge dotmap jsonschema matplotlib numpy pandas rich screeninfo
```

---

## 2. Configuration & Preferences
1. Run the application:
   ```bash
   python3 index.py
   ```
2. Log in using your 6-digit PIN (Default: `123456`).
3. In the menu bar, go to **Settings → Preferences**.
4. Configure the folders:
   * **Input Directory**: Create a folder on your computer (e.g., `inputs`) and select it. This is where scanned pages will be prepared.
   * **Output Directory**: Create a folder on your computer (e.g., `outputs`) and select it. This is where graded CSV results will be saved.
   * **Templates Folder**: Choose the folder where your OMR templates are stored (e.g., `samples`).
   * **Python Command**: Enter the path to your OMR evaluation script. Use `{input}` and `{output}` as placeholders:
     * *Windows Example:* `py C:\OMRChecker-master\main.py --inputDir {input} --outputDir {output}`
     * *macOS Example:* `python3 /Users/yourusername/OMRChecker-master/main.py --inputDir {input} --outputDir {output}`
   * **Firestore Auth Key**: Browse and load the Google Cloud credentials JSON file provided by your technical team.
   * **Firestore Collection**: Set the database collection name (default: `test_results`).
5. Click **Save**.

---

## 3. Standard Workflow (How to process exams)

Follow these steps for every OMR test you need to grade:

### Step A: Add a Test Exam
1. Click **Add Test** on the dashboard.
2. Enter the **Test Name** and **Date (YYYY-MM-DD)**.
3. Select the appropriate layout template from the **Template Folder** dropdown list.
4. Click **Save**.

### Step B: Load and Convert the Scan PDF
1. Select your test from the left-hand menu.
2. Click **Input PDF**.
3. Choose the scanned PDF containing all student answer sheets.
4. Confirm the page count on the pop-up window. The app will automatically split the PDF into page images and copy the layout template.

### Step C: Run OMR Grading
1. Click **Run Command**.
2. Click **Yes** to confirm.
3. The OMR engine will grade the sheets. Once finished, a table preview of the results containing student scores, Roll Numbers, and marked answers will load automatically on the right panel.

### Step D: Sync Results with Cloud
1. Click **Push to Firestore**.
2. Confirm the prompt to upload. 
3. The results will be pushed directly to your school cloud database!

---

## 4. Troubleshooting Guide for Staff
* **Error: "Template folder '...' not found."**
  * Check that your **Templates Folder** in Preferences contains the folder name selected for this test.
* **The CSV Preview shows old values or doesn't update.**
  * Click on another test name on the left sidebar and click back to force the preview window to reload.
* **Error: "Firestore Auth Key not found."**
  * Go to **Settings → Preferences** and check that you have selected a valid credentials JSON key file.
