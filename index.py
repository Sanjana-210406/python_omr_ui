import os
import sys
import json
import sqlite3
import hashlib
import shutil
import threading
import subprocess
import csv
import time
from datetime import datetime
from tkinter import *
from tkinter import ttk, filedialog, messagebox, scrolledtext
from google.cloud import firestore
from google.oauth2 import service_account
import fitz
from PIL import Image, ImageTk



# ========================== CONFIGURATION ==========================
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.expanduser("~/.omr_test_manager")
    os.makedirs(DATA_DIR, exist_ok=True)
    CONFIG_FILE = os.path.join(DATA_DIR, "app_config.json")
    DB_FILE = os.path.join(DATA_DIR, "tests.db")
else:
    CONFIG_FILE = "app_config.json"
    DB_FILE = "tests.db"
PIN_SALT = "some_salt"  # Keep fixed for hashing


# ========================== DATABASE ==========================
class Database:
    def __init__(self, db_file=DB_FILE):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                template_folder TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def insert_test(self, name, date, template_folder):
        self.cursor.execute(
            "INSERT INTO tests (name, date, template_folder) VALUES (?, ?, ?)",
            (name, date, template_folder)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_all_tests(self):
        self.cursor.execute("SELECT id, name, date, template_folder FROM tests ORDER BY created_at DESC")
        return self.cursor.fetchall()

    def get_test(self, test_id):
        self.cursor.execute("SELECT id, name, date, template_folder FROM tests WHERE id=?", (test_id,))
        return self.cursor.fetchone()

    def update_test(self, test_id, name, date, template_folder):
        self.cursor.execute(
            "UPDATE tests SET name=?, date=?, template_folder=? WHERE id=?",
            (name, date, template_folder, test_id)
        )
        self.conn.commit()

    def delete_test(self, test_id):
        self.cursor.execute("DELETE FROM tests WHERE id=?", (test_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()


# ========================== SETTINGS ==========================
class SettingsManager:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.expanduser("~/OMR_Test_Manager")
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.defaults = {
            "input_dir": os.path.join(base_dir, "inputs"),
            "output_dir": os.path.join(base_dir, "outputs"),
            "python_command": "python3 main.py --inputDir {input} --outputDir {output}",
            "templates_dir": os.path.join(base_dir, "samples"),
            "firestore_auth_key": "",  # path to service account JSON
            "firestore_collection": "parents_token",
            "parent_tokens_collection": "parent_tokens",
            "students_collection": "students",
            "parent_notifications_collection": "parent_notifications",
            "pin_hash": self._hash_pin("123456")  # default PIN: 123456
        }
        self.data = self._load()
        
        # Ensure default directories are set if missing/empty in loaded config
        updated = False
        for key in ["input_dir", "output_dir", "templates_dir"]:
            platform_key = f"{key}_{sys.platform}"
            if platform_key not in self.data or not self.data[platform_key]:
                if key in self.data and self.data[key]:
                    pass
                else:
                    self.data[platform_key] = self.defaults[key]
                    updated = True
                    
        if updated or not os.path.exists(self.config_file):
            self.save()
            
        self._deploy_bundled_samples()
        
        # Ensure default directories exist on startup
        for key in ["input_dir", "output_dir", "templates_dir"]:
            path = self.get(key, raw=True)
            if path:
                os.makedirs(path, exist_ok=True)

        self.current_test_id = None

    def _deploy_bundled_samples(self):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.expanduser("~/OMR_Test_Manager")
            os.makedirs(os.path.join(base_dir, "inputs"), exist_ok=True)
            os.makedirs(os.path.join(base_dir, "outputs"), exist_ok=True)
            user_samples_dir = os.path.join(base_dir, "samples")
            if not os.path.exists(user_samples_dir) or not os.listdir(user_samples_dir):
                os.makedirs(user_samples_dir, exist_ok=True)
                bundled_samples = os.path.join(sys._MEIPASS, "samples")
                if os.path.exists(bundled_samples):
                    for item in os.listdir(bundled_samples):
                        src_item = os.path.join(bundled_samples, item)
                        dst_item = os.path.join(user_samples_dir, item)
                        try:
                            if os.path.isdir(src_item):
                                shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                            else:
                                shutil.copy2(src_item, dst_item)
                        except Exception as e:
                            print(f"Failed to copy template {item}: {e}")

    def _hash_pin(self, pin):
        return hashlib.sha256((pin + PIN_SALT).encode()).hexdigest()

    def _load(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                try:
                    return json.load(f)
                except:
                    return self.defaults.copy()
        else:
            return self.defaults.copy()

    def save(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.data, f, indent=4)

    def get(self, key, default=None, raw=False):
        if key in ["input_dir", "output_dir", "python_command", "templates_dir"]:
            platform_key = f"{key}_{sys.platform}"
            val = None
            if platform_key in self.data and self.data[platform_key]:
                val = self.data[platform_key]
            elif sys.platform == "win32" and key in self.data and self.data[key]:
                val = self.data[key]
            else:
                if getattr(sys, 'frozen', False):
                    base_dir = os.path.expanduser("~/OMR_Test_Manager")
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                defaults_map = {
                    "input_dir": os.path.join(base_dir, "inputs"),
                    "output_dir": os.path.join(base_dir, "outputs"),
                    "templates_dir": os.path.join(base_dir, "samples"),
                    "python_command": "python3 main.py --inputDir {input} --outputDir {output}"
                }
                val = defaults_map.get(key, default)
            
            # Make relative directory paths absolute relative to base_dir
            if key in ["input_dir", "output_dir", "templates_dir"] and val and not os.path.isabs(val):
                if getattr(sys, 'frozen', False):
                    base_dir = os.path.expanduser("~/OMR_Test_Manager")
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                val = os.path.abspath(os.path.join(base_dir, val))
                
            if not raw and key in ["input_dir", "output_dir"] and getattr(self, "current_test_id", None) is not None:
                val = os.path.join(val, str(self.current_test_id))
            return val
        return self.data.get(key, default)

    def set(self, key, value):
        if key in ["input_dir", "output_dir", "python_command", "templates_dir"]:
            platform_key = f"{key}_{sys.platform}"
            self.data[platform_key] = value
        else:
            self.data[key] = value
        self.save()

    def verify_pin(self, pin):
        return self._hash_pin(pin) == self.data.get("pin_hash")

    def change_pin(self, old_pin, new_pin):
        if not self.verify_pin(old_pin):
            return False
        self.data["pin_hash"] = self._hash_pin(new_pin)
        self.save()
        return True


# ========================== PDF PROCESSOR ==========================
class PDFProcessor:
    def __init__(self, settings):
        self.settings = settings

    def get_questions_in_order(self, input_dir):
        template_path = os.path.join(input_dir, "template.json")
        if not os.path.exists(template_path):
            return []
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                temp_data = json.load(f)
            field_blocks = temp_data.get("fieldBlocks", {})
            all_labels = []
            for block in field_blocks.values():
                all_labels.extend(block.get("fieldLabels", []))
            
            import re
            questions = []
            for label in all_labels:
                range_match = re.match(r'^([qQ])(\d+)\.\.(\d+)$', label)
                if range_match:
                    prefix, start, end = range_match.groups()
                    for i in range(int(start), int(end) + 1):
                        questions.append(f"q{i}")
                else:
                    single_match = re.match(r'^([qQ])(\d+)$', label)
                    if single_match:
                        prefix, num = single_match.groups()
                        questions.append(f"q{num}")
            # Sort questions numerically (q1, q2... q50)
            questions.sort(key=lambda x: int(x[1:]))
            return questions
        except Exception as e:
            print(f"Error parsing template for questions_in_order: {e}")
            return []

    def configure_answer_key(self, test_id, input_dir):
        base_input_dir = self.settings.get("input_dir", raw=True)
        
        # Check which type was uploaded
        found_ext = None
        uploaded_path = None
        for ext in [".csv", ".jpg", ".jpeg", ".png", ".json"]:
            path = os.path.join(base_input_dir, f"answer_key_{test_id}{ext}")
            if os.path.exists(path):
                found_ext = ext
                uploaded_path = path
                break
                
        if not found_ext:
            # Fallback: if no uploaded answer key is found, check if first page page_1.jpg exists in input_dir
            first_page_path = os.path.join(input_dir, "page_1.jpg")
            if os.path.exists(first_page_path):
                dst_img_name = "answer_key.jpg"
                dst_img_path = os.path.join(input_dir, dst_img_name)
                try:
                    shutil.copy2(first_page_path, dst_img_path)
                    os.remove(first_page_path)
                except Exception as e:
                    print(f"Error copying first page as answer key: {e}")
                    return

                evaluation_json_path = os.path.join(input_dir, "evaluation.json")
                if os.path.exists(evaluation_json_path):
                    try:
                        with open(evaluation_json_path, 'r') as f:
                            data = json.load(f)
                    except Exception as e:
                        print(f"Error loading evaluation.json: {e}")
                        data = {}
                else:
                    data = {}

                data["source_type"] = "csv"
                if "options" not in data:
                    data["options"] = {}
                data["options"]["answer_key_csv_path"] = "answer_key.csv"
                data["options"]["answer_key_image_path"] = dst_img_name
                data["options"]["questions_in_order"] = self.get_questions_in_order(input_dir)

                # Make sure we don't have a stray answer_key.csv left over in the folder
                stray_csv = os.path.join(input_dir, "answer_key.csv")
                if os.path.exists(stray_csv):
                    try:
                        os.remove(stray_csv)
                    except Exception as e:
                        print(f"Error removing stray CSV: {e}")

                if "marking_schemes" not in data:
                    if "marking_scheme" in data:
                        data["marking_schemes"] = data["marking_scheme"]
                    else:
                        data["marking_schemes"] = {
                            "DEFAULT": {
                                "correct": "1",
                                "incorrect": "0",
                                "unmarked": "0"
                            }
                        }
                try:
                    with open(evaluation_json_path, 'w') as f:
                        json.dump(data, f, indent=4)
                except Exception as e:
                    print(f"Error writing evaluation.json: {e}")
            return
            
        # 1. If it's a JSON file, it replaces evaluation.json
        if found_ext == ".json":
            dst_evaluation_path = os.path.join(input_dir, "evaluation.json")
            try:
                shutil.copy2(uploaded_path, dst_evaluation_path)
            except Exception as e:
                print(f"Error copying evaluation JSON: {e}")
            return
            
        # 2. If it's CSV, copy as answer_key.csv and configure evaluation.json
        if found_ext == ".csv":
            dst_csv_path = os.path.join(input_dir, "answer_key.csv")
            try:
                shutil.copy2(uploaded_path, dst_csv_path)
            except Exception as e:
                print(f"Error copying answer key CSV: {e}")
                return
                
            evaluation_json_path = os.path.join(input_dir, "evaluation.json")
            if os.path.exists(evaluation_json_path):
                try:
                    with open(evaluation_json_path, 'r') as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"Error loading evaluation.json: {e}")
                    data = {}
            else:
                data = {}
                
            data["source_type"] = "csv"
            if "options" not in data:
                data["options"] = {}
            data["options"]["answer_key_csv_path"] = "answer_key.csv"
            if "answer_key_image_path" in data["options"]:
                del data["options"]["answer_key_image_path"]
            if "marking_schemes" not in data:
                data["marking_schemes"] = {
                    "DEFAULT": {
                        "correct": "1",
                        "incorrect": "0",
                        "unmarked": "0"
                    }
                }
            try:
                with open(evaluation_json_path, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                print(f"Error writing evaluation.json: {e}")
            return
            
        # 3. If it's an Image (jpg, jpeg, png), copy as answer_key.<ext> and configure evaluation.json
        if found_ext in [".jpg", ".jpeg", ".png"]:
            # Normalize extension to .jpg or .png
            norm_ext = ".jpg" if found_ext in [".jpg", ".jpeg"] else ".png"
            dst_img_name = f"answer_key{norm_ext}"
            dst_img_path = os.path.join(input_dir, dst_img_name)
            try:
                shutil.copy2(uploaded_path, dst_img_path)
            except Exception as e:
                print(f"Error copying answer key Image: {e}")
                return
                
            evaluation_json_path = os.path.join(input_dir, "evaluation.json")
            if os.path.exists(evaluation_json_path):
                try:
                    with open(evaluation_json_path, 'r') as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"Error loading evaluation.json: {e}")
                    data = {}
            else:
                data = {}
                
            data["source_type"] = "csv"
            if "options" not in data:
                data["options"] = {}
            data["options"]["answer_key_csv_path"] = "answer_key.csv"
            data["options"]["answer_key_image_path"] = dst_img_name
            data["options"]["questions_in_order"] = self.get_questions_in_order(input_dir)
            
            # Make sure we don't have a stray answer_key.csv left over in the folder
            stray_csv = os.path.join(input_dir, "answer_key.csv")
            if os.path.exists(stray_csv):
                try:
                    os.remove(stray_csv)
                except Exception as e:
                    print(f"Error removing stray CSV: {e}")
                    
            if "marking_schemes" not in data:
                if "marking_scheme" in data:
                    data["marking_schemes"] = data["marking_scheme"]
                else:
                    data["marking_schemes"] = {
                        "DEFAULT": {
                            "correct": "1",
                            "incorrect": "0",
                            "unmarked": "0"
                        }
                    }
            try:
                with open(evaluation_json_path, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                print(f"Error writing evaluation.json: {e}")
            return

    # -------------------------------------------------------
    # Get PDF Page Count
    # -------------------------------------------------------
    def get_page_count(self, pdf_path):
        try:
            import fitz
            doc = fitz.open(pdf_path)
            return len(doc)
        except Exception as e:
            raise Exception(f"Unable to read PDF.\n\n{e}")

    # -------------------------------------------------------
    # Convert PDF to Images
    # -------------------------------------------------------
    def process_pdf(self, pdf_path, template_folder, progress_callback=None):

        base_input_dir = self.settings.get("input_dir", raw=True)
        base_output_dir = self.settings.get("output_dir", raw=True)
        templates_dir = self.settings.get("templates_dir")

        # Validate base folders
        if not os.path.exists(base_input_dir):
            raise Exception("Base input directory does not exist. Check settings.")

        if not os.path.exists(base_output_dir):
            raise Exception("Base output directory does not exist. Check settings.")

        if not os.path.exists(templates_dir):
            raise Exception("Templates directory does not exist.")

        # Resolve actual folders and create them
        input_dir = self.settings.get("input_dir")
        output_dir = self.settings.get("output_dir")
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        template_source = os.path.join(
            templates_dir,
            template_folder
        )

        if not os.path.exists(template_source):
            raise Exception(
                f"Template folder '{template_folder}' not found."
            )

        # ---------------------------------------------------
        # Clear Input & Output folders
        # ---------------------------------------------------
        for folder in [input_dir, output_dir]:

            for item in os.listdir(folder):

                path = os.path.join(folder, item)

                print("Deleting:", path)

                try:
                    if os.path.isfile(path):
                        os.remove(path)

                    elif os.path.isdir(path):
                        shutil.rmtree(path)

                except PermissionError:
                    print(f"Permission denied: {path}")
                    # Skip folders that Windows is using
                    continue

                except Exception as e:
                    print(f"Error deleting {path}: {e}")
                    continue

        # ---------------------------------------------------
        # Convert PDF to Images
        # ---------------------------------------------------
        if progress_callback:
            progress_callback("Converting PDF to Images...")

        try:
            import fitz
            doc = fitz.open(pdf_path)
            zoom = 300 / 72
            matrix = fitz.Matrix(zoom, zoom)
            page_count = len(doc)

            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=matrix)
                pix.save(os.path.join(input_dir, f"page_{i}.jpg"))

            if progress_callback:
                progress_callback(f"{page_count} pages converted.")
        except Exception as e:
            raise Exception(f"Failed to convert PDF pages: {e}")

        # ---------------------------------------------------
        # Copy Template Files
        # ---------------------------------------------------
        if progress_callback:
            progress_callback("Copying Template...")

        for item in os.listdir(template_source):

            src = os.path.join(template_source, item)
            dst = os.path.join(input_dir, item)

            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)

            else:
                shutil.copy2(src, dst)

        if progress_callback:
            progress_callback("Template copied successfully.")

        # Configure uploaded answer key if exists
        test_id = getattr(self.settings, "current_test_id", None)
        if test_id is not None:
            self.configure_answer_key(test_id, input_dir)

        return page_count

    # -------------------------------------------------------
    # Run OMR Command
    # -------------------------------------------------------
    def run_command(self, progress_callback=None):

        test_id = getattr(self.settings, "current_test_id", None)
        input_dir = self.settings.get("input_dir")
        if test_id is not None:
            self.configure_answer_key(test_id, input_dir)

        cmd_template = self.settings.get("python_command")

        input_dir = self.settings.get("input_dir")
        output_dir = self.settings.get("output_dir")

        # Determine if we should use the built-in OMRChecker or fallback to shell command
        is_default_cmd = "OMRChecker" in cmd_template or getattr(sys, 'frozen', False)

        if is_default_cmd:
            if progress_callback:
                progress_callback("Initializing built-in OMR Engine...")
            try:
                import logging
                
                # Create a custom log handler to stream logs to GUI callback
                class GUIProgressLogHandler(logging.Handler):
                    def __init__(self, callback):
                        super().__init__()
                        self.callback = callback
                    def emit(self, record):
                        try:
                            msg = self.format(record)
                            self.callback(msg)
                        except Exception:
                            pass

                # Add our handler to the root logger
                handler = GUIProgressLogHandler(progress_callback)
                handler.setFormatter(logging.Formatter('%(message)s'))
                root_logger = logging.getLogger()
                root_logger.addHandler(handler)

                try:
                    from src.entry import entry_point
                    from pathlib import Path
                    from src.utils.interaction import InteractionUtils
                    InteractionUtils.disable_gui = True
                    
                    args = {
                        "input_paths": [input_dir],
                        "output_dir": output_dir,
                        "debug": False,
                        "autoAlign": False,
                        "setLayout": False
                    }
                    
                    for root_path in args["input_paths"]:
                        entry_point(Path(root_path), args)
                        
                    if progress_callback:
                        progress_callback("OMR completed successfully.")
                        
                finally:
                    # Clean up handler
                    root_logger.removeHandler(handler)

            except Exception as e:
                import traceback
                print(traceback.format_exc())
                raise Exception(f"OMR Engine error: {e}")
        else:
            # Fallback to subprocess execution (original logic)
            cmd = (
                cmd_template
                .replace("{input}", input_dir)
                .replace("{output}", output_dir)
            )

            if progress_callback:
                progress_callback(f"Running:\n{cmd}")

            try:

                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                time.sleep(2)
                 # Show command output
                print("========== STDOUT ==========")
                print(result.stdout)

                print("========== STDERR ==========")
                print(result.stderr)

                if progress_callback:
                    progress_callback(result.stdout + "\n" + result.stderr)

                if result.returncode != 0:
                    raise Exception(result.stderr)

                if progress_callback:
                    progress_callback("OMR completed successfully.")

                return result.stdout

            except subprocess.TimeoutExpired:
                raise Exception("OMR process timed out.")

    # -------------------------------------------------------
    # CSV Files
    # -------------------------------------------------------
    def get_csv_files(self, output_dir):

        results_dir = os.path.join(output_dir, "Results")

        if not os.path.exists(results_dir):
            return []

        return [
            os.path.join(results_dir, f)
            for f in os.listdir(results_dir)
            if f.lower().endswith(".csv")
        ]

    # -------------------------------------------------------
    # Read CSV
    # -------------------------------------------------------
    def read_csv(self, csv_path):

        rows = []

        with open(
            csv_path,
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:
                rows.append(row)

        return rows
# ========================== FIRESTORE UPLOADER ==========================
class FirestoreUploader:
    def __init__(self, settings):
        self.settings = settings

    def upload_csv(self, csv_path, progress_callback=None):
        """Upload CSV data to Firestore collection."""
        auth_key_path = self.settings.get("firestore_auth_key")
        if not auth_key_path or not os.path.exists(auth_key_path):
            raise Exception("Firestore auth key file not found. Please set it in Settings.")

        collection = self.settings.get("firestore_collection", "parents_token")

        # Initialize Firestore
        credentials = service_account.Credentials.from_service_account_file(auth_key_path)
        db = firestore.Client(credentials=credentials)

        # Read CSV
        rows = []
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            raise Exception("CSV file is empty or invalid.")

        # Upload each row as a document
        batch = db.batch()
        for i, row in enumerate(rows):
            # Use auto-generated ID or use a field if available
            doc_ref = db.collection(collection).document()
            batch.set(doc_ref, row)
            if i % 500 == 499:  # Firestore batch limit is 500
                batch.commit()
                batch = db.batch()
        batch.commit()

        if progress_callback:
            progress_callback(f"Uploaded {len(rows)} rows to Firestore collection '{collection}'.")


# ========================== MAIN APPLICATION ==========================
class TestManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Test Manager")
        self.root.geometry("900x700")

        self.settings = SettingsManager()
        self.db = Database()
        self.processor = PDFProcessor(self.settings)

        # Check PIN on startup
        self.show_login()

    # ---------- LOGIN ----------
    def show_login(self):
        self.login_frame = Frame(self.root)
        self.login_frame.pack(expand=True)

        Label(self.login_frame, text="Enter 6-digit PIN", font=('Arial', 16)).pack(pady=20)
        self.pin_entry = Entry(self.login_frame, show='*', font=('Arial', 20), width=10, justify='center')
        self.pin_entry.pack(pady=10)
        self.pin_entry.bind('<Return>', lambda e: self.check_pin())
        Button(self.login_frame, text="Login", command=self.check_pin, width=15).pack(pady=10)

        self.pin_error = Label(self.login_frame, text="", fg="red")
        self.pin_error.pack()

        self.pin_entry.focus()

    def check_pin(self):
        pin = self.pin_entry.get()
        if len(pin) != 6 or not pin.isdigit():
            self.pin_error.config(text="PIN must be exactly 6 digits.")
            return
        if self.settings.verify_pin(pin):
            self.login_frame.destroy()
            self.setup_main_ui()
        else:
            self.pin_error.config(text="Invalid PIN. Try again.")
            self.pin_entry.delete(0, END)

    # ---------- MAIN UI ----------
    def setup_main_ui(self):
        # Menu bar
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        settings_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences", command=self.open_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="Change PIN", command=self.change_pin_dialog)
        settings_menu.add_separator()
        settings_menu.add_command(label="Exit", command=self.root.quit)

        # Main container with left (CRUD) and right (details/actions)
        main_paned = PanedWindow(self.root, orient=HORIZONTAL)
        main_paned.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Left frame: list of tests
        left_frame = Frame(main_paned)
        main_paned.add(left_frame, width=400)

        Label(left_frame, text="Tests", font=('Arial', 14)).pack(pady=5)

        # CRUD buttons
        crud_frame = Frame(left_frame)
        crud_frame.pack(fill=X, pady=5)
        Button(crud_frame, text="Add Test", command=self.add_test_dialog).pack(side=LEFT, padx=2)
        Button(crud_frame, text="Edit", command=self.edit_test_dialog).pack(side=LEFT, padx=2)
        Button(crud_frame, text="Delete", command=self.delete_test).pack(side=LEFT, padx=2)

        # Test list (Treeview)
        self.tree = ttk.Treeview(left_frame, columns=("ID", "Name", "Date", "Template"), show="headings", height=20)
        self.tree.heading("ID", text="ID")
        self.tree.heading("Name", text="Test Name")
        self.tree.heading("Date", text="Date")
        self.tree.heading("Template", text="Template")
        self.tree.column("ID", width=30)
        self.tree.column("Name", width=150)
        self.tree.column("Date", width=100)
        self.tree.column("Template", width=100)
        self.tree.pack(fill=BOTH, expand=True, pady=5)

        # Bind selection
        self.tree.bind('<<TreeviewSelect>>', self.on_test_select)

        # Right frame: details and actions
        right_frame = Frame(main_paned)
        main_paned.add(right_frame, width=500)

        # Test details
        self.details_frame = LabelFrame(right_frame, text="Test Details", padx=5, pady=5)
        self.details_frame.pack(fill=X, pady=5)

        self.test_info_label = Label(self.details_frame, text="Select a test", font=('Arial', 12))
        self.test_info_label.pack(anchor=W)

        # Action buttons
        action_frame = Frame(right_frame)
        action_frame.pack(fill=X, pady=5)

        self.btn_input_pdf = Button(action_frame, text="Input PDF", command=self.input_pdf, state=DISABLED)
        self.btn_input_pdf.pack(side=LEFT, padx=2)

        self.btn_run = Button(action_frame, text="Run Command", command=self.run_command, state=DISABLED)
        self.btn_run.pack(side=LEFT, padx=2)

        self.btn_push = Button(action_frame, text="Push to Firestore", command=self.push_to_firestore, state=DISABLED)
        self.btn_push.pack(side=LEFT, padx=2)

        self.btn_notify = Button(action_frame, text="Notify All Parents", command=self.notify_parents, state=DISABLED)
        self.btn_notify.pack(side=LEFT, padx=2)

        self.btn_export_csv = Button(action_frame, text="Export CSV", command=self.export_csv, state=DISABLED)
        self.btn_export_csv.pack(side=LEFT, padx=2)

        self.btn_verify = Button(action_frame, text="Verify CSV", command=self.verify_results, state=DISABLED)
        self.btn_verify.pack(side=LEFT, padx=2)

        self.btn_darken = Button(action_frame, text="Darken CSV", command=self.darken_csv, state=DISABLED)
        self.btn_darken.pack(side=LEFT, padx=2)

        # Output display area
        self.output_frame = LabelFrame(right_frame, text="CSV Output", padx=5, pady=5)
        self.output_frame.pack(fill=BOTH, expand=True, pady=5)

        self.output_text = scrolledtext.ScrolledText(self.output_frame, height=10, wrap=NONE)
        self.output_text.pack(fill=BOTH, expand=True)

        # Progress / status bar
        self.status_var = StringVar()
        self.status_var.set("Ready")
        self.status_bar = Label(self.root, textvariable=self.status_var, relief=SUNKEN, anchor=W)
        self.status_bar.pack(fill=X, side=BOTTOM, ipady=2)

        # Initially populate list
        self.refresh_test_list()

        # Store currently selected test id
        self.current_test_id = None
        self.current_test_data = None

    # ---------- TEST LIST OPERATIONS ----------
    def refresh_test_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        tests = self.db.get_all_tests()
        for test in tests:
            self.tree.insert("", END, values=test)

    def on_test_select(self, event):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            values = item['values']
            if values:
                self.current_test_id = values[0]
                self.settings.current_test_id = values[0]
                self.current_test_data = {
                    "id": values[0],
                    "name": values[1],
                    "date": values[2],
                    "template": values[3]
                }
                # Check for answer key
                base_input_dir = self.settings.get("input_dir", raw=True)
                key_status = "None"
                for ext in [".csv", ".jpg", ".jpeg", ".png", ".json"]:
                    uploaded_key = os.path.join(base_input_dir, f"answer_key_{self.current_test_id}{ext}")
                    if os.path.exists(uploaded_key):
                        key_status = f"Uploaded ({ext[1:].upper()})"
                        break
                self.test_info_label.config(text=f"Test: {values[1]} | Template: {values[3]} | Answer Key: {key_status}")
                self.btn_input_pdf.config(state=NORMAL)
                self.btn_run.config(state=NORMAL)
                self.btn_push.config(state=NORMAL)
                self.btn_notify.config(state=NORMAL)
                self.btn_export_csv.config(state=NORMAL)
                self.btn_verify.config(state=NORMAL)
                self.btn_darken.config(state=NORMAL)
                # Clear output display
                self.output_text.delete(1.0, END)
                # Check if CSV exists in output dir and display it
                self.display_latest_csv()
        else:
            self.current_test_id = None
            self.settings.current_test_id = None
            self.current_test_data = None
            self.test_info_label.config(text="Select a test")
            self.btn_input_pdf.config(state=DISABLED)
            self.btn_run.config(state=DISABLED)
            self.btn_push.config(state=DISABLED)
            self.btn_notify.config(state=DISABLED)
            self.btn_export_csv.config(state=DISABLED)
            self.btn_verify.config(state=DISABLED)
            self.btn_darken.config(state=DISABLED)

    # ---------- CRUD DIALOGS ----------
    def add_test_dialog(self):
        self._open_test_dialog("Add Test", None)

    def edit_test_dialog(self):
        if not self.current_test_id:
            messagebox.showwarning("No selection", "Please select a test to edit.")
            return
        test = self.db.get_test(self.current_test_id)
        if test:
            self._open_test_dialog("Edit Test", test)

    def _open_test_dialog(self, title, test_data):
        dialog = Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("500x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # Load template folders from templates_dir (find folders containing template.json)
        templates_dir = self.settings.get("templates_dir")
        template_options = []
        if os.path.exists(templates_dir):
            for root, dirs, files in os.walk(templates_dir):
                if "template.json" in files:
                    rel_path = os.path.relpath(root, templates_dir)
                    if rel_path != ".":
                        template_options.append(rel_path)
            template_options.sort()
        else:
            messagebox.showwarning("Templates folder not set", "Please set the templates folder in Settings.")

        # Variables
        name_var = StringVar()
        date_var = StringVar()
        template_var = StringVar()
        csv_file_path_var = StringVar()

        test_id = test_data[0] if test_data else None
        has_existing_key = False
        existing_filename = ""
        if test_id:
            base_input_dir = self.settings.get("input_dir", raw=True)
            for ext in [".csv", ".jpg", ".jpeg", ".png", ".json"]:
                path = os.path.join(base_input_dir, f"answer_key_{test_id}{ext}")
                if os.path.exists(path):
                    existing_filename = f"answer_key{ext}"
                    csv_file_path_var.set(f"Already uploaded ({existing_filename})")
                    has_existing_key = True
                    break
            if not has_existing_key:
                csv_file_path_var.set("No file selected")
        else:
            csv_file_path_var.set("No file selected")

        selected_csv = [None]
        
        def browse_csv():
            path = filedialog.askopenfilename(
                title="Select Answer Key File",
                filetypes=[
                    ("CSV Files", "*.csv"),
                    ("Image Files", "*.jpg *.jpeg *.png"),
                    ("JSON Files", "*.json"),
                    ("All Files", "*")
                ]
            )
            if path:
                ext = os.path.splitext(path)[1].lower()
                selected_csv[0] = (path, ext)
                csv_file_path_var.set(os.path.basename(path))

        def clear_csv():
            selected_csv[0] = "CLEAR"
            csv_file_path_var.set("No file selected")

        if test_data:
            name_var.set(test_data[1])
            date_var.set(test_data[2])
            template_var.set(test_data[3])

        # Layout
        Label(dialog, text="Test Name:").grid(row=0, column=0, sticky=W, padx=5, pady=5)
        Entry(dialog, textvariable=name_var, width=30).grid(row=0, column=1, padx=5, pady=5)

        Label(dialog, text="Date (YYYY-MM-DD):").grid(row=1, column=0, sticky=W, padx=5, pady=5)
        Entry(dialog, textvariable=date_var, width=30).grid(row=1, column=1, padx=5, pady=5)

        Label(dialog, text="Template Folder:").grid(row=2, column=0, sticky=W, padx=5, pady=5)
        template_combo = ttk.Combobox(dialog, textvariable=template_var, values=template_options, width=27)
        template_combo.grid(row=2, column=1, padx=5, pady=5)
        template_combo['state'] = 'readonly'
        if not template_options:
            template_combo.set("No templates found")
        elif template_var.get() and template_var.get() in template_options:
            template_combo.set(template_var.get())
        elif template_options:
            template_combo.set(template_options[0])

        Label(dialog, text="Answer Key CSV/Img/JSON:").grid(row=3, column=0, sticky=W, padx=5, pady=5)
        csv_info_frame = Frame(dialog)
        csv_info_frame.grid(row=3, column=1, sticky=W, padx=5, pady=5)
        
        csv_label = Label(csv_info_frame, textvariable=csv_file_path_var, width=20, anchor=W)
        if has_existing_key:
            csv_label.config(fg="green")
        csv_label.pack(side=LEFT)
        Button(csv_info_frame, text="Browse...", command=browse_csv).pack(side=LEFT, padx=2)
        Button(csv_info_frame, text="Clear", command=clear_csv).pack(side=LEFT, padx=2)

        def save():
            name = name_var.get().strip()
            date = date_var.get().strip()
            template = template_var.get()
            if not name or not date or not template:
                messagebox.showerror("Error", "All fields are required.")
                return
            # Validate date format
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Error", "Date must be in YYYY-MM-DD format.")
                return
            if test_data:
                # Update
                self.db.update_test(test_data[0], name, date, template)
                inserted_id = test_data[0]
            else:
                # Insert
                inserted_id = self.db.insert_test(name, date, template)
                
            # Save uploaded answer key if one was selected
            if inserted_id:
                base_input_dir = self.settings.get("input_dir", raw=True)
                os.makedirs(base_input_dir, exist_ok=True)
                
                # If we cleared or selected a new one, delete any old ones first
                if selected_csv[0] == "CLEAR" or selected_csv[0] is not None:
                    for ext in [".csv", ".jpg", ".jpeg", ".png", ".json"]:
                        old_path = os.path.join(base_input_dir, f"answer_key_{inserted_id}{ext}")
                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                            except Exception as e:
                                print(f"Error removing old key: {e}")
                                
                if selected_csv[0] is not None and selected_csv[0] != "CLEAR":
                    src_path, ext = selected_csv[0]
                    target_path = os.path.join(base_input_dir, f"answer_key_{inserted_id}{ext}")
                    try:
                        shutil.copy2(src_path, target_path)
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to save answer key file: {e}")
                        return
                        
            self.refresh_test_list()
            dialog.destroy()

        Button(dialog, text="Save", command=save, width=10).grid(row=4, column=0, pady=20)
        Button(dialog, text="Cancel", command=dialog.destroy, width=10).grid(row=4, column=1, pady=20)

    def delete_test(self):
        if not self.current_test_id:
            messagebox.showwarning("No selection", "Please select a test to delete.")
            return
        if messagebox.askyesno("Delete", "Are you sure you want to delete this test?"):
            # Delete uploaded answer key if exists
            base_input_dir = self.settings.get("input_dir", raw=True)
            for ext in [".csv", ".jpg", ".jpeg", ".png", ".json"]:
                uploaded_key = os.path.join(base_input_dir, f"answer_key_{self.current_test_id}{ext}")
                if os.path.exists(uploaded_key):
                    try:
                        os.remove(uploaded_key)
                    except Exception as e:
                        print(f"Error removing key on test delete: {e}")
                        
            self.db.delete_test(self.current_test_id)
            self.refresh_test_list()
            self.on_test_select(None)  # clear selection

    # ---------- PDF INPUT AND PROCESSING ----------
    def input_pdf(self):
        if not self.current_test_data:
            return
        # Select PDF file
        pdf_path = filedialog.askopenfilename(
            title="Select PDF file",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not pdf_path:
            return

        # Show page count
        try:
            page_count = self.processor.get_page_count(pdf_path)
            answer = messagebox.askyesno(
                "PDF Info",
                f"PDF has {page_count} pages.\nProceed with processing? This will clear input/output folders."
            )
            if not answer:
                return
        except Exception as e:
            messagebox.showerror("Error", f"Cannot read PDF: {e}")
            return

        # Process in background
        self.status_var.set("Processing PDF...")
        self.btn_input_pdf.config(state=DISABLED)
        self.btn_run.config(state=DISABLED)
        self.btn_push.config(state=DISABLED)
        self.btn_notify.config(state=DISABLED)
        self.btn_export_csv.config(state=DISABLED)
        self.btn_verify.config(state=DISABLED)

        def process():
            try:
                template = self.current_test_data["template"]
                def progress(msg):
                    self.root.after(0, lambda: self.status_var.set(msg))
                self.processor.process_pdf(pdf_path, template, progress_callback=progress)
                self.root.after(0, lambda: messagebox.showinfo("Success", "PDF processed and template copied."))
                self.root.after(0, lambda: self.status_var.set("Ready"))
                self.root.after(0, lambda: self.btn_input_pdf.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_run.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_push.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_notify.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_export_csv.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_verify.config(state=NORMAL))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.root.after(0, lambda: self.status_var.set("Error"))
                self.root.after(0, lambda: self.btn_input_pdf.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_run.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_push.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_notify.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_export_csv.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_verify.config(state=NORMAL))

        threading.Thread(target=process, daemon=True).start()

    # ---------- RUN COMMAND ----------
    def run_command(self):
        if not self.current_test_data:
            return

        # Check if PDF was loaded first
        input_dir = self.settings.get("input_dir")
        if not os.path.exists(input_dir) or not os.listdir(input_dir):
            # No PDF loaded. Check if the template folder contains sample images!
            template_folder = self.current_test_data["template"]
            templates_dir = self.settings.get("templates_dir")
            template_path = os.path.join(templates_dir, template_folder)
            
            sample_images = []
            if os.path.exists(template_path):
                for root, dirs, files in os.walk(template_path):
                    for f in files:
                        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                            if f.lower() != "omr_marker.jpg":
                                sample_images.append(os.path.join(root, f))
            
            if sample_images:
                self.status_var.set("Copying built-in sample images...")
                os.makedirs(input_dir, exist_ok=True)
                
                # Copy all files (template.json, evaluation.json, answer_key.csv, etc.) from template root
                if os.path.exists(template_path):
                    for item in os.listdir(template_path):
                        src_item = os.path.join(template_path, item)
                        dst_item = os.path.join(input_dir, item)
                        if os.path.isfile(src_item):
                            shutil.copy2(src_item, dst_item)
                    
                # Copy images
                for idx, img_path in enumerate(sample_images, start=1):
                    ext = os.path.splitext(img_path)[1]
                    shutil.copy2(img_path, os.path.join(input_dir, f"page_{idx}{ext}"))
            else:
                messagebox.showwarning("Warning", "Please load your scanned PDF sheets first by clicking the 'Input PDF' button!")
                return

        # Confirm
        if not messagebox.askyesno("Run Command", "Run the configured OMR command now?"):
            return

        self.status_var.set("Running command...")
        self.btn_run.config(state=DISABLED)
        self.btn_input_pdf.config(state=DISABLED)
        self.btn_push.config(state=DISABLED)
        self.btn_notify.config(state=DISABLED)
        self.btn_export_csv.config(state=DISABLED)
        self.btn_verify.config(state=DISABLED)

        def run():
            try:
                def progress(msg):
                    self.root.after(0, lambda: self.status_var.set(msg))
                self.processor.run_command(progress_callback=progress)
                self.root.after(0, lambda: messagebox.showinfo("Success", "Command executed successfully."))
                self.root.after(0, self.display_latest_csv)
                self.root.after(0, lambda: self.status_var.set("Ready"))
                self.root.after(0, lambda: self.btn_run.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_input_pdf.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_push.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_notify.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_export_csv.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_verify.config(state=NORMAL))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.root.after(0, lambda: self.status_var.set("Error"))
                self.root.after(0, lambda: self.btn_run.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_input_pdf.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_push.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_notify.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_export_csv.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_verify.config(state=NORMAL))

        threading.Thread(target=run, daemon=True).start()

    # ---------- DISPLAY CSV ----------
    def display_latest_csv(self):
        output_dir = self.settings.get("output_dir")
        csv_files = self.processor.get_csv_files(output_dir)
        # Exclude Option Analysis CSV from student results preview
        csv_files = [f for f in csv_files if os.path.basename(f) != "Option_Analysis.csv"]
        if csv_files:
            # Pick the most recent CSV (by file modification time)
            csv_files.sort(key=os.path.getmtime, reverse=True)
            latest = csv_files[0]
            csv_path = latest
            try:
                rows = self.processor.read_csv(csv_path)
                if rows:
                    # Display as a simple table in text area
                    self.output_text.delete(1.0, END)
                    # Filter out path columns for a cleaner display
                    headers = [h for h in rows[0].keys() if h not in ["input_path", "output_path"]]
                    
                    # Create readable display headers
                    display_headers = []
                    for h in headers:
                        if h == "file_id":
                            display_headers.append("Page")
                        elif h == "Roll_no":
                            display_headers.append("Roll No")
                        elif h.startswith("q") and h[1:].isdigit():
                            display_headers.append(h.upper())  # Q1, Q2, etc.
                        else:
                            display_headers.append(h.title())
                            
                    header_line = "\t".join(display_headers)
                    self.output_text.insert(END, header_line + "\n")
                    self.output_text.insert(END, "-" * (len(header_line) + 15) + "\n")
                    
                    for row in rows:
                        row_values = []
                        for h in headers:
                            val = row.get(h, "")
                            if h == "file_id":
                                if str(val) == "Answer Key":
                                    row_values.append("Answer Key")
                                else:
                                    clean_val = str(val).replace("page_", "").replace(".jpg", "").replace(".png", "").replace(".jpeg", "")
                                    row_values.append(f"Page {clean_val}")
                            else:
                                row_values.append(str(val))
                        line = "\t".join(row_values)
                        self.output_text.insert(END, line + "\n")
                    self.status_var.set(f"Displayed CSV: {latest}")
                else:
                    self.output_text.delete(1.0, END)
                    self.output_text.insert(END, "CSV file is empty.")
            except Exception as e:
                self.output_text.delete(1.0, END)
                self.output_text.insert(END, f"Error reading CSV: {e}")
        else:
            self.output_text.delete(1.0, END)
            self.output_text.insert(END, "No CSV files found in output directory.")

    # ---------- PUSH TO FIRESTORE ----------
    def push_to_firestore(self):
        if not self.current_test_data:
            return
        output_dir = self.settings.get("output_dir")
        csv_files = self.processor.get_csv_files(output_dir)
        # Exclude Option Analysis CSV from Firestore upload list
        csv_files = [f for f in csv_files if os.path.basename(f) != "Option_Analysis.csv"]
        if not csv_files:
            messagebox.showwarning("No CSV", "No CSV files found in output directory to push.")
            return

        # Ask which CSV to push (or push the latest)
        # For simplicity, we push the latest
        csv_files.sort(key=os.path.getmtime, reverse=True)
        csv_path = csv_files[0]
        latest = os.path.basename(csv_path)

        if not messagebox.askyesno("Push to Firestore", f"Push '{latest}' to Firestore?"):
            return

        self.status_var.set("Pushing to Firestore...")
        self.btn_push.config(state=DISABLED)
        self.btn_run.config(state=DISABLED)
        self.btn_input_pdf.config(state=DISABLED)
        self.btn_notify.config(state=DISABLED)
        self.btn_export_csv.config(state=DISABLED)
        self.btn_verify.config(state=DISABLED)

        def upload():
            try:
                uploader = FirestoreUploader(self.settings)
                def progress(msg):
                    self.root.after(0, lambda: self.status_var.set(msg))
                uploader.upload_csv(csv_path, progress_callback=progress)
                self.root.after(0, lambda: messagebox.showinfo("Success", "Data pushed to Firestore."))
                self.root.after(0, lambda: self.status_var.set("Ready"))
                self.root.after(0, lambda: self.btn_push.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_run.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_input_pdf.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_notify.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_export_csv.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_verify.config(state=NORMAL))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.root.after(0, lambda: self.status_var.set("Error"))
                self.root.after(0, lambda: self.btn_push.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_run.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_input_pdf.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_notify.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_export_csv.config(state=NORMAL))
                self.root.after(0, lambda: self.btn_verify.config(state=NORMAL))

        threading.Thread(target=upload, daemon=True).start()

    # ---------- NOTIFY PARENTS (FCM PUSH NOTIFICATIONS) ----------
    def notify_parents(self):
        if not self.current_test_data:
            return

        test_name = self.current_test_data["name"]
        test_date = self.current_test_data["date"]
        
        output_dir = self.settings.get("output_dir")
        csv_files = self.processor.get_csv_files(output_dir)
        # Exclude Option Analysis CSV from notification processing
        csv_files = [f for f in csv_files if os.path.basename(f) != "Option_Analysis.csv"]
        if not csv_files:
            messagebox.showwarning("No CSV", "No CSV files found in output directory to notify parents. Please run grading first.")
            return

        # Use the latest CSV results file
        csv_files.sort(key=os.path.getmtime, reverse=True)
        csv_path = csv_files[0]
        latest = os.path.basename(csv_path)

        auth_key_path = self.settings.get("firestore_auth_key")
        if not auth_key_path or not os.path.exists(auth_key_path):
            messagebox.showerror("Error", "Firestore auth key file not found. Please set it in Settings.")
            return

        if not messagebox.askyesno("Notify Parents", f"Send push notifications to all parents for test '{test_name}' using '{latest}'?"):
            return

        self.status_var.set("Sending notifications...")
        self.btn_push.config(state=DISABLED)
        self.btn_run.config(state=DISABLED)
        self.btn_input_pdf.config(state=DISABLED)
        self.btn_notify.config(state=DISABLED)
        self.btn_export_csv.config(state=DISABLED)
        self.btn_verify.config(state=DISABLED)

        def run_notifications():
            try:
                # 1. Initialize Firestore
                credentials = service_account.Credentials.from_service_account_file(auth_key_path)
                db = firestore.Client(credentials=credentials)

                # 2. Read CSV
                rows = self.processor.read_csv(csv_path)
                if not rows:
                    raise Exception("CSV file is empty or invalid.")

                # 3. Get Collection settings
                students_col = self.settings.get("students_collection", "students")
                parent_notifications_col = self.settings.get("parent_notifications_collection", "parent_notifications")

                processed_count = 0
                success_count = 0
                fail_count = 0
                no_student_count = 0

                # Define internal helper for student data lookup
                def get_student_data(roll_no):
                    roll_no_str = str(roll_no).strip()
                    if not roll_no_str:
                        return None
                    try:
                        # Direct doc ID check
                        doc_ref = db.collection(students_col).document(roll_no_str)
                        doc = doc_ref.get()
                        if doc.exists:
                            return doc.to_dict()
                        
                        # Query by fields
                        for field in ["roll_no", "rollNo", "rollNumber", "student_id"]:
                            snaps = db.collection(students_col).where(field, "==", roll_no_str).limit(1).stream()
                            for snap in snaps:
                                return snap.to_dict()

                        # Numeric check
                        if roll_no_str.isdigit():
                            roll_no_int = int(roll_no_str)
                            for field in ["roll_no", "rollNo", "rollNumber", "student_id"]:
                                snaps = db.collection(students_col).where(field, "==", roll_no_int).limit(1).stream()
                                for snap in snaps:
                                    return snap.to_dict()
                    except Exception as e:
                        print(f"Error querying student data for Roll No {roll_no_str}: {e}")
                    return None

                # Filter out key rows
                student_rows = []
                for row in rows:
                    roll = str(row.get("Roll_no", "")).strip()
                    file_id = str(row.get("file_id", "")).strip()
                    if roll.upper() == "KEY" or "key" in file_id.lower():
                        continue
                    if not roll:
                        continue
                    student_rows.append(row)

                processed_count = len(student_rows)
                notifications_to_write = []

                # Fetch student data for all students first
                self.root.after(0, lambda: self.status_var.set("Fetching student data from Firestore..."))
                for idx, row in enumerate(student_rows, start=1):
                    roll = str(row.get("Roll_no", "")).strip()
                    score = row.get("score", "N/A")
                    
                    self.root.after(0, lambda r=roll, i=idx: self.status_var.set(f"Querying student ({i}/{processed_count}): Roll No {r}"))
                    student_data = get_student_data(roll)
                    
                    if student_data:
                        parent_phone = student_data.get("parent_phone") or student_data.get("phone") or student_data.get("parentPhone") or student_data.get("parent_number") or ""
                        school = student_data.get("school") or student_data.get("school_name") or ""
                        school_code = student_data.get("school_code") or student_data.get("schoolCode") or ""
                        student_name = student_data.get("student_name") or student_data.get("name") or student_data.get("studentName") or ""
                        
                        notifications_to_write.append({
                            "roll_no": roll,
                            "student_name": student_name,
                            "score": score,
                            "parent_phone": parent_phone,
                            "school": school,
                            "school_code": school_code,
                            "test_name": test_name,
                            "test_date": test_date,
                            "status": "pending",
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                        success_count += 1
                    else:
                        no_student_count += 1

                # Write notifications in batch
                if notifications_to_write:
                    self.root.after(0, lambda: self.status_var.set("Writing parent notifications to Firestore..."))
                    batch = db.batch()
                    for i, notification_data in enumerate(notifications_to_write):
                        doc_id = f"{self.current_test_id}_{notification_data['roll_no']}"
                        doc_ref = db.collection(parent_notifications_col).document(doc_id)
                        batch.set(doc_ref, notification_data, merge=True)
                        if i % 500 == 499:
                            batch.commit()
                            batch = db.batch()
                    batch.commit()

                def show_result():
                    self.status_var.set("Ready")
                    self.btn_push.config(state=NORMAL)
                    self.btn_run.config(state=NORMAL)
                    self.btn_input_pdf.config(state=NORMAL)
                    self.btn_notify.config(state=NORMAL)
                    self.btn_export_csv.config(state=NORMAL)
                    self.btn_verify.config(state=NORMAL)
                    
                    summary_msg = (
                        f"Parent notifications queuing complete.\n\n"
                        f"- Total students processed: {processed_count}\n"
                        f"- Found in students collection: {success_count}\n"
                        f"- Not found in students collection: {no_student_count}\n"
                        f"- Notifications queued in Firestore: {len(notifications_to_write)}"
                    )
                    messagebox.showinfo("Notifications Queued", summary_msg)
                
                self.root.after(0, show_result)

            except Exception as e:
                def show_error(err=str(e)):
                    self.status_var.set("Error")
                    self.btn_push.config(state=NORMAL)
                    self.btn_run.config(state=NORMAL)
                    self.btn_input_pdf.config(state=NORMAL)
                    self.btn_notify.config(state=NORMAL)
                    self.btn_export_csv.config(state=NORMAL)
                    self.btn_verify.config(state=NORMAL)
                    messagebox.showerror("Error", f"Failed to queue notifications: {err}")
                self.root.after(0, show_error)

        threading.Thread(target=run_notifications, daemon=True).start()

    # ---------- DARKEN CSV ----------
    def darken_csv(self):
        if not self.current_test_id:
            messagebox.showwarning("Warning", "Please select a test first.")
            return

        input_dir = self.settings.get("input_dir")
        if not os.path.exists(input_dir):
            messagebox.showerror("Error", f"Input directory '{input_dir}' does not exist.")
            return

        exts = (".png", ".jpg", ".jpeg")
        img_files = [
            os.path.join(input_dir, f)
            for f in os.listdir(input_dir)
            if f.lower().endswith(exts) and not f.lower().startswith("omr_marker")
        ]

        if not img_files:
            messagebox.showwarning("No Sheets Found", "No scanned image sheets found in input directory. Please run 'Input PDF' first.")
            return

        if not messagebox.askyesno("Confirm Darken", f"Found {len(img_files)} sheet(s) in input folder.\nDo you want to detect and darken faint OMR bubbles?"):
            return

        self.btn_darken.config(state=DISABLED)
        self.btn_run.config(state=DISABLED)

        def process():
            try:
                from PIL import Image
                from pdf_darken import process_image
                
                total_darkened = 0
                processed_count = 0

                for img_path in sorted(img_files):
                    try:
                        pil_img = Image.open(img_path)
                        darkened_img, _, candidates = process_image(pil_img)
                        if candidates > 0:
                            darkened_img.save(img_path)
                            total_darkened += candidates
                        processed_count += 1
                        msg = f"Darkening faint bubbles: {processed_count}/{len(img_files)} sheets processed ({total_darkened} marks darkened)"
                        self.root.after(0, lambda m=msg: self.status_var.set(m))
                    except Exception as e:
                        print(f"Error darkening image {img_path}: {e}")

                done_msg = f"Darkening complete: processed {processed_count} sheet(s) and darkened {total_darkened} faint bubble mark(s)."
                self.root.after(0, lambda: self.status_var.set(done_msg))
                self.root.after(0, lambda: messagebox.showinfo("Darken Complete", done_msg))
            except Exception as e:
                err_msg = f"Failed to darken sheets: {e}"
                self.root.after(0, lambda: messagebox.showerror("Error", err_msg))
            finally:
                def reenable():
                    self.btn_darken.config(state=NORMAL)
                    self.btn_run.config(state=NORMAL)
                self.root.after(0, reenable)

        threading.Thread(target=process, daemon=True).start()

    # ---------- EXPORT CSV ----------
    def export_csv(self):
        if not self.current_test_data:
            messagebox.showwarning("No Selection", "Please select a test from the left list first.")
            return

        output_dir = self.settings.get("output_dir")
        if not output_dir or not os.path.exists(output_dir):
            messagebox.showwarning("No Data", "Output directory does not exist. Please run OMR grading first.")
            return

        # Search both output_dir/Results and output_dir for CSV files
        csv_files = []
        for root_folder in [os.path.join(output_dir, "Results"), output_dir]:
            if os.path.exists(root_folder):
                for f in os.listdir(root_folder):
                    if f.lower().endswith(".csv") and f.lower() != "option_analysis.csv":
                        csv_files.append(os.path.join(root_folder, f))

        if not csv_files:
            messagebox.showwarning("No CSV Results", "No graded CSV files found to export. Please click 'Run Command' to grade sheets first.")
            return

        # Use the latest CSV results file
        csv_files.sort(key=os.path.getmtime, reverse=True)
        src_csv_path = csv_files[0]

        test_name = self.current_test_data.get("name", "test")
        safe_test_name = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in test_name).replace(" ", "_")

        # Ask user where to save
        save_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"student_responses_{safe_test_name}.csv"
        )
        if not save_path:
            return

        try:
            with open(src_csv_path, mode='r', newline='', encoding='utf-8') as infile:
                reader = csv.DictReader(infile)
                fieldnames = reader.fieldnames or []
                
                # Identify and sort question columns (e.g. q1, q2... q60)
                q_headers = [h for h in fieldnames if (h.lower().startswith("q") and h[1:].isdigit()) or h.isdigit()]
                q_headers.sort(key=lambda x: int(x[1:]) if x.lower().startswith("q") else int(x))

                out_headers = ["Roll"] + q_headers

                rows_to_write = []
                for row in reader:
                    # Look for non-empty roll number
                    roll_val = ""
                    for key_name in ["Roll_no", "roll_no", "Roll", "roll"]:
                        val = row.get(key_name, "").strip()
                        if val:
                            roll_val = val
                            break
                    
                    file_id_val = row.get("file_id", "").strip()
                    if roll_val.upper() == "KEY" or file_id_val == "Answer Key" or file_id_val.upper() == "ANSWER KEY":
                        continue

                    # If Roll Number is empty, fall back to file_id
                    if not roll_val:
                        roll_val = file_id_val if file_id_val else "N/A"

                    # Clean file extension if roll_val came from file_id (e.g. page_2.jpg -> page_2)
                    if roll_val.lower().endswith((".jpg", ".png", ".jpeg")):
                        roll_val = os.path.splitext(roll_val)[0]

                    new_row = {"Roll": roll_val}
                    for q in q_headers:
                        new_row[q] = row.get(q, "")
                    rows_to_write.append(new_row)

            if not rows_to_write:
                messagebox.showwarning("No Student Data", "No student rows were found in the results file.")
                return

            with open(save_path, mode='w', newline='', encoding='utf-8') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=out_headers)
                writer.writeheader()
                writer.writerows(rows_to_write)

            messagebox.showinfo("Export Successful", f"Successfully exported {len(rows_to_write)} student response(s) to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}")

    # ---------- VERIFY RESULTS ----------
    def verify_results(self):
        if not self.current_test_data:
            return

        output_dir = self.settings.get("output_dir")
        checked_omr_dir = os.path.join(output_dir, "CheckedOMRs")
        csv_files = self.processor.get_csv_files(output_dir)
        csv_files = [f for f in csv_files if os.path.basename(f) != "Option_Analysis.csv"]

        if not os.path.exists(checked_omr_dir) or not csv_files:
            messagebox.showwarning("No Data", "No checked OMR images or CSV results found. Please run OMR grading first.")
            return

        # Find latest CSV
        csv_files.sort(key=os.path.getmtime, reverse=True)
        csv_path = csv_files[0]

        # Load CSV data
        csv_rows = []
        try:
            with open(csv_path, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                for row in reader:
                    csv_rows.append(row)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read results CSV: {e}")
            return

        # Find Answer Key row and Question Headers
        answer_key = {}
        q_headers = []
        for row in csv_rows:
            roll_val = ""
            for key_name in ["Roll_no", "roll_no", "Roll", "roll"]:
                if key_name in row:
                    roll_val = row[key_name].strip()
                    break
            file_id_val = row.get("file_id", "").strip()
            if roll_val.upper() == "KEY" or file_id_val == "Answer Key":
                answer_key = row
                break

        # If we have rows, extract question headers from the first row keys
        if csv_rows:
            q_headers = [h for h in csv_rows[0].keys() if h.lower().startswith("q") and h[1:].isdigit()]
            q_headers.sort(key=lambda x: int(x[1:]))

        # Index CSV data by file_id
        csv_data = {}
        for row in csv_rows:
            file_id_val = row.get("file_id", "").strip()
            if file_id_val:
                csv_data[file_id_val] = row

        # Get list of checked OMR images
        try:
            images = [f for f in os.listdir(checked_omr_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            # Sort them numerically
            def image_key(filename):
                digits = "".join([c for c in filename if c.isdigit()])
                return int(digits) if digits else 0
            images.sort(key=image_key)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to scan CheckedOMRs directory: {e}")
            return

        if not images:
            messagebox.showwarning("No Images", "No graded OMR images found in CheckedOMRs directory.")
            return

        # Create Window
        verify_win = Toplevel(self.root)
        verify_win.title(f"Verify OMR Results - {self.current_test_data['name']}")
        verify_win.geometry("1000x750")
        verify_win.transient(self.root)
        verify_win.grab_set()

        # Current page index tracker
        current_index = 0

        # Top Control Frame
        top_frame = Frame(verify_win, padx=10, pady=10)
        top_frame.pack(fill=X)

        btn_prev = Button(top_frame, text="◀ Previous", width=12)
        btn_prev.pack(side=LEFT, padx=5)

        page_label = Label(top_frame, text="Page 1 of 1", font=("Arial", 12))
        page_label.pack(side=LEFT, padx=10)

        btn_next = Button(top_frame, text="Next ▶", width=12)
        btn_next.pack(side=LEFT, padx=5)

        # Dropdown Search
        Label(top_frame, text="  Jump to:", font=("Arial", 12)).pack(side=LEFT)
        
        # Populate dropdown options
        roll_to_index = {}
        dropdown_options = []
        for idx, img_name in enumerate(images):
            row = csv_data.get(img_name, {})
            roll = ""
            for k in ["Roll_no", "roll_no", "Roll", "roll"]:
                if k in row:
                    roll = row[k].strip()
                    break
            if roll:
                label_text = f"Roll {roll} ({img_name})"
            else:
                label_text = f"Unknown ({img_name})"
            roll_to_index[label_text] = idx
            dropdown_options.append(label_text)

        combobox = ttk.Combobox(top_frame, values=dropdown_options, state="readonly", width=25)
        combobox.pack(side=LEFT, padx=5)
        if dropdown_options:
            combobox.current(0)

        # Main Split Area
        main_frame = Frame(verify_win, padx=10, pady=5)
        main_frame.pack(fill=BOTH, expand=True)

        # Left image panel
        left_panel = LabelFrame(main_frame, text="Graded OMR Sheet", padx=5, pady=5)
        left_panel.pack(side=LEFT, fill=BOTH, expand=True)

        image_label = Label(left_panel, text="Loading Image...")
        image_label.pack(fill=BOTH, expand=True)

        # Right details panel
        right_panel = LabelFrame(main_frame, text="Parsed Student Data", width=350, padx=10, pady=5)
        right_panel.pack(side=RIGHT, fill=BOTH)
        right_panel.pack_propagate(False)

        # Student Summary Headers
        info_frame = Frame(right_panel, pady=5)
        info_frame.pack(fill=X)

        roll_header = Label(info_frame, text="Roll Number: N/A", font=("Arial", 13, "bold"), anchor=W)
        roll_header.pack(fill=X, pady=2)

        score_header = Label(info_frame, text="OMR Score: N/A", font=("Arial", 13, "bold"), fg="blue", anchor=W)
        score_header.pack(fill=X, pady=2)

        # Treeview Comparison Table
        table_frame = Frame(right_panel)
        table_frame.pack(fill=BOTH, expand=True, pady=5)

        columns = ("question", "student_ans", "correct_ans", "status")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("question", text="Q#")
        tree.heading("student_ans", text="Opted")
        tree.heading("correct_ans", text="Correct")
        tree.heading("status", text="Status")

        tree.column("question", width=50, anchor=CENTER)
        tree.column("student_ans", width=70, anchor=CENTER)
        tree.column("correct_ans", width=70, anchor=CENTER)
        tree.column("status", width=130, anchor=W)

        # Scrollbar for tree
        scrollbar = ttk.Scrollbar(table_frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Tree Tags for formatting
        tree.tag_configure("correct", foreground="green")
        tree.tag_configure("incorrect", foreground="red")
        tree.tag_configure("unmarked", foreground="gray")

        # Page update function
        def update_page():
            nonlocal current_index
            if not images:
                return

            filename = images[current_index]
            image_path = os.path.join(checked_omr_dir, filename)

            # Update navigation states
            page_label.config(text=f"Page {current_index + 1} of {len(images)}")
            btn_prev.config(state=NORMAL if current_index > 0 else DISABLED)
            btn_next.config(state=NORMAL if current_index < len(images) - 1 else DISABLED)
            
            if dropdown_options:
                combobox.current(current_index)

            # Load and display image
            try:
                # Open with PIL
                img = Image.open(image_path)
                # Scale to fit left panel width/height (approx 550x650)
                max_w, max_h = 550, 650
                w, h = img.size
                scale = min(max_w / w, max_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(img)
                verify_win.image_ref = photo  # prevent garbage collection
                image_label.config(image=photo, text="")
            except Exception as ex:
                image_label.config(image="", text=f"Error loading image:\n{ex}")

            # Update parsed student details
            student_row = csv_data.get(filename, {})
            for row_k, row_v in csv_data.items():
                if os.path.splitext(filename)[0] == os.path.splitext(row_k)[0]:
                    student_row = row_v
                    break

            # Clear Tree
            for item in tree.get_children():
                tree.delete(item)

            if student_row:
                roll_val = ""
                for k in ["Roll_no", "roll_no", "Roll", "roll"]:
                    if k in student_row:
                        roll_val = student_row[k].strip()
                        break
                score_val = student_row.get("score", "N/A").strip()
                
                roll_header.config(text=f"Roll Number: {roll_val}")
                score_header.config(text=f"OMR Score: {score_val}")

                # Populate Tree Comparison
                for q in q_headers:
                    s_ans = student_row.get(q, "").strip()
                    c_ans = answer_key.get(q, "").strip()
                    
                    if s_ans == c_ans and c_ans:
                        status = "Correct"
                        tag = "correct"
                    elif not s_ans:
                        status = "Unmarked"
                        tag = "unmarked"
                    else:
                        status = f"Incorrect (Correct: {c_ans})"
                        tag = "incorrect"
                    
                    tree.insert("", END, values=(q.upper(), s_ans, c_ans, status), tags=(tag,))
            else:
                roll_header.config(text="Roll Number: N/A (Not parsed)")
                score_header.config(text="OMR Score: N/A")

        # Bind button commands
        def on_prev():
            nonlocal current_index
            if current_index > 0:
                current_index -= 1
                update_page()

        def on_next():
            nonlocal current_index
            if current_index < len(images) - 1:
                current_index += 1
                update_page()

        def on_dropdown_select(event):
            nonlocal current_index
            sel = combobox.get()
            if sel in roll_to_index:
                current_index = roll_to_index[sel]
                update_page()

        btn_prev.config(command=on_prev)
        btn_next.config(command=on_next)
        combobox.bind("<<ComboboxSelected>>", on_dropdown_select)

        # Load first page on start
        update_page()

    # ---------- SETTINGS ----------
    def open_settings(self):
        settings_win = Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("500x580")
        settings_win.transient(self.root)
        settings_win.grab_set()

        # Variables
        input_dir_var = StringVar(value=self.settings.get("input_dir", raw=True))
        output_dir_var = StringVar(value=self.settings.get("output_dir", raw=True))
        python_cmd_var = StringVar(value=self.settings.get("python_command", raw=True))
        templates_dir_var = StringVar(value=self.settings.get("templates_dir", raw=True))
        firestore_key_var = StringVar(value=self.settings.get("firestore_auth_key", raw=True))
        collection_var = StringVar(value=self.settings.get("firestore_collection", "parents_token"))
        parent_tokens_collection_var = StringVar(value=self.settings.get("parent_tokens_collection", "parent_tokens"))
        students_collection_var = StringVar(value=self.settings.get("students_collection", "students"))
        parent_notifications_collection_var = StringVar(value=self.settings.get("parent_notifications_collection", "parent_notifications"))

        def browse_dir(var):
            path = filedialog.askdirectory()
            if path:
                var.set(path)

        def browse_file(var):
            path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
            if path:
                var.set(path)

        row = 0
        Label(settings_win, text="Input Directory:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=input_dir_var, width=40).grid(row=row, column=1, padx=5)
        Button(settings_win, text="Browse", command=lambda: browse_dir(input_dir_var)).grid(row=row, column=2, padx=5)
        row += 1

        Label(settings_win, text="Output Directory:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=output_dir_var, width=40).grid(row=row, column=1, padx=5)
        Button(settings_win, text="Browse", command=lambda: browse_dir(output_dir_var)).grid(row=row, column=2, padx=5)
        row += 1

        Label(settings_win, text="Python Command (use {input} and {output}):").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=python_cmd_var, width=50).grid(row=row, column=1, columnspan=2, padx=5)
        row += 1

        Label(settings_win, text="Templates Folder:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=templates_dir_var, width=40).grid(row=row, column=1, padx=5)
        Button(settings_win, text="Browse", command=lambda: browse_dir(templates_dir_var)).grid(row=row, column=2, padx=5)
        row += 1

        Label(settings_win, text="Firestore Auth Key (JSON):").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=firestore_key_var, width=40).grid(row=row, column=1, padx=5)
        Button(settings_win, text="Browse", command=lambda: browse_file(firestore_key_var)).grid(row=row, column=2, padx=5)
        row += 1

        Label(settings_win, text="Results Collection:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=collection_var, width=30).grid(row=row, column=1, padx=5, columnspan=2, sticky=W)
        row += 1

        Label(settings_win, text="Parent Tokens Collection:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=parent_tokens_collection_var, width=30).grid(row=row, column=1, padx=5, columnspan=2, sticky=W)
        row += 1

        Label(settings_win, text="Students Collection:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=students_collection_var, width=30).grid(row=row, column=1, padx=5, columnspan=2, sticky=W)
        row += 1

        Label(settings_win, text="Parent Notifications Col:").grid(row=row, column=0, sticky=W, padx=5, pady=5)
        Entry(settings_win, textvariable=parent_notifications_collection_var, width=30).grid(row=row, column=1, padx=5, columnspan=2, sticky=W)
        row += 1

        def save_settings():
            self.settings.set("input_dir", input_dir_var.get())
            self.settings.set("output_dir", output_dir_var.get())
            self.settings.set("python_command", python_cmd_var.get())
            self.settings.set("templates_dir", templates_dir_var.get())
            self.settings.set("firestore_auth_key", firestore_key_var.get())
            self.settings.set("firestore_collection", collection_var.get())
            self.settings.set("parent_tokens_collection", parent_tokens_collection_var.get())
            self.settings.set("students_collection", students_collection_var.get())
            self.settings.set("parent_notifications_collection", parent_notifications_collection_var.get())
            messagebox.showinfo("Settings", "Settings saved.")
            settings_win.destroy()

        Button(settings_win, text="Save", command=save_settings, width=10).grid(row=row, column=0, pady=10)
        Button(settings_win, text="Cancel", command=settings_win.destroy, width=10).grid(row=row, column=1, pady=10)

    # ---------- CHANGE PIN ----------
    def change_pin_dialog(self):
        pin_win = Toplevel(self.root)
        pin_win.title("Change PIN")
        pin_win.geometry("350x200")
        pin_win.transient(self.root)
        pin_win.grab_set()

        Label(pin_win, text="Current PIN:").grid(row=0, column=0, padx=5, pady=5, sticky=W)
        old_pin = Entry(pin_win, show='*', width=10)
        old_pin.grid(row=0, column=1, padx=5, pady=5)

        Label(pin_win, text="New PIN:").grid(row=1, column=0, padx=5, pady=5, sticky=W)
        new_pin = Entry(pin_win, show='*', width=10)
        new_pin.grid(row=1, column=1, padx=5, pady=5)

        Label(pin_win, text="Confirm New PIN:").grid(row=2, column=0, padx=5, pady=5, sticky=W)
        confirm_pin = Entry(pin_win, show='*', width=10)
        confirm_pin.grid(row=2, column=1, padx=5, pady=5)

        def change():
            old = old_pin.get()
            new = new_pin.get()
            confirm = confirm_pin.get()
            if not old or not new or not confirm:
                messagebox.showerror("Error", "All fields are required.")
                return
            if len(new) != 6 or not new.isdigit():
                messagebox.showerror("Error", "PIN must be 6 digits.")
                return
            if new != confirm:
                messagebox.showerror("Error", "New PINs do not match.")
                return
            if self.settings.change_pin(old, new):
                messagebox.showinfo("Success", "PIN changed successfully.")
                pin_win.destroy()
            else:
                messagebox.showerror("Error", "Current PIN is incorrect.")

        Button(pin_win, text="Change", command=change, width=10).grid(row=3, column=0, pady=10)
        Button(pin_win, text="Cancel", command=pin_win.destroy, width=10).grid(row=3, column=1, pady=10)


# ========================== ENTRY POINT ==========================
if __name__ == "__main__":
    try:
        root = Tk()
        app = TestManagerApp(root)
        root.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")