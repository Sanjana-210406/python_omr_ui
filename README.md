# Test Manager App

A cross‑platform desktop GUI application (Tkinter) for managing test forms, processing PDFs, running external Python scripts, and uploading results to Google Firestore.

---

## Features

- **PIN‑protected access** – 6‑digit PIN with SHA‑256 hashing (default: `123456`).
- **CRUD for test forms** – each test stores a name, date, and selected template folder.
- **PDF processing** – convert PDF to images, clear input/output folders, copy a selected template (from a templates folder) into the input directory.
- **Show PDF page count** – before processing, the app displays the number of pages.
- **Run external command** – execute a custom Python command (e.g., `python3 main.py --inputDir {input} --outputDir {output}`) with placeholders for input/output directories.
- **Live CSV preview** – after the command runs, the latest CSV from the output directory is displayed in a scrollable text area.
- **Push CSV to Firestore** – upload the CSV data to a Firestore collection using a service account key.
- **Settings page** – configure input/output directories, Python command, templates folder, Firestore auth key, collection name, and change the PIN.
- **Background threading** – all long operations run in threads, keeping the UI responsive.

---

## Requirements

### Python
- Python 3.7 or higher

### Required Python Packages
- `tkinter` (usually bundled with Python)
- `PyPDF2` **or** `pypdf` (recommended)
- `pdf2image`
- `Pillow`
- `google-cloud-firestore`
- `shutil`, `subprocess`, `json`, `sqlite3`, `hashlib`, `csv`, `threading`, `datetime` – these are part of the standard library.

Install all dependencies with:

```bash
pip install pypdf pdf2image Pillow google-cloud-firestore
```

> **Note:** `pypdf` is the actively maintained fork of `PyPDF2`. The code will fallback to other methods if it’s not installed.

### Poppler (for PDF to image conversion)
`pdf2image` requires **poppler** installed on your system:

- **Windows**: download poppler binaries and add the `bin` folder to your `PATH`, or install via `conda install -c conda-forge poppler`.
- **macOS**: `brew install poppler`
- **Linux (Debian/Ubuntu)**: `sudo apt-get install poppler-utils`

Verify installation by running `pdfinfo` in a terminal – it should print usage information.

---

## Installation

1. Clone or download this repository.
2. Install the Python dependencies (see above).
3. Make sure poppler is installed and in your `PATH`.
4. Run the application:

```bash
python test_manager_app.py
```

On first run, the app creates a default configuration file (`app_config.json`) and a SQLite database (`tests.db`). The default PIN is `123456`.

---

## Configuration (Settings)

Go to **Settings → Preferences** to configure:

| Setting                  | Description |
|--------------------------|-------------|
| **Input Directory**      | Where images and template files will be placed before running your script. |
| **Output Directory**     | Where your script writes results (CSV files). |
| **Python Command**       | The full command to run your script. Use `{input}` and `{output}` as placeholders. Example: `python3 main.py --inputDir {input} --outputDir {output}`. |
| **Templates Folder**     | A directory that contains subfolders – each subfolder is a template. The app copies the contents of the selected template into the input directory during PDF processing. |
| **Firestore Auth Key**   | Path to a service account JSON file for Firestore authentication. |
| **Firestore Collection** | The collection name where CSV rows will be uploaded (default: `test_results`). |

All settings are saved automatically in `app_config.json`.

---

## How to Use

### 1. Login
Enter the 6‑digit PIN. The default is `123456`. You can change it later via **Settings → Change PIN**.

### 2. Manage Tests
- **Add Test**: fill in a name, date (YYYY-MM-DD), and choose a template folder from the dropdown (populated from your templates directory).
- **Edit / Delete**: select a test from the list and use the corresponding buttons.

### 3. Process a Test
- Select a test in the list.
- Click **Input PDF** and choose a PDF file.
- The app will show the page count and ask for confirmation.
- It then clears the input/output directories, converts each page of the PDF to a JPEG image (saved in the input directory), and copies the selected template folder’s contents into the input directory.

### 4. Run the Python Command
- Click **Run Command**.
- The configured command is executed with the `{input}` and `{output}` placeholders replaced by the actual directories.
- Any CSV file generated in the output directory is automatically displayed in the right panel.

### 5. Push to Firestore
- After the command runs and a CSV exists, click **Push to Firestore**.
- The latest CSV (by modification time) is uploaded row‑by‑row to the configured Firestore collection.
- A progress message appears in the status bar.

---

## File Structure

```
.
├── test_manager_app.py   # Main application code
├── app_config.json       # Settings (created on first run)
├── tests.db              # SQLite database for test metadata
└── README.md
```

---

## Developer Notes

### Code Overview

- **Database**: SQLite (`tests.db`) with a simple `tests` table.
- **Settings**: managed by `SettingsManager` – loads/saves JSON.
- **PDF Processing**: handled by `PDFProcessor` – uses `pypdf`/`pdfinfo` for page count, `pdf2image` for conversion.
- **Firestore Upload**: `FirestoreUploader` – uses `google-cloud-firestore`.
- **GUI**: built with `tkinter` – `TestManagerApp` is the main class.

### Adding a New Feature

- All heavy operations (PDF conversion, command execution, upload) run in background threads to avoid freezing the UI. Use the `threading` module and update the GUI via `root.after()`.
- The status bar (`self.status_var`) is updated to show progress.
- The CSV preview is a simple `ScrolledText` widget – you could replace it with a `Treeview` for a more structured table display.

### Customising the PDF Conversion

- The app saves images as JPEG. To change format or quality, modify the `process_pdf` method in `PDFProcessor`.

### Changing the Default PIN

- The default PIN is `123456` – it is hashed with SHA‑256 and stored in `app_config.json`. You can change it via the GUI or by editing the JSON manually (but the hash must be recomputed).

---

## Security Considerations

- **PIN**: Stored as a SHA‑256 hash with a fixed salt. This is not production‑grade security, but suitable for a local desktop tool.
- **Firestore**: The service account key JSON file grants full read/write access to your Firestore database. Protect it and do not commit it to version control.
- The application does not encrypt the `app_config.json` or the SQLite database – they are stored in plain text.

---

## Troubleshooting

### The app does not start or shows no window
- Ensure Tkinter is installed: `python3 -c "import tkinter; tkinter._test()"`.
- Run with `python3 test_manager_app.py 2>&1 | tee error.log` to capture errors.
- Check the working directory – the script must have write permissions to create `app_config.json` and `tests.db`.

### “Unable to get page count. Is poppler installed and in PATH?”
- Install poppler (see Requirements).
- The app tries multiple methods: `pypdf` (recommended), `pdf2image` with auto‑detected poppler path, and direct `pdfinfo` call. If you still see this error, install `pypdf` (`pip install pypdf`).
- If you manually installed poppler in a non‑standard location, you can set the `POPPLER_PATH` environment variable or modify the code to pass the path explicitly.

### Firestore upload fails
- Verify the service account JSON path is correct and the file exists.
- Ensure the service account has the **Firestore Data Owner** role (or equivalent) for the project.
- Check that your internet connection allows access to Google Cloud.

### The command runs but no CSV appears
- Make sure your script actually writes a CSV file to the output directory.
- Check the command syntax – use `{input}` and `{output}` as placeholders in the Settings.
- If your script produces a CSV with a different name, the app will still show the latest (by modification time) CSV.
