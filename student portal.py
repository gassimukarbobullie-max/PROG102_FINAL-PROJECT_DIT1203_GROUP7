
import sqlite3
import os
import csv
from datetime import datetime, timedelta

# ── Third-party imports with graceful fallbacks
try:
    import customtkinter as ctk
except ImportError:
    raise ImportError(
        "customtkinter is not installed.\n"
        "Install it via: pip install customtkinter"
    )

try:
    from PIL import Image, ImageEnhance, ImageTk
except ImportError:
    Image = None
    ImageEnhance = None
    ImageTk = None

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    from tkinter import messagebox


    # Fallback wrapper so the rest of the code can call CTkMessagebox uniformly
    class CTkMessagebox:
        def __init__(self, **kwargs):
            self.msg = kwargs.get("message", "")
            self.title = kwargs.get("title", "Alert")
            self.icon = kwargs.get("icon", "info")

        def get(self):
            icon = str(self.icon).lower()
            if "warning" in icon or "cancel" in icon or "question" in icon:
                answer = messagebox.askyesno(self.title, self.msg)
                return "Delete" if answer else "Cancel"
            else:
                messagebox.showinfo(self.title, self.msg)
                return "OK"

# ============================================================
# SECTION 1 – CONSTANTS & GLOBAL STYLE TOKENS
# ============================================================

# Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Colour palette (Sierra Leone flag green/blue inspired)
APP_BG = "#0F172A"  # deep navy — page background
CARD_BG = "#1E293B"  # slate card background
PRIMARY_BLUE = "#2563EB"  # primary action blue
SUCCESS_GREEN = "#10B981"  # pass / active indicator
WARNING_ORANGE = "#F59E0B"  # warning / moderate GPA
DANGER_RED = "#EF4444"  # fail / at-risk indicator
MUTED_TEXT = "#94A3B8"  # secondary text
WHITE = "#F8FAFC"  # primary text on dark bg
INPUT_BG = "#0F172A"  # input background
BORDER_COLOR = "#334155"  # border color for inputs

# GPA scale (standard 4.0 system)
GRADE_GPA_MAP: dict[str, float] = {
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D": 1.0,
    "F": 0.0,
}

# Academic thresholds
GPA_PASS_THRESHOLD = 2.0  # minimum GPA to be "Active"
GPA_HONOURS_THRESHOLD = 3.5  # honours / distinction level
AT_RISK_THRESHOLD = 2.0  # students below this are "At Risk"
NEW_ENROL_DAYS = 30  # days window for "new enrolment" stat

# Demo credentials
DEMO_USERNAME = "admin"
DEMO_PASSWORD = "admin123"

# Database file
DB_FILE = "limkokwing_sl_students.db"


# ============================================================
# SECTION 2 – BUSINESS LOGIC (separated from GUI)
# ============================================================

def calculate_gpa_from_grade(grade: str) -> float:
    """
    Convert a letter grade string to its GPA point equivalent.
    Uses the GRADE_GPA_MAP constant.
    Returns 0.0 for unrecognised grades.
    """
    return GRADE_GPA_MAP.get(grade.strip(), 0.0)


def calculate_average_gpa(gpa_values: list) -> float:
    """
    Compute the arithmetic mean of a list of GPA floats.
    Returns 0.0 if the list is empty.
    """
    if not gpa_values:
        return 0.0
    total = 0.0
    for value in gpa_values:
        total += value
    return round(total / len(gpa_values), 2)


def determine_student_status(average_gpa: float) -> str:
    """
    Classify a student's enrolment status based on their cumulative GPA.
    Decision structure: if / elif / else
    """
    if average_gpa >= GPA_HONOURS_THRESHOLD:
        return "Distinction"
    elif average_gpa >= GPA_PASS_THRESHOLD:
        return "Active"
    elif average_gpa > 0.0:
        return "At Risk"
    else:
        return "Active"  # newly enrolled, no grades yet


def calculate_pass_rate(total: int, passing: int) -> str:
    """
    Calculate and format the percentage of passing students.
    Avoids division by zero with a guard clause.
    """
    if total == 0:
        return "0%"
    rate = (passing / total) * 100
    return f"{round(rate)}%"


def validate_student_id(sid: str) -> bool:
    """
    Validate that a student ID follows the pattern SL followed by digits.
    Returns True if valid, False otherwise.
    """
    sid = sid.strip()
    if len(sid) < 3:
        return False
    prefix = sid[:2].upper()
    digits = sid[2:]
    return prefix == "SL" and digits.isdigit()


def validate_email(email: str) -> bool:
    """
    Basic email validation: must contain '@' and a '.' after it.
    """
    email = email.strip()
    if "@" not in email:
        return False
    parts = email.split("@")
    return len(parts) == 2 and "." in parts[1]


def validate_phone(phone: str) -> bool:
    """
    Validate phone: must be numeric (allowing leading '+') and 7-15 digits.
    """
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    return cleaned.isdigit() and 7 <= len(cleaned) <= 15


def get_grade_colour(gpa: float) -> str:
    """
    Return a colour hex string corresponding to GPA performance level.
    Uses if / elif / else decision structure.
    """
    if gpa >= GPA_HONOURS_THRESHOLD:
        return SUCCESS_GREEN
    elif gpa >= GPA_PASS_THRESHOLD:
        return WARNING_ORANGE
    else:
        return DANGER_RED


def load_logo_image(size=(60, 60)):
    """Load and resize the logo image for display."""
    logo_path = "logo.jpeg"
    if Image and os.path.exists(logo_path):
        try:
            img = Image.open(logo_path)
            # Resize maintaining aspect ratio
            img.thumbnail(size, Image.LANCZOS)
            return ctk.CTkImage(img, size=img.size)
        except Exception:
            return None
    return None


# ============================================================
# SECTION 3 – DATABASE SETUP & QUERIES
# ============================================================

def init_database() -> None:
    """
    Initialise the SQLite database.
    Creates tables if they do not exist and seeds demo data on first run.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id    TEXT PRIMARY KEY,
            full_name     TEXT NOT NULL,
            gender        TEXT,
            email         TEXT,
            phone         TEXT,
            program       TEXT,
            study_year    INTEGER,
            cumulative_gpa REAL DEFAULT 0.0,
            status        TEXT DEFAULT 'Active',
            enrolled_date DATE
        )
    """)

    # Courses table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            course_code  TEXT PRIMARY KEY,
            course_name  TEXT NOT NULL,
            credit_hours INTEGER,
            lecturer     TEXT,
            program      TEXT,
            status       TEXT DEFAULT 'Active'
        )
    """)

    # Results / grades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            result_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   TEXT,
            student_name TEXT,
            semester     TEXT,
            course_code  TEXT,
            grade        TEXT,
            gpa_points   REAL,
            entry_date   DATE
        )
    """)

    # ── Seed demo data only on first run ─────────────────────
    if cursor.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
        today = datetime.now().strftime("%Y-%m-%d")
        demo_students = [
            ("SL1001", "Mohamed Kamara", "Male", "mkamara@limkokwing.edu.sl", "+23276543210", "Software Engineering", 2,
             3.70, "Active", today),
            ("SL1002", "Fatmata Koroma", "Female", "fkoroma@limkokwing.edu.sl", "+23278901234", "Multimedia Design", 3,
             3.30, "Active", today),
            ("SL1003", "Ibrahim Bangura", "Male", "ibangura@limkokwing.edu.sl", "+23275678901", "Architecture", 1, 1.70,
             "At Risk", today),
            ("SL1004", "Aminata Sesay", "Female", "amsesay@limkokwing.edu.sl", "+23277654321", "Business Management", 4,
             3.85, "Distinction", today),
            ("SL1005", "Abdul Conteh", "Male", "aconteh@limkokwing.edu.sl", "+23279012345", "Mass Communication", 2,
             2.30, "Active", today),
        ]
        cursor.executemany(
            "INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?,?)",
            demo_students
        )

    if cursor.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
        demo_courses = [
            ("PROG103", "Principle of Structured Programming", 3, "Mr. Elijah Fullah", "Software Engineering",
             "Active"),
            ("SE204", "Data Structures & Algorithms", 4, "Dr. Samuel Koroma", "Software Engineering", "Active"),
            ("MMD102", "Digital Graphic Design", 3, "Ms. Grace Bangura", "Multimedia Design", "Active"),
            ("ARCH103", "Architectural Drawing", 4, "Ar. James Conteh", "Architecture", "Active"),
            ("BUS201", "Principles of Marketing", 3, "Dr. Mary Kamara", "Business Management", "Active"),
            ("COM105", "Media & Communication Skills", 3, "Mr. David Sesay", "Mass Communication", "Active"),
        ]
        cursor.executemany(
            "INSERT INTO courses VALUES (?,?,?,?,?,?)",
            demo_courses
        )

    if cursor.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0:
        today = datetime.now().strftime("%Y-%m-%d")
        demo_results = [
            (None, "SL1001", "Mohamed Kamara", "Semester 2", "PROG103", "A-", 3.7, today),
            (None, "SL1002", "Fatmata Koroma", "Semester 3", "MMD102", "B+", 3.3, today),
            (None, "SL1003", "Ibrahim Bangura", "Semester 1", "ARCH103", "C-", 1.7, today),
            (None, "SL1004", "Aminata Sesay", "Semester 4", "BUS201", "A", 4.0, today),
            (None, "SL1005", "Abdul Conteh", "Semester 2", "COM105", "C+", 2.3, today),
        ]
        cursor.executemany(
            "INSERT INTO results VALUES (?,?,?,?,?,?,?,?)",
            demo_results
        )

    conn.commit()
    conn.close()


def db_get_all_students(search_term: str = "") -> list:
    """Retrieve students filtered by an optional search string."""
    conn = sqlite3.connect(DB_FILE)
    pattern = f"%{search_term}%"
    rows = conn.execute(
        "SELECT student_id, full_name, program, cumulative_gpa, status "
        "FROM students WHERE student_id LIKE ? OR full_name LIKE ?",
        (pattern, pattern)
    ).fetchall()
    conn.close()
    return rows


def db_get_student_by_id(student_id: str) -> tuple | None:
    """Fetch a single student record by ID."""
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT * FROM students WHERE student_id = ?", (student_id,)
    ).fetchone()
    conn.close()
    return row


def db_recalculate_student_gpa(student_id: str, conn: sqlite3.Connection) -> None:
    """
    Recalculate a student's cumulative GPA from all their result records
    and update the students table accordingly.
    This keeps GPA always consistent with entered grades.
    """
    gpa_rows = conn.execute(
        "SELECT gpa_points FROM results WHERE student_id = ?", (student_id,)
    ).fetchall()

    gpa_values = [row[0] for row in gpa_rows]
    new_avg_gpa = calculate_average_gpa(gpa_values)
    new_status = determine_student_status(new_avg_gpa)

    conn.execute(
        "UPDATE students SET cumulative_gpa = ?, status = ? WHERE student_id = ?",
        (new_avg_gpa, new_status, student_id)
    )


def db_save_student(data: tuple, editing_id: str | None) -> tuple[bool, str]:
    """
    Insert a new student or update an existing one.
    Returns (success: bool, message: str).
    """
    conn = sqlite3.connect(DB_FILE)
    try:
        if editing_id:
            # Update all fields except ID and enrolled date
            conn.execute(
                "UPDATE students SET full_name=?, gender=?, email=?, phone=?, "
                "program=?, study_year=? WHERE student_id=?",
                data
            )
            msg = f"Student {editing_id} updated successfully."
        else:
            conn.execute(
                "INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?,?)", data
            )
            msg = f"Student {data[0]} registered successfully."
        conn.commit()
        return True, msg
    except sqlite3.IntegrityError:
        return False, f"Student ID '{data[0]}' already exists in the database."
    except Exception as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def db_delete_student(student_id: str) -> None:
    """Remove a student and all their results from the database."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    conn.execute("DELETE FROM results WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()


def db_save_grade(student_combo: str, semester: str,
                  course_combo: str, grade: str) -> tuple[bool, str]:
    """
    Record a grade for a student, then recalculate their cumulative GPA.
    Returns (success: bool, message: str).
    """
    if not student_combo or " - " not in student_combo:
        return False, "Please select a student."
    if not grade:
        return False, "Please select a grade."
    if not semester:
        return False, "Please select a semester."
    if not course_combo or ":" not in course_combo:
        return False, "Please select a course."

    sid = student_combo.split(" - ")[0].strip()
    sname = student_combo.split(" - ")[1].strip()
    course_code = course_combo.split(":")[0].strip()
    gpa_points = calculate_gpa_from_grade(grade)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute(
            "INSERT INTO results VALUES (NULL,?,?,?,?,?,?,?)",
            (sid, sname, semester, course_code, grade, gpa_points, today)
        )
        db_recalculate_student_gpa(sid, conn)
        conn.commit()
        return True, (
            f"Grade '{grade}' saved for {sname}.\n"
            f"GPA points awarded: {gpa_points:.1f}\n"
            f"Cumulative GPA recalculated automatically."
        )
    except Exception as e:
        return False, f"Save failed: {str(e)}"
    finally:
        conn.close()


def db_get_dashboard_stats() -> dict:
    """Fetch all figures needed by the dashboard in one database round-trip."""
    conn = sqlite3.connect(DB_FILE)
    cutoff = (datetime.now() - timedelta(days=NEW_ENROL_DAYS)).strftime("%Y-%m-%d")
    stats = {
        "total_students": conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "new_enrolments": conn.execute(
            "SELECT COUNT(*) FROM students WHERE enrolled_date >= ?", (cutoff,)
        ).fetchone()[0],
        "active_courses": conn.execute(
            "SELECT COUNT(*) FROM courses WHERE status='Active'"
        ).fetchone()[0],
        "avg_gpa": conn.execute(
            "SELECT AVG(cumulative_gpa) FROM students"
        ).fetchone()[0] or 0.0,
    }
    conn.close()
    stats["avg_gpa"] = round(stats["avg_gpa"], 2)
    return stats


def db_get_results_stats() -> dict:
    """Fetch statistics needed by the Results page."""
    conn = sqlite3.connect(DB_FILE)
    total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    passing = conn.execute(
        "SELECT COUNT(*) FROM students WHERE cumulative_gpa >= ?", (GPA_PASS_THRESHOLD,)
    ).fetchone()[0]
    avg_gpa = conn.execute("SELECT AVG(cumulative_gpa) FROM students").fetchone()[0] or 0.0
    top_row = conn.execute(
        "SELECT full_name FROM students ORDER BY cumulative_gpa DESC LIMIT 1"
    ).fetchone()
    at_risk = conn.execute(
        "SELECT COUNT(*) FROM students WHERE cumulative_gpa > 0 AND cumulative_gpa < ?",
        (AT_RISK_THRESHOLD,)
    ).fetchone()[0]
    results = conn.execute(
        "SELECT student_id, student_name, semester, course_code, grade, gpa_points "
        "FROM results ORDER BY entry_date DESC"
    ).fetchall()
    students = [f"{r[0]} - {r[1]}" for r in conn.execute(
        "SELECT student_id, full_name FROM students"
    ).fetchall()]
    courses = [f"{r[0]}: {r[1]}" for r in conn.execute(
        "SELECT course_code, course_name FROM courses"
    ).fetchall()]
    conn.close()
    return {
        "avg_gpa": round(avg_gpa, 2),
        "pass_rate": calculate_pass_rate(total, passing),
        "top_student": top_row[0] if top_row else "None",
        "at_risk": at_risk,
        "results": results,
        "students": students,
        "courses": courses,
    }


def db_get_report_data() -> dict:
    """Fetch all data needed for the Reports & Analytics page."""
    conn = sqlite3.connect(DB_FILE)
    total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    by_program = conn.execute(
        "SELECT program, COUNT(*) FROM students GROUP BY program"
    ).fetchall()
    top_students = conn.execute(
        "SELECT full_name, cumulative_gpa FROM students ORDER BY cumulative_gpa DESC LIMIT 3"
    ).fetchall()
    at_risk = conn.execute(
        "SELECT full_name, cumulative_gpa FROM students "
        "WHERE cumulative_gpa > 0 AND cumulative_gpa < ?", (AT_RISK_THRESHOLD,)
    ).fetchall()
    all_students = conn.execute("SELECT * FROM students").fetchall()
    conn.close()
    return {
        "total": total,
        "by_program": by_program,
        "top_students": top_students,
        "at_risk": at_risk,
        "all_students": all_students,
    }


# ============================================================
# SECTION 4 – LOGIN PAGE
# ============================================================

class LoginPage(ctk.CTkFrame):
    """
    Login screen shown before accessing the main system.
    Validates credentials against DEMO_USERNAME / DEMO_PASSWORD constants.
    """

    def __init__(self, parent, on_login_success):
        super().__init__(parent, fg_color=APP_BG)
        self.on_login_success = on_login_success
        self._show_password = False
        self._build_ui()

    def _build_ui(self):
        # Optional background image (campus.jpg if present)
        if Image and os.path.exists("campus.jpg"):
            try:
                raw = Image.open("campus.jpg").resize((1280, 720))
                dark = ImageEnhance.Brightness(raw).enhance(0.35)
                bg_img = ctk.CTkImage(dark, size=(1280, 720))
                ctk.CTkLabel(self, image=bg_img, text="").place(x=0, y=0)
            except Exception:
                pass

        # Centred login card
        card = ctk.CTkFrame(self, width=420, height=520,
                            fg_color=CARD_BG, corner_radius=16)
        card.place(relx=0.5, rely=0.5, anchor="center")

        # ── Logo ──────────────────────────────────────────────
        logo_img = load_logo_image((80, 80))
        if logo_img:
            logo_label = ctk.CTkLabel(card, image=logo_img, text="")
            logo_label.pack(pady=(25, 4))
        else:
            # Fallback to text emoji if logo not found
            ctk.CTkLabel(card, text="🏛️", font=("Segoe UI", 50)).pack(pady=(25, 4))

        ctk.CTkLabel(card, text="LIMKOKWING",
                     font=("Segoe UI", 24, "bold"),
                     text_color=WHITE).pack(pady=(4, 2))
        ctk.CTkLabel(card,
                     text="University of Creative Technology\nSierra Leone Campus",
                     font=("Segoe UI", 12), text_color=MUTED_TEXT,
                     justify="center").pack(pady=(2, 30))

        self.email_input = ctk.CTkEntry(
            card, width=320, height=44,
            placeholder_text="Username / Staff ID", corner_radius=8,
            font=("Segoe UI", 13)
        )
        self.email_input.pack(pady=6)

        self.password_input = ctk.CTkEntry(
            card, width=320, height=44,
            placeholder_text="Password", show="*", corner_radius=8,
            font=("Segoe UI", 13)
        )
        self.password_input.pack(pady=6)
        self.password_input.bind("<Return>", lambda _: self._validate_login())

        # Show/hide password button
        ctk.CTkButton(
            self.password_input, text="👁", width=30,
            fg_color="transparent", hover_color=CARD_BG,
            command=self._toggle_password
        ).place(relx=0.92, rely=0.5, anchor="e")

        remember_row = ctk.CTkFrame(card, fg_color="transparent")
        remember_row.pack(fill="x", padx=50, pady=12)
        ctk.CTkCheckBox(remember_row, text="Remember me",
                        text_color=MUTED_TEXT, border_color=PRIMARY_BLUE).pack(side="left")
        ctk.CTkLabel(remember_row, text="Forgot Password?",
                     text_color=PRIMARY_BLUE, cursor="hand2").pack(side="right")

        ctk.CTkButton(
            card, text="Login", width=320, height=44,
            fg_color=PRIMARY_BLUE, font=("Segoe UI", 14, "bold"),
            command=self._validate_login
        ).pack(pady=(20, 0))

        ctk.CTkLabel(card,
                     text=f"Demo: {DEMO_USERNAME} / {DEMO_PASSWORD}",
                     font=("Segoe UI", 10), text_color=MUTED_TEXT).pack(pady=(16, 0))

    def _toggle_password(self):
        self._show_password = not self._show_password
        self.password_input.configure(show="" if self._show_password else "*")

    def _validate_login(self):
        """Check credentials; use constants, not hard-coded strings inside logic."""
        username = self.email_input.get().strip()
        password = self.password_input.get()
        if username == DEMO_USERNAME and password == DEMO_PASSWORD:
            self.on_login_success()
        else:
            CTkMessagebox(
                title="Login Failed",
                message="Invalid username or password.\nUse: admin / admin123",
                icon="cancel"
            )


# ============================================================
# SECTION 5 – DASHBOARD PAGE
# ============================================================

class DashboardPage(ctk.CTkFrame):
    """Overview screen with live statistics pulled from the database."""

    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=APP_BG)
        self.app = app_ref
        self._build_static_ui()

    def _build_static_ui(self):
        ctk.CTkLabel(self, text="Dashboard",
                     font=("Segoe UI", 28, "bold"), text_color=WHITE).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(self, text="Overview of student statistics — Limkokwing SL",
                     font=("Segoe UI", 13), text_color=MUTED_TEXT).pack(anchor="w", pady=(0, 25))

        # Stat cards row
        self.stats_row = ctk.CTkFrame(self, fg_color=APP_BG)
        self.stats_row.pack(fill="x", pady=(0, 25))
        self.stat_value_labels = []

        stat_cfg = [
            ("Total Students", "🧑‍🎓"),
            ("New Enrolments", "🆕"),
            ("Active Courses", "📚"),
            ("Average GPA", "📊"),
        ]
        for i, (title, icon) in enumerate(stat_cfg):
            card = ctk.CTkFrame(self.stats_row, width=250, height=140,
                                fg_color=CARD_BG, corner_radius=12)
            card.pack(side="left", padx=(0 if i == 0 else 15, 0),
                      fill="x", expand=True)
            ctk.CTkLabel(card, text=icon,
                         font=("Segoe UI", 22), text_color=PRIMARY_BLUE).pack(anchor="w", padx=20, pady=(18, 0))
            val = ctk.CTkLabel(card, text="—",
                               font=("Segoe UI", 28, "bold"), text_color=WHITE)
            val.pack(anchor="w", padx=20)
            ctk.CTkLabel(card, text=title,
                         font=("Segoe UI", 12), text_color=MUTED_TEXT).pack(anchor="w", padx=20, pady=(0, 18))
            self.stat_value_labels.append(val)

        # Content row
        content = ctk.CTkFrame(self, fg_color=APP_BG)
        content.pack(fill="both", expand=True)

        # Recent activities card
        recent = ctk.CTkFrame(content, fg_color=CARD_BG, corner_radius=12)
        recent.pack(side="left", fill="both", expand=True, padx=(0, 15))
        ctk.CTkLabel(recent, text="Recent Activities",
                     font=("Segoe UI", 16, "bold"), text_color=WHITE).pack(anchor="w", padx=25, pady=18)
        activities = [
            ("✅  New student registered via portal", "Just now"),
            ("📊  GPA recalculated after grade entry", "1 hour ago"),
            ("📚  Course catalog updated for Semester 2", "Today"),
            ("⚠️   At-risk student flagged for review", "Yesterday"),
            ("✅  CSV report exported by admin", "2 days ago"),
        ]
        for text, time in activities:
            row = ctk.CTkFrame(recent, fg_color="transparent")
            row.pack(fill="x", padx=25, pady=8)
            ctk.CTkLabel(row, text=text, font=("Segoe UI", 13),
                         text_color=WHITE).pack(anchor="w")
            ctk.CTkLabel(row, text=time, font=("Segoe UI", 11),
                         text_color=MUTED_TEXT).pack(anchor="w")

        # Welcome card
        welcome = ctk.CTkFrame(content, width=300, fg_color=CARD_BG, corner_radius=12)
        welcome.pack(side="right", fill="y")

        # Small logo on dashboard welcome card
        logo_img = load_logo_image((55, 55))
        if logo_img:
            ctk.CTkLabel(welcome, image=logo_img, text="").pack(pady=18)
        else:
            ctk.CTkLabel(welcome, text="🏛️", font=("Segoe UI", 50)).pack(pady=18)

        ctk.CTkLabel(welcome, text="Limkokwing University",
                     font=("Segoe UI", 15, "bold"), text_color=WHITE).pack(padx=20)
        ctk.CTkLabel(welcome,
                     text="Sierra Leone Campus\nStudent Management Portal\nSDG 4 — Quality Education",
                     wraplength=250, font=("Segoe UI", 12),
                     text_color=MUTED_TEXT, justify="center").pack(padx=20, pady=12)
        ctk.CTkButton(welcome, text="Campus Directory",
                      width=240, height=40, fg_color=PRIMARY_BLUE, corner_radius=8,
                      font=("Segoe UI", 13)).pack(pady=18)

    def refresh_stats(self):
        """Pull live stats from the database and update the card labels."""
        data = db_get_dashboard_stats()
        self.stat_value_labels[0].configure(text=str(data["total_students"]))
        self.stat_value_labels[1].configure(text=str(data["new_enrolments"]))
        self.stat_value_labels[2].configure(text=str(data["active_courses"]))
        self.stat_value_labels[3].configure(text=f"{data['avg_gpa']}  📈")


# ============================================================
# SECTION 6 – REGISTRATION PAGE (SPACIOUS, CENTERED, ALL VISIBLE)
# ============================================================

class RegistrationPage(ctk.CTkFrame):
    """Form to add or edit a student record with full input validation."""

    PROGRAMS = [
        "Software Engineering",
        "Multimedia Design",
        "Architecture",
        "Business Management",
        "Mass Communication",
    ]
    YEARS = ["1", "2", "3", "4"]

    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=APP_BG)
        self.app = app_ref
        self.editing_id = None
        self._build_ui()

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(header_frame, text="Student Registration",
                     font=("Segoe UI", 28, "bold"), text_color=WHITE).pack(anchor="center")
        ctk.CTkLabel(header_frame, text="Add or update student records — Limkokwing University SL",
                     font=("Segoe UI", 13), text_color=MUTED_TEXT).pack(anchor="center", pady=(2, 0))

        # ── Main scrollable container ───────────────────────────
        # Using scrollable frame so content is always accessible
        main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_scroll.pack(fill="both", expand=True)

        # ── Form Card ───────────────────────────────────────────
        form_card = ctk.CTkFrame(main_scroll,
                                 width=880,
                                 fg_color=CARD_BG,
                                 corner_radius=16)
        form_card.pack(pady=20, padx=40)

        # Form title with icon
        title_frame = ctk.CTkFrame(form_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=35, pady=(25, 15))

        ctk.CTkLabel(title_frame, text="📝  Student Information",
                     font=("Segoe UI", 18, "bold"), text_color=WHITE).pack(side="left")

        # Status indicator (shows when editing)
        self.status_indicator = ctk.CTkLabel(title_frame, text="",
                                             font=("Segoe UI", 12),
                                             text_color=WARNING_ORANGE)
        self.status_indicator.pack(side="right")

        # ── Form Grid (2 columns) ──────────────────────────────
        grid = ctk.CTkFrame(form_card, fg_color="transparent")
        grid.pack(fill="x", padx=35, pady=(5, 10))

        # Left column
        left_col = ctk.CTkFrame(grid, fg_color="transparent")
        left_col.pack(side="left", fill="x", expand=True, padx=(0, 15))

        # Right column
        right_col = ctk.CTkFrame(grid, fg_color="transparent")
        right_col.pack(side="left", fill="x", expand=True, padx=(15, 0))

        # ── Left Column Fields ──────────────────────────────────
        # Student ID
        self.inp_student_id = ctk.CTkEntry(left_col, height=44,
                                           placeholder_text="Student ID (e.g. SL1006)",
                                           corner_radius=8,
                                           font=("Segoe UI", 13))
        self.inp_student_id.pack(fill="x", pady=8)

        # Full Name
        self.inp_fullname = ctk.CTkEntry(left_col, height=44,
                                         placeholder_text="Full Name",
                                         corner_radius=8,
                                         font=("Segoe UI", 13))
        self.inp_fullname.pack(fill="x", pady=8)

        # Email
        self.inp_email = ctk.CTkEntry(left_col, height=44,
                                      placeholder_text="Email (e.g. name@limkokwing.edu.sl)",
                                      corner_radius=8,
                                      font=("Segoe UI", 13))
        self.inp_email.pack(fill="x", pady=8)

        # Phone
        self.inp_phone = ctk.CTkEntry(left_col, height=44,
                                      placeholder_text="Phone (e.g. +23276123456)",
                                      corner_radius=8,
                                      font=("Segoe UI", 13))
        self.inp_phone.pack(fill="x", pady=8)

        # ── Right Column Fields ─────────────────────────────────
        # Gender with radio buttons
        gender_frame = ctk.CTkFrame(right_col, fg_color=INPUT_BG, corner_radius=8)
        gender_frame.pack(fill="x", pady=8)

        ctk.CTkLabel(gender_frame, text="Gender:",
                     font=("Segoe UI", 12, "bold"), text_color=MUTED_TEXT).pack(anchor="w", padx=15, pady=(8, 4))

        gender_row = ctk.CTkFrame(gender_frame, fg_color="transparent")
        gender_row.pack(fill="x", padx=15, pady=(0, 8))

        self.gender_var = ctk.StringVar(value="Male")
        ctk.CTkRadioButton(gender_row, text="Male",
                           variable=self.gender_var, value="Male",
                           fg_color=PRIMARY_BLUE,
                           text_color=WHITE,
                           font=("Segoe UI", 12)).pack(side="left", padx=(0, 25))
        ctk.CTkRadioButton(gender_row, text="Female",
                           variable=self.gender_var, value="Female",
                           fg_color=PRIMARY_BLUE,
                           text_color=WHITE,
                           font=("Segoe UI", 12)).pack(side="left")

        # Program
        self.program_dd = ctk.CTkComboBox(right_col, height=44,
                                          values=self.PROGRAMS,
                                          corner_radius=8,
                                          font=("Segoe UI", 13),
                                          state="readonly")
        self.program_dd.pack(fill="x", pady=8)
        self.program_dd.set("Select Program")

        # Study Year
        self.year_dd = ctk.CTkComboBox(right_col, height=44,
                                       values=self.YEARS,
                                       corner_radius=8,
                                       font=("Segoe UI", 13),
                                       state="readonly")
        self.year_dd.pack(fill="x", pady=8)
        self.year_dd.set("Select Year")

        # Address
        self.inp_address = ctk.CTkEntry(right_col, height=44,
                                        placeholder_text="Home Address / District",
                                        corner_radius=8,
                                        font=("Segoe UI", 13))
        self.inp_address.pack(fill="x", pady=8)

        # ── Buttons ─────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(form_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=35, pady=(15, 20))

        ctk.CTkButton(btn_frame, text="💾  Save Student", height=46,
                      fg_color=PRIMARY_BLUE,
                      font=("Segoe UI", 14, "bold"),
                      corner_radius=8,
                      command=self._save_student).pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(btn_frame, text="🔄  Clear Form", height=46,
                      fg_color="#334155",
                      font=("Segoe UI", 14),
                      corner_radius=8,
                      command=self.clear_form).pack(side="left", fill="x", expand=True, padx=(10, 0))

        # ── Notes Section ───────────────────────────────────────
        notes_frame = ctk.CTkFrame(form_card, fg_color=INPUT_BG, corner_radius=8)
        notes_frame.pack(fill="x", padx=35, pady=(0, 25))

        ctk.CTkLabel(notes_frame, text="📋  Registration Guidelines",
                     font=("Segoe UI", 14, "bold"), text_color=WHITE).pack(anchor="w", padx=20, pady=(15, 8))

        notes_grid = ctk.CTkFrame(notes_frame, fg_color="transparent")
        notes_grid.pack(fill="x", padx=20, pady=(0, 15))

        notes_left = ctk.CTkFrame(notes_grid, fg_color="transparent")
        notes_left.pack(side="left", fill="x", expand=True)

        notes_right = ctk.CTkFrame(notes_grid, fg_color="transparent")
        notes_right.pack(side="left", fill="x", expand=True)

        notes = [
            ("✅", "Student ID must start with 'SL' + digits"),
            ("✅", "Email must be a valid address format"),
            ("✅", "Phone: include country code (+232...)"),
            ("✅", "All fields are compulsory"),
            ("✅", "GPA is auto-calculated from grades"),
            ("✅", "Status updates automatically on grade entry"),
        ]

        mid = len(notes) // 2
        for i, (icon, text) in enumerate(notes):
            container = notes_left if i < mid else notes_right
            ctk.CTkLabel(container, text=f"{icon}  {text}",
                         font=("Segoe UI", 11), text_color=MUTED_TEXT,
                         wraplength=350, justify="left").pack(anchor="w", pady=4)

    def clear_form(self):
        """Reset all form fields and editing state."""
        self.editing_id = None
        for inp in [self.inp_student_id, self.inp_fullname,
                    self.inp_email, self.inp_phone, self.inp_address]:
            inp.delete(0, ctk.END)
        self.gender_var.set("Male")
        self.program_dd.set("Select Program")
        self.year_dd.set("Select Year")
        self.inp_student_id.configure(state="normal")
        self.status_indicator.configure(text="")

    def load_for_edit(self, student_id: str):
        """Populate the form with an existing student's data for editing."""
        row = db_get_student_by_id(student_id)
        if not row:
            return
        self.clear_form()
        self.editing_id = student_id
        self.inp_student_id.insert(0, row[0])
        self.inp_student_id.configure(state="disabled")  # ID cannot be changed
        self.inp_fullname.insert(0, row[1])
        self.gender_var.set(row[2] or "Male")
        self.inp_email.insert(0, row[3] or "")
        self.inp_phone.insert(0, row[4] or "")
        self.program_dd.set(row[5] or self.PROGRAMS[0])
        self.year_dd.set(str(row[6]) if row[6] else "1")
        self.status_indicator.configure(text=f"✏️  Editing: {student_id}")
        self.app.navigate("Register")

    def _save_student(self):
        """Validate all inputs then call the database save function."""
        sid = self.inp_student_id.get().strip()
        name = self.inp_fullname.get().strip()
        email = self.inp_email.get().strip()
        phone = self.inp_phone.get().strip()
        year_raw = self.year_dd.get()
        year = int(year_raw) if year_raw.isdigit() else 1

        # ── Input validation (decision structures) ────────────
        if not self.editing_id and not validate_student_id(sid):
            CTkMessagebox(title="Validation Error",
                          message="Student ID must start with 'SL' followed by digits.\nExample: SL1006",
                          icon="cancel")
            return
        if not name:
            CTkMessagebox(title="Validation Error",
                          message="Full name is required.", icon="cancel")
            return
        if email and not validate_email(email):
            CTkMessagebox(title="Validation Error",
                          message="Please enter a valid email address.", icon="cancel")
            return
        if phone and not validate_phone(phone):
            CTkMessagebox(title="Validation Error",
                          message="Phone number appears invalid. Include country code.", icon="cancel")
            return

        today = datetime.now().strftime("%Y-%m-%d")

        if self.editing_id:
            data = (name, self.gender_var.get(), email, phone,
                    self.program_dd.get(), year, sid)
        else:
            data = (sid, name, self.gender_var.get(), email, phone,
                    self.program_dd.get(), year, 0.0, "Active", today)

        ok, msg = db_save_student(data, self.editing_id)
        if ok:
            CTkMessagebox(title="Success", message=msg, icon="check")
            self.clear_form()
            self.app.refresh_all_data()
            self.app.navigate("Records")
        else:
            CTkMessagebox(title="Error", message=msg, icon="cancel")


# ============================================================
# SECTION 7 – STUDENT RECORDS PAGE
# ============================================================

class StudentRecordsPage(ctk.CTkFrame):
    """Searchable table of all student records with edit / delete actions."""

    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=APP_BG)
        self.app = app_ref
        self._build_ui()

    def _build_ui(self):
        header_row = ctk.CTkFrame(self, fg_color=APP_BG)
        header_row.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(header_row, text="Student Records",
                     font=("Segoe UI", 28, "bold"), text_color=WHITE).pack(side="left", anchor="w")

        right = ctk.CTkFrame(header_row, fg_color=APP_BG)
        right.pack(side="right")
        self.search_input = ctk.CTkEntry(right, width=280, height=40,
                                         placeholder_text="Search by name or ID...",
                                         corner_radius=8,
                                         font=("Segoe UI", 13))
        self.search_input.pack(side="left", padx=8)
        self.search_input.bind("<KeyRelease>", lambda _: self.refresh_table())
        ctk.CTkButton(right, text="+ Register Student", height=40,
                      fg_color=PRIMARY_BLUE,
                      font=("Segoe UI", 13),
                      command=lambda: self.app.navigate("Register")).pack(side="left", padx=8)

        table_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        table_card.pack(fill="both", expand=True)

        # Table header
        header = ctk.CTkFrame(table_card, fg_color=PRIMARY_BLUE,
                              height=44, corner_radius=8)
        header.pack(fill="x", padx=15, pady=15)
        col_widths = [0.11, 0.22, 0.26, 0.1, 0.13, 0.09, 0.09]
        col_names = ["Student ID", "Full Name", "Program", "GPA", "Status", "Edit", "Delete"]
        for i, name in enumerate(col_names):
            ctk.CTkLabel(header, text=name, text_color=WHITE,
                         font=("Segoe UI", 13, "bold")).place(
                relx=sum(col_widths[:i]) + 0.01, rely=0.5, anchor="w")

        self.table_scroll = ctk.CTkScrollableFrame(table_card, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def refresh_table(self):
        """Clear and re-populate the table from the database."""
        for widget in self.table_scroll.winfo_children():
            widget.destroy()

        students = db_get_all_students(self.search_input.get().strip())
        col_widths = [0.11, 0.22, 0.26, 0.1, 0.13, 0.09, 0.09]

        for idx, (sid, name, program, gpa, status) in enumerate(students):
            row_bg = "#273449" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.table_scroll, fg_color=row_bg,
                               height=44, corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=sid, text_color=WHITE, font=("Segoe UI", 12)).place(relx=0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=name, text_color=WHITE, font=("Segoe UI", 12)).place(relx=col_widths[0] + 0.01,
                                                                                        rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=program, text_color=WHITE, font=("Segoe UI", 12)).place(
                relx=sum(col_widths[:2]) + 0.01, rely=0.5, anchor="w")

            gpa_colour = get_grade_colour(gpa)
            ctk.CTkLabel(row, text=f"{gpa:.2f}",
                         text_color=gpa_colour,
                         font=("Segoe UI", 12, "bold")).place(relx=sum(col_widths[:3]) + 0.01, rely=0.5, anchor="w")

            status_colour = (SUCCESS_GREEN if status == "Active"
                             else WARNING_ORANGE if status == "At Risk"
            else DANGER_RED)
            ctk.CTkLabel(row, text=status, fg_color=status_colour,
                         text_color=WHITE, corner_radius=6,
                         width=75, font=("Segoe UI", 11)).place(relx=sum(col_widths[:4]) + 0.01, rely=0.5, anchor="w")

            ctk.CTkButton(row, text="✏️", width=35, height=28, fg_color="transparent",
                          command=lambda s=sid: self.app.registration_page.load_for_edit(s)
                          ).place(relx=sum(col_widths[:5]) + 0.01, rely=0.5, anchor="w")
            ctk.CTkButton(row, text="🗑️", width=35, height=28, fg_color="transparent",
                          hover_color="#DC2626",
                          command=lambda s=sid: self._delete_student(s)
                          ).place(relx=sum(col_widths[:6]) + 0.01, rely=0.5, anchor="w")

    def _delete_student(self, student_id: str):
        confirm = CTkMessagebox(
            title="Confirm Delete",
            message=f"Permanently delete student {student_id} and all their results?",
            icon="warning"
        )
        if confirm.get() == "Delete":
            db_delete_student(student_id)
            self.app.refresh_all_data()
            CTkMessagebox(title="Deleted",
                          message="Student record removed.", icon="check")


# ============================================================
# SECTION 8 – COURSES PAGE
# ============================================================

class CoursesPage(ctk.CTkFrame):
    """View and manage the university course catalogue."""

    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=APP_BG)
        self.app = app_ref
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Course Management",
                     font=("Segoe UI", 28, "bold"), text_color=WHITE).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(self, text="Manage university courses — Limkokwing SL",
                     font=("Segoe UI", 13), text_color=MUTED_TEXT).pack(anchor="w", pady=(0, 20))

        # Stat cards
        self.stats_row = ctk.CTkFrame(self, fg_color=APP_BG)
        self.stats_row.pack(fill="x", pady=(0, 20))
        self.course_stat_labels = []
        stat_items = [("Total Courses", "📚"), ("Active Courses", "✅"), ("Total Students", "🧑‍🎓"),
                      ("Avg Class Size", "👥")]
        for i, (title, icon) in enumerate(stat_items):
            card = ctk.CTkFrame(self.stats_row, width=250, height=120,
                                fg_color=CARD_BG, corner_radius=12)
            card.pack(side="left", padx=(0 if i == 0 else 15, 0), fill="x", expand=True)
            ctk.CTkLabel(card, text=icon, font=("Segoe UI", 22),
                         text_color=PRIMARY_BLUE).pack(anchor="w", padx=20, pady=(15, 0))
            val = ctk.CTkLabel(card, text="0",
                               font=("Segoe UI", 26, "bold"), text_color=WHITE)
            val.pack(anchor="w", padx=20)
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 12),
                         text_color=MUTED_TEXT).pack(anchor="w", padx=20, pady=(0, 15))
            self.course_stat_labels.append(val)

        # Add course bar
        add_bar = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        add_bar.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(add_bar, text="Add New Course",
                     font=("Segoe UI", 15, "bold"), text_color=WHITE).pack(side="left", padx=25, pady=15)
        form = ctk.CTkFrame(add_bar, fg_color="transparent")
        form.pack(side="right", padx=25)
        self.inp_code = ctk.CTkEntry(form, width=120, height=40, placeholder_text="Code", font=("Segoe UI", 12),
                                     corner_radius=8)
        self.inp_name = ctk.CTkEntry(form, width=230, height=40, placeholder_text="Course Name", font=("Segoe UI", 12),
                                     corner_radius=8)
        self.inp_credits = ctk.CTkEntry(form, width=80, height=40, placeholder_text="Credits", font=("Segoe UI", 12),
                                        corner_radius=8)
        self.inp_lecturer = ctk.CTkEntry(form, width=190, height=40, placeholder_text="Lecturer", font=("Segoe UI", 12),
                                         corner_radius=8)
        for w in [self.inp_code, self.inp_name, self.inp_credits, self.inp_lecturer]:
            w.pack(side="left", padx=4)
        ctk.CTkButton(form, text="+ Add Course", height=40,
                      fg_color=PRIMARY_BLUE,
                      font=("Segoe UI", 13),
                      command=self._add_course).pack(side="left", padx=4)

        # Table
        table_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        table_card.pack(fill="both", expand=True)
        hdr = ctk.CTkFrame(table_card, fg_color=PRIMARY_BLUE, height=44, corner_radius=8)
        hdr.pack(fill="x", padx=15, pady=15)
        col_widths = [0.1, 0.3, 0.08, 0.22, 0.15, 0.08, 0.07]
        for i, h in enumerate(["Code", "Course Name", "Credits", "Lecturer", "Program", "Status", "Delete"]):
            ctk.CTkLabel(hdr, text=h, text_color=WHITE,
                         font=("Segoe UI", 13, "bold")).place(
                relx=sum(col_widths[:i]) + 0.01, rely=0.5, anchor="w")
        self.scroll = ctk.CTkScrollableFrame(table_card, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _add_course(self):
        code = self.inp_code.get().strip()
        name = self.inp_name.get().strip()
        credits = self.inp_credits.get().strip()
        lecturer = self.inp_lecturer.get().strip()
        if not code or not name:
            CTkMessagebox(title="Error", message="Course code and name are required.", icon="cancel")
            return
        conn = sqlite3.connect(DB_FILE)
        try:
            conn.execute("INSERT INTO courses VALUES (?,?,?,?,?,?)",
                         (code, name, int(credits) if credits.isdigit() else 3,
                          lecturer, "General", "Active"))
            conn.commit()
            for inp in [self.inp_code, self.inp_name, self.inp_credits, self.inp_lecturer]:
                inp.delete(0, ctk.END)
            CTkMessagebox(title="Success", message="Course added.", icon="check")
            self.app.refresh_all_data()
        except sqlite3.IntegrityError:
            CTkMessagebox(title="Error", message=f"Course code '{code}' already exists.", icon="cancel")
        finally:
            conn.close()

    def _delete_course(self, code: str):
        confirm = CTkMessagebox(title="Delete Course",
                                message=f"Delete course {code}?", icon="warning")
        if confirm.get() == "Delete":
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM courses WHERE course_code = ?", (code,))
            conn.commit()
            conn.close()
            self.app.refresh_all_data()

    def refresh_courses(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        conn = sqlite3.connect(DB_FILE)
        total_c = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        active_c = conn.execute("SELECT COUNT(*) FROM courses WHERE status='Active'").fetchone()[0]
        total_s = conn.execute("SELECT COUNT(*) FROM students WHERE status='Active'").fetchone()[0]
        avg_class = round(total_s / active_c) if active_c > 0 else 0
        courses = conn.execute("SELECT * FROM courses").fetchall()
        conn.close()

        self.course_stat_labels[0].configure(text=str(total_c))
        self.course_stat_labels[1].configure(text=str(active_c))
        self.course_stat_labels[2].configure(text=str(total_s))
        self.course_stat_labels[3].configure(text=str(avg_class))

        col_widths = [0.1, 0.3, 0.08, 0.22, 0.15, 0.08, 0.07]
        for idx, (code, name, credits, lecturer, program, status) in enumerate(courses):
            row_bg = "#273449" if idx % 2 == 0 else "#1E293B"
            row = ctk.CTkFrame(self.scroll, fg_color=row_bg, height=44, corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=code, text_color=WHITE, font=("Segoe UI", 12)).place(relx=0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=name, text_color=WHITE, font=("Segoe UI", 12)).place(relx=col_widths[0] + 0.01,
                                                                                        rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=str(credits), text_color=WHITE, font=("Segoe UI", 12)).place(
                relx=sum(col_widths[:2]) + 0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=lecturer, text_color=WHITE, font=("Segoe UI", 12)).place(
                relx=sum(col_widths[:3]) + 0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=program, text_color=WHITE, font=("Segoe UI", 12)).place(
                relx=sum(col_widths[:4]) + 0.01, rely=0.5, anchor="w")
            s_col = SUCCESS_GREEN if status == "Active" else WARNING_ORANGE
            ctk.CTkLabel(row, text=status, fg_color=s_col, text_color=WHITE,
                         corner_radius=6, width=75, font=("Segoe UI", 11)).place(relx=sum(col_widths[:5]) + 0.01,
                                                                                 rely=0.5, anchor="w")
            ctk.CTkButton(row, text="🗑️", width=35, height=28, fg_color="transparent",
                          hover_color="#DC2626",
                          command=lambda c=code: self._delete_course(c)
                          ).place(relx=sum(col_widths[:6]) + 0.01, rely=0.5, anchor="w")


# ============================================================
# SECTION 9 – RESULTS / GRADES PAGE
# ============================================================

class ResultsPage(ctk.CTkFrame):
    """Record grades for students. GPA is calculated automatically."""

    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=APP_BG)
        self.app = app_ref
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Student Results & Grades",
                     font=("Segoe UI", 28, "bold"), text_color=WHITE).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(self,
                     text="Record grades — cumulative GPA is calculated automatically",
                     font=("Segoe UI", 13), text_color=MUTED_TEXT).pack(anchor="w", pady=(0, 20))

        # Stat cards
        self.stats_row = ctk.CTkFrame(self, fg_color=APP_BG)
        self.stats_row.pack(fill="x", pady=(0, 20))
        self.result_stat_labels = []
        stat_items = [("Class Avg GPA", "📊"), ("Pass Rate", "✅"), ("Top Performer", "🏆"), ("At-Risk Students", "⚠️")]
        for i, (title, icon) in enumerate(stat_items):
            card = ctk.CTkFrame(self.stats_row, width=250, height=120,
                                fg_color=CARD_BG, corner_radius=12)
            card.pack(side="left", padx=(0 if i == 0 else 15, 0), fill="x", expand=True)
            ctk.CTkLabel(card, text=icon, font=("Segoe UI", 22),
                         text_color=PRIMARY_BLUE).pack(anchor="w", padx=20, pady=(15, 0))
            val = ctk.CTkLabel(card, text="—",
                               font=("Segoe UI", 26, "bold"), text_color=WHITE)
            val.pack(anchor="w", padx=20)
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 12),
                         text_color=MUTED_TEXT).pack(anchor="w", padx=20, pady=(0, 15))
            self.result_stat_labels.append(val)

        # GPA reference card
        ref_bar = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        ref_bar.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(ref_bar, text="📋  GPA Reference Scale",
                     font=("Segoe UI", 14, "bold"), text_color=WHITE).pack(side="left", padx=25, pady=12)
        ref_frame = ctk.CTkFrame(ref_bar, fg_color="transparent")
        ref_frame.pack(side="right", padx=25)
        for grade, pts in GRADE_GPA_MAP.items():
            col = get_grade_colour(pts)
            ctk.CTkLabel(ref_frame,
                         text=f"{grade}={pts:.1f}",
                         font=("Segoe UI", 10, "bold"),
                         text_color=col).pack(side="left", padx=6)

        # Grade entry bar
        add_bar = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        add_bar.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(add_bar, text="Add New Grade",
                     font=("Segoe UI", 15, "bold"), text_color=WHITE).pack(side="left", padx=25, pady=15)
        form = ctk.CTkFrame(add_bar, fg_color="transparent")
        form.pack(side="right", padx=25)

        self.student_dd = ctk.CTkComboBox(form, width=210, height=40, values=[], state="readonly",
                                          font=("Segoe UI", 12), corner_radius=8)
        self.semester_dd = ctk.CTkComboBox(form, width=130, height=40,
                                           values=["Semester 1", "Semester 2", "Semester 3", "Semester 4"],
                                           state="readonly", font=("Segoe UI", 12), corner_radius=8)
        self.course_dd = ctk.CTkComboBox(form, width=160, height=40, values=[], state="readonly", font=("Segoe UI", 12),
                                         corner_radius=8)
        self.grade_dd = ctk.CTkComboBox(form, width=100, height=40,
                                        values=list(GRADE_GPA_MAP.keys()), state="readonly", font=("Segoe UI", 12),
                                        corner_radius=8)
        for w in [self.student_dd, self.semester_dd, self.course_dd, self.grade_dd]:
            w.pack(side="left", padx=4)
        ctk.CTkButton(form, text="Save Grade", height=40,
                      fg_color=SUCCESS_GREEN, hover_color="#059669",
                      font=("Segoe UI", 13, "bold"),
                      command=self._save_grade).pack(side="left", padx=4)

        # Results table
        table_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        table_card.pack(fill="both", expand=True)
        hdr = ctk.CTkFrame(table_card, fg_color=PRIMARY_BLUE, height=44, corner_radius=8)
        hdr.pack(fill="x", padx=15, pady=15)
        col_widths = [0.12, 0.22, 0.15, 0.15, 0.1, 0.12, 0.14]
        for i, h in enumerate(["Student ID", "Student Name", "Semester", "Course", "Grade", "GPA Pts", "Status"]):
            ctk.CTkLabel(hdr, text=h, text_color=WHITE,
                         font=("Segoe UI", 13, "bold")).place(
                relx=sum(col_widths[:i]) + 0.01, rely=0.5, anchor="w")
        self.results_scroll = ctk.CTkScrollableFrame(table_card, fg_color="transparent")
        self.results_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _save_grade(self):
        ok, msg = db_save_grade(
            self.student_dd.get(),
            self.semester_dd.get(),
            self.course_dd.get(),
            self.grade_dd.get()
        )
        if ok:
            CTkMessagebox(title="Grade Saved", message=msg, icon="check")
            self.app.refresh_all_data()
        else:
            CTkMessagebox(title="Error", message=msg, icon="cancel")

    def refresh_results(self):
        """Reload dropdowns and result rows from the database."""
        data = db_get_results_stats()

        self.student_dd.configure(values=data["students"])
        self.course_dd.configure(values=data["courses"])

        self.result_stat_labels[0].configure(text=str(data["avg_gpa"]))
        self.result_stat_labels[1].configure(text=data["pass_rate"])
        self.result_stat_labels[2].configure(text=data["top_student"])
        self.result_stat_labels[3].configure(text=str(data["at_risk"]))

        for w in self.results_scroll.winfo_children():
            w.destroy()

        col_widths = [0.12, 0.22, 0.15, 0.15, 0.1, 0.12, 0.14]
        for idx, (sid, name, sem, course, grade, gpa_pts) in enumerate(data["results"]):
            row_bg = "#273449" if idx % 2 == 0 else "#1E293B"
            is_pass = gpa_pts >= GPA_PASS_THRESHOLD
            status_txt = "Pass" if is_pass else "Fail"
            s_col = SUCCESS_GREEN if is_pass else DANGER_RED

            row = ctk.CTkFrame(self.results_scroll, fg_color=row_bg, height=44, corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=sid, text_color=WHITE, font=("Segoe UI", 12)).place(relx=0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=name, text_color=WHITE, font=("Segoe UI", 12)).place(relx=col_widths[0] + 0.01,
                                                                                        rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=sem, text_color=WHITE, font=("Segoe UI", 12)).place(relx=sum(col_widths[:2]) + 0.01,
                                                                                       rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=course, text_color=WHITE, font=("Segoe UI", 12)).place(
                relx=sum(col_widths[:3]) + 0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=grade, text_color=WHITE, font=("Segoe UI", 12)).place(
                relx=sum(col_widths[:4]) + 0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=f"{gpa_pts:.1f}",
                         text_color=get_grade_colour(gpa_pts),
                         font=("Segoe UI", 12, "bold")).place(relx=sum(col_widths[:5]) + 0.01, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=status_txt, fg_color=s_col,
                         text_color=WHITE, corner_radius=6,
                         width=70, font=("Segoe UI", 11)).place(relx=sum(col_widths[:6]) + 0.01, rely=0.5, anchor="w")


# ============================================================
# SECTION 10 – REPORTS & ANALYTICS PAGE
# ============================================================

class ReportsPage(ctk.CTkFrame):
    """Analytics page with program breakdown, honour roll, at-risk list, and CSV export."""

    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=APP_BG)
        self.app = app_ref
        self._build_static_ui()

    def _build_static_ui(self):
        ctk.CTkLabel(self, text="Reports & Analytics",
                     font=("Segoe UI", 28, "bold"), text_color=WHITE).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(self, text="University performance breakdown and data export",
                     font=("Segoe UI", 13), text_color=MUTED_TEXT).pack(anchor="w", pady=(0, 20))

        top_bar = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        top_bar.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(top_bar, text="Academic report — current semester | SDG 4 Quality Education",
                     font=("Segoe UI", 14), text_color=WHITE).pack(side="left", padx=25, pady=15)
        ctk.CTkButton(top_bar, text="📥  Export to CSV", height=42,
                      fg_color=SUCCESS_GREEN, hover_color="#059669",
                      font=("Segoe UI", 13, "bold"),
                      command=self._export_csv).pack(side="right", padx=25, pady=10)

        content = ctk.CTkFrame(self, fg_color=APP_BG)
        content.pack(fill="both", expand=True)

        # Left: enrollment by program
        left_card = ctk.CTkFrame(content, fg_color=CARD_BG, corner_radius=12)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 15))
        ctk.CTkLabel(left_card, text="Enrolment by Program",
                     font=("Segoe UI", 16, "bold"), text_color=WHITE).pack(anchor="w", padx=25, pady=20)
        self.program_container = ctk.CTkFrame(left_card, fg_color="transparent")
        self.program_container.pack(fill="x", padx=25, pady=(0, 20))

        # Right column
        right_col = ctk.CTkFrame(content, fg_color=APP_BG, width=400)
        right_col.pack(side="right", fill="y")

        honour_card = ctk.CTkFrame(right_col, fg_color=CARD_BG, corner_radius=12)
        honour_card.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(honour_card, text="🏆  Honour Roll  (GPA ≥ 3.5)",
                     font=("Segoe UI", 15, "bold"), text_color=WHITE).pack(anchor="w", padx=25, pady=15)
        self.honour_container = ctk.CTkFrame(honour_card, fg_color="transparent")
        self.honour_container.pack(fill="x", padx=25, pady=(0, 15))

        risk_card = ctk.CTkFrame(right_col, fg_color=CARD_BG, corner_radius=12)
        risk_card.pack(fill="x")
        ctk.CTkLabel(risk_card, text=f"⚠️  At-Risk  (GPA < {AT_RISK_THRESHOLD:.1f})",
                     font=("Segoe UI", 15, "bold"), text_color=WHITE).pack(anchor="w", padx=25, pady=15)
        self.risk_container = ctk.CTkFrame(risk_card, fg_color="transparent")
        self.risk_container.pack(fill="x", padx=25, pady=(0, 15))

    def _export_csv(self):
        data = db_get_report_data()
        outfile = "limkokwing_sl_student_report.csv"
        with open(outfile, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Student ID", "Full Name", "Gender", "Email", "Phone",
                "Program", "Study Year", "Cumulative GPA", "Status", "Enrolled Date"
            ])
            writer.writerows(data["all_students"])
        CTkMessagebox(
            title="Export Complete",
            message=f"Report exported as:\n{outfile}",
            icon="check"
        )

    def load_report_data(self):
        """Clear dynamic widgets and reload from database."""
        for container in [self.program_container,
                          self.honour_container, self.risk_container]:
            for w in container.winfo_children():
                w.destroy()

        data = db_get_report_data()
        total = data["total"]

        # Program breakdown with progress bars
        for program, count in data["by_program"]:
            pct = int((count / total) * 100) if total > 0 else 0
            prow = ctk.CTkFrame(self.program_container, fg_color="transparent")
            prow.pack(fill="x", pady=8)
            ctk.CTkLabel(prow, text=program, text_color=WHITE,
                         font=("Segoe UI", 13)).pack(anchor="w")
            bar_row = ctk.CTkFrame(prow, fg_color="transparent")
            bar_row.pack(fill="x", pady=3)
            prog = ctk.CTkProgressBar(bar_row, width=300, progress_color=PRIMARY_BLUE)
            prog.pack(side="left")
            prog.set(pct / 100)
            ctk.CTkLabel(bar_row,
                         text=f"{count} student(s)  ({pct}%)",
                         text_color=MUTED_TEXT, font=("Segoe UI", 12)).pack(side="right", padx=10)

        # Honour roll
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, gpa) in enumerate(data["top_students"]):
            hrow = ctk.CTkFrame(self.honour_container, fg_color="transparent")
            hrow.pack(fill="x", pady=5)
            ctk.CTkLabel(hrow, text=f"{medals[i]}  {name}",
                         text_color=WHITE, font=("Segoe UI", 13)).pack(side="left")
            ctk.CTkLabel(hrow, text=f"GPA: {gpa:.2f}",
                         text_color=SUCCESS_GREEN,
                         font=("Segoe UI", 13, "bold")).pack(side="right")

        # At-risk students
        if not data["at_risk"]:
            ctk.CTkLabel(self.risk_container,
                         text="✅  No at-risk students currently",
                         text_color=SUCCESS_GREEN,
                         font=("Segoe UI", 13)).pack(anchor="w", pady=5)
        else:
            for name, gpa in data["at_risk"]:
                rrow = ctk.CTkFrame(self.risk_container, fg_color="transparent")
                rrow.pack(fill="x", pady=5)
                ctk.CTkLabel(rrow, text=f"⚠️  {name}",
                             text_color=WHITE, font=("Segoe UI", 13)).pack(side="left")
                ctk.CTkLabel(rrow, text=f"GPA: {gpa:.2f}",
                             text_color=DANGER_RED,
                             font=("Segoe UI", 13, "bold")).pack(side="right")


# ============================================================
# SECTION 11 – MAIN APPLICATION CONTROLLER
# ============================================================

class StudentManagementApp(ctk.CTk):
    """
    Root application window.
    Manages the login screen and main navigation between pages.
    """

    def __init__(self):
        super().__init__()
        self.title("Limkokwing Student Management System — Sierra Leone")
        self.geometry("1280x720")
        self.minsize(1100, 650)
        self.configure(fg_color=APP_BG)

        # Initialise database on startup
        init_database()

        # Show login first
        self.login_frame = LoginPage(self, self._show_main_app)
        self.login_frame.pack(fill="both", expand=True)

    def _show_main_app(self):
        """Destroy login and build the main interface."""
        self.login_frame.destroy()

        self.main_container = ctk.CTkFrame(self, fg_color=APP_BG)
        self.main_container.pack(fill="both", expand=True)

        self._build_sidebar()

        self.page_container = ctk.CTkFrame(self.main_container, fg_color=APP_BG)
        self.page_container.pack(side="right", fill="both", expand=True, padx=15, pady=15)

        # Instantiate all pages
        self.dashboard_page = DashboardPage(self.page_container, self)
        self.registration_page = RegistrationPage(self.page_container, self)
        self.records_page = StudentRecordsPage(self.page_container, self)
        self.courses_page = CoursesPage(self.page_container, self)
        self.results_page = ResultsPage(self.page_container, self)
        self.reports_page = ReportsPage(self.page_container, self)

        self.navigate("Dashboard")

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self.main_container, width=240,
                               fg_color=CARD_BG, corner_radius=0)
        sidebar.pack(side="left", fill="y")

        # ── Sidebar with Logo ──────────────────────────────────
        header_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        header_frame.pack(pady=(18, 15), padx=15, fill="x")

        # Logo on sidebar
        logo_img = load_logo_image((45, 45))
        if logo_img:
            logo_label = ctk.CTkLabel(header_frame, image=logo_img, text="")
            logo_label.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(header_frame, text="Limkokwing\nSierra Leone",
                     font=("Segoe UI", 16, "bold"), text_color=WHITE).pack(side="left", anchor="w")

        # Separator
        ctk.CTkFrame(sidebar, height=1, fg_color=BORDER_COLOR).pack(fill="x", padx=15, pady=5)

        nav_items = [
            ("Dashboard", "📊"),
            ("Students", "🧑‍🎓"),
            ("Courses", "📚"),
            ("Results", "📝"),
            ("Reports", "📈"),
        ]
        self.nav_buttons: dict[str, ctk.CTkButton] = {}

        for label, icon in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=f"  {icon}  {label}", anchor="w",
                fg_color="transparent", hover_color="#334155",
                text_color=WHITE, font=("Segoe UI", 14),
                command=lambda l=label: self.navigate(l),
                height=44
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[label] = btn

        ctk.CTkFrame(sidebar, height=1, fg_color=BORDER_COLOR).pack(fill="x", padx=15, pady=5)

        ctk.CTkButton(
            sidebar, text="  ✅  New Registration", anchor="w",
            fg_color=SUCCESS_GREEN, hover_color="#059669",
            text_color=WHITE, font=("Segoe UI", 13, "bold"),
            command=lambda: self.navigate("Register"),
            height=44
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 15))

        for label, icon in [("Help", "❓"), ("Logout", "🚪")]:
            btn = ctk.CTkButton(
                sidebar, text=f"  {icon}  {label}", anchor="w",
                fg_color="transparent", hover_color="#334155",
                text_color=MUTED_TEXT, font=("Segoe UI", 13),
                command=lambda l=label: self._sidebar_action(l),
                height=40
            )
            btn.pack(side="bottom", fill="x", padx=10, pady=3)
            self.nav_buttons[label] = btn

    def navigate(self, page_name: str):
        """Show the requested page and highlight its nav button."""
        # Reset all nav buttons
        for label, btn in self.nav_buttons.items():
            btn.configure(fg_color=PRIMARY_BLUE if label == page_name else "transparent")

        # Hide all pages
        for page in [self.dashboard_page, self.registration_page,
                     self.records_page, self.courses_page,
                     self.results_page, self.reports_page]:
            page.pack_forget()

        # Show and refresh the selected page
        if page_name == "Dashboard":
            self.dashboard_page.refresh_stats()
            self.dashboard_page.pack(fill="both", expand=True)
        elif page_name in ("Register", "Students"):
            self.registration_page.clear_form()
            self.registration_page.pack(fill="both", expand=True)
        elif page_name == "Records":
            self.records_page.refresh_table()
            self.records_page.pack(fill="both", expand=True)
        elif page_name == "Courses":
            self.courses_page.refresh_courses()
            self.courses_page.pack(fill="both", expand=True)
        elif page_name == "Results":
            self.results_page.refresh_results()
            self.results_page.pack(fill="both", expand=True)
        elif page_name == "Reports":
            self.reports_page.load_report_data()
            self.reports_page.pack(fill="both", expand=True)

    def refresh_all_data(self):
        """Refresh every page's data — called after any create / update / delete."""
        self.dashboard_page.refresh_stats()
        self.records_page.refresh_table()
        self.courses_page.refresh_courses()
        self.results_page.refresh_results()
        self.reports_page.load_report_data()

    def _sidebar_action(self, action: str):
        if action == "Logout":
            confirm = CTkMessagebox(title="Logout",
                                    message="Are you sure you want to logout?",
                                    icon="question")
            if confirm.get() == "Delete":  # CTkMessagebox maps "Yes" → "Delete"
                self.destroy()
                StudentManagementApp().mainloop()
        elif action == "Help":
            CTkMessagebox(title="Help",
                          message="For support contact:\nsupport@limkokwing.edu.sl\n\nPROG103 Final Project\nSDG 4 — Quality Education",
                          icon="info")


# ============================================================
# SECTION 12 – ENTRY POINT
# ============================================================

if __name__ == "__main__":
    app = StudentManagementApp()
    app.mainloop()