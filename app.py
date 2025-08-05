from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
from werkzeug.utils import secure_filename
import base64
from datetime import datetime
import sqlite3
from flask import send_from_directory
import json
import pdfkit
from flask import make_response, render_template_string
import uuid;


#ollama
import requests
import re

app = Flask(__name__)
app.secret_key = 'a3f4c6e8b1d2e9f7c4b3d2a1e6f8c7d9'

#for converting html content into pdf (this is used in certificate download feature)
path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)


# Create upload folders if they don't exist
ID_CARD_FOLDER = 'uploads/id_cards'
LIVE_PHOTO_FOLDER = 'uploads/live_photos'
os.makedirs(ID_CARD_FOLDER, exist_ok=True)
os.makedirs(LIVE_PHOTO_FOLDER, exist_ok=True)

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = 'uploads/notes'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

DATABASE = 'grademate_ollama.db' #Database name

#Database Initialization
def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    #teacher table creation
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers (
        employee_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        password TEXT NOT NULL,
        college_name TEXT NOT NULL,
        department TEXT NOT NULL,
        id_card_path TEXT,
        live_photo_path TEXT,
        status TEXT DEFAULT 'pending'
    )
    ''')
    
    #student table creation
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            username TEXT NOT NULL,
            usn TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            section TEXT NOT NULL,
            semester TEXT NOT NULL
        )
    ''')
    
    #tests table creation
    cursor.execute('''   
        CREATE TABLE IF NOT EXISTS tests (
        test_id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT NOT NULL,
        subject TEXT NOT NULL,
        section TEXT NOT NULL,  
        semester TEXT NOT NULL,  
        total_time INTEGER NOT NULL,
        total_questions INTEGER NOT NULL,
        status TEXT DEFAULT 'draft',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES teachers(employee_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
    )
    ''')
     
    #test_questions table creation
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS test_questions (
        question_id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_id INTEGER NOT NULL,
        question_no INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        rubric TEXT NOT NULL,
        max_marks INTEGER NOT NULL,
        FOREIGN KEY (test_id) REFERENCES tests(test_id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    )
''')
    
    #student_responses table creation
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS student_responses (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    usn TEXT NOT NULL,
    test_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    score INTEGER,
    feedback TEXT,
    FOREIGN KEY (test_id) REFERENCES tests(test_id),
    FOREIGN KEY (question_id) REFERENCES test_questions(question_id),
    FOREIGN KEY (usn) REFERENCES students(usn)
);
        
    ''')
    
    #notes table creation
    cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL,
    section TEXT NOT NULL,
    semester TEXT NOT NULL,
    faculty_name TEXT NOT NULL,
    file_path TEXT NOT NULL
);
               ''')


    conn.commit()
    conn.close()

init_db()  # Initialize DB on startup


#routing - home - working fine
@app.route('/')
def home():
    return render_template('index.html')


#routing how it works
@app.route('/how_it_works')
def how_it_works():
    return render_template('how_it_works.html')

#routing upload notes
@app.route('/upload_notes', methods=['GET', 'POST'])
def upload_notes():
    # Only allow logged-in teachers to upload notes
    if 'employee_id' not in session:
        flash("Please log in as a teacher to upload notes.", "error")
        return redirect(url_for('teacher_signin'))

    employee_id = session['employee_id']

    # Handle note upload
    if request.method == 'POST':
        subject_name = request.form.get('subject_name')
        section = request.form.get('section')
        semester = request.form.get('semester')
        note_file = request.files.get('note_file')

        if not subject_name or not section or not semester or not note_file:
            flash("All fields are required.", "error")
            return redirect(request.url)

        if note_file.filename == '':
            flash("No file selected.", "error")
            return redirect(request.url)

        if note_file and allowed_file(note_file.filename):
            filename = secure_filename(note_file.filename)
            unique_filename = str(uuid.uuid4()) + '_' + filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            note_file.save(file_path)

            # Get teacher's name for faculty_name
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM teachers WHERE employee_id = ?', (employee_id,))
            teacher = cursor.fetchone()
            faculty_name = teacher[0] if teacher else employee_id

            cursor.execute('''
                INSERT INTO notes (subject_name, section, semester, faculty_name, file_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (subject_name, section, semester, faculty_name, file_path))
            conn.commit()
            conn.close()

            flash("Note uploaded successfully!", "success")
            return redirect(url_for('upload_notes'))
        else:
            flash("Invalid file type. Allowed: PDF, DOC, DOCX", "error")
            return redirect(request.url)

    # GET request: Show notes uploaded by this teacher
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT note_id, subject_name, section, semester, file_path FROM notes WHERE faculty_name = (SELECT name FROM teachers WHERE employee_id = ?)', (employee_id,))
    notes = cursor.fetchall()
    conn.close()

    # Get teacher's name for display
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM teachers WHERE employee_id = ?', (employee_id,))
    teacher = cursor.fetchone()
    faculty_name = teacher[0] if teacher else employee_id
    conn.close()

    return render_template('upload_notes.html', notes=notes, faculty_name=faculty_name)


#delete notes
@app.route('/delete_note/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    if 'employee_id' not in session:
        flash("Please log in to delete notes.", "error")
        return redirect(url_for('teacher_signin'))

    employee_id = session['employee_id']

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    # Get the note and check ownership
    cursor.execute('SELECT faculty_name, file_path FROM notes WHERE note_id = ?', (note_id,))
    note = cursor.fetchone()
    if not note:
        flash("Note not found.", "error")
        conn.close()
        return redirect(url_for('upload_notes'))

    faculty_name, file_path = note
    cursor.execute('SELECT name FROM teachers WHERE employee_id = ?', (employee_id,))
    teacher = cursor.fetchone()
    current_teacher_name = teacher[0] if teacher else employee_id

    if faculty_name != current_teacher_name:
        flash("You can only delete your own notes.", "error")
        conn.close()
        return redirect(url_for('upload_notes'))

    # Delete file from filesystem
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            flash(f"Error deleting file: {e}", "error")

    # Delete from database
    cursor.execute('DELETE FROM notes WHERE note_id = ?', (note_id,))
    conn.commit()
    conn.close()

    flash("Note deleted successfully.", "success")
    return redirect(url_for('upload_notes'))


# Resources route
@app.route('/resources')
def resources():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes')
    notes = cursor.fetchall()
    conn.close()
    # Use employee_id for ownership check in template
    current_faculty = session.get('employee_id', None)
    return render_template('resources.html', notes=notes, current_faculty=current_faculty)


#routing - admin_signin - working fine 
@app.route('/admin_signin', methods=['GET', 'POST'])
def admin_signin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == 'admin' and password == 'admin123':  # hardcoded
            session['admin_logged_in'] = True  # <-- This line is needed!
            flash('Login successful!')
            return redirect(url_for('admin_dashboard')) 
        else:
            flash('Invalid credentials!')
            return redirect(url_for('admin_signin'))  # return to login

    # If GET request, just render the form
    return render_template('admin_signin.html')


#routing - admin_dashboard - working fine 
@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Please login as admin first.', 'error')
        return redirect(url_for('admin_signin'))

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT employee_id, name, id_card_path, live_photo_path, status FROM teachers')
            teachers = cursor.fetchall()
        return render_template('admin_dashboard.html', teachers=teachers)
    except Exception as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for('admin_signin'))

#routing - admin-actions-approve - working fine 
@app.route('/approve/<emp_id>', methods=['POST'])
def approve_teacher(emp_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE teachers SET status = "approved" WHERE employee_id = ?', (emp_id,))
    conn.commit()
    conn.close()
    flash("Teacher approved!", "success")
    return redirect(url_for('admin_dashboard'))


#routing - admin-actions-decline - working fine 
@app.route('/decline/<emp_id>', methods=['POST'])
def decline_teacher(emp_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE teachers SET status = "declined" WHERE employee_id = ?', (emp_id,))
    conn.commit()
    conn.close()
    flash("Teacher declined!", "info")
    return redirect(url_for('admin_dashboard'))


#routing - admin-actions-remove - working fine 
@app.route('/remove/<emp_id>', methods=['POST'])
def remove_teacher(emp_id):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM teachers WHERE employee_id = ?", (emp_id,))
            conn.commit()
        flash(f"Removed teacher: {emp_id}", "success")
    except Exception as e:
        flash(f"Error removing teacher: {e}", "error")
    return redirect(url_for('admin_dashboard'))


#routing - teacher_signup (GET + POST) - working fine but sometimes previous flash messages will get displayed 
@app.route('/teacher_signup', methods=['GET', 'POST'])
def teacher_signup():
    
    session.pop('_flashes', None)  # Clear any lingering flash messages (modified-added)
    if request.method == 'POST':
        # Get form fields
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        employee_id = request.form['employee_id']
        college_name = request.form['college_name']
        department = request.form['department']
        live_photo_data = request.form['live_photo_data']

        if password != confirm_password:
            flash("Passwords do not match.", "teacher_error")
            return redirect(url_for('teacher_signup'))

        # Save ID card
        id_card_path = ""
        id_card_file = request.files['id_card']
        if id_card_file:
            id_card_filename = secure_filename(id_card_file.filename)
            id_card_path = os.path.join(ID_CARD_FOLDER, id_card_filename)
            id_card_file.save(id_card_path)

        # Save live photo
        live_photo_path = ""
        if live_photo_data:
            try:
                header, encoded = live_photo_data.split(",", 1)
                live_photo_bytes = base64.b64decode(encoded)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                live_photo_filename = f"{employee_id}_{timestamp}.png"
                live_photo_path = os.path.join(LIVE_PHOTO_FOLDER, live_photo_filename)
                with open(live_photo_path, "wb") as f:
                    f.write(live_photo_bytes)
            except Exception as e:
                flash(f"Error saving live photo: {e}", "teacher_error")
                return redirect(url_for('teacher_signup'))

        try:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO teachers (
                    employee_id, name, email, password, college_name,
                    department, id_card_path, live_photo_path,status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,?)
            ''', (
                employee_id, name, email, password, college_name,
                department, id_card_path, live_photo_path,'pending'
            ))
            conn.commit()
            conn.close()
            flash("Signup successful! Please login.", "success")
            return redirect(url_for('teacher_signin'))
        except sqlite3.IntegrityError as e:
            flash(f"Error: {e}. Possibly duplicate employee ID or email.", "teacher_error")
            return redirect(url_for('teacher_signup'))
        except Exception as e:
            flash(f"Database error: {e}", "teacher_error")
            return redirect(url_for('teacher_signup'))

    return render_template('teacher_signup.html')


@app.route('/teacher_signin', methods=['GET', 'POST'])
def teacher_signin():
    if request.method == 'GET':
        return render_template('teacher_signin.html')

    # POST method handling
    employee_id = request.form['employee_id']
    password = request.form['password']

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM teachers WHERE employee_id = ? AND password = ?', (employee_id, password))
        teacher = cursor.fetchone()
        conn.close()

        if teacher:
            status = teacher[8]  # Assuming status is the 9th column (index 8)
            if status != 'approved':
                flash("Your account is not approved yet.", "teacher_error")
                return redirect(url_for('teacher_signin'))

            session['employee_id'] = employee_id
            flash("Login successful!", "success")
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('teacher_dashboard', employee_id=employee_id))
        else:
            flash("Invalid employee ID or password", "teacher_error")
            return redirect(url_for('teacher_signin'))

    except Exception as e:
        flash(f"Database error: {e}", "teacher_error")
        return redirect(url_for('teacher_signin'))


#routing teacher_dashboard -working fine
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if not session.get('employee_id'):
        flash("Please login first.", "teacher_error")
        return redirect(url_for('teacher_signin'))

    employee_id = session.get('employee_id')

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT name, email, college_name, department FROM teachers WHERE employee_id = ?', (employee_id,))
        teacher = cursor.fetchone()
        conn.close()

        if teacher:
            name, email, college_name, department = teacher
            return render_template('teacher_dashboard.html', name=name, email=email, college_name=college_name, department=department)

        else:
            flash("Teacher record not found.", "teacher_error")
            return redirect(url_for('teacher_signin'))

    except Exception as e:
        flash(f"Database error: {e}", "teacher_error")
        return redirect(url_for('teacher_signin'))


#routing create_test- working fine
@app.route('/create_test', methods=['GET', 'POST'])
def create_test():
    if 'employee_id' not in session:
        return redirect('/teacher_signin')  # Ensure only logged-in teachers access

    if request.method == 'POST':
        subject = request.form['subject']
        section = request.form['section']
        semester = request.form['semester']
        total_time = int(request.form['total_time'])
        total_questions = int(request.form['total_questions'])
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        employee_id = session['employee_id']  # from login session

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO tests (employee_id,  subject, section,semester,
                               total_time, total_questions, created_at)
            VALUES (?, ?, ?, ?, ?, ?,?)
        ''', (employee_id, subject, section,semester, total_time,
              total_questions, created_at))

        test_id = cursor.lastrowid  # needed for inserting questions next
        conn.commit()
        conn.close()

        return redirect(f'/add_questions/{test_id}') #(modified- removed no_questions)

    return render_template('create_test.html')

#routing add_questions - working fine 
@app.route('/add_questions/<int:test_id>', methods=['GET', 'POST'])
def add_questions(test_id):
    if 'employee_id' not in session:
        return redirect('/teacher_signin')  # use a full route string

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get total_questions from DB
    cursor.execute('SELECT total_questions FROM tests WHERE test_id = ?', (test_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return "Invalid test ID", 404

    total_questions = row['total_questions']

    if request.method == 'POST':
        for q_no in range(1, total_questions + 1):
            question_text = request.form.get(f'question_text_{q_no}')
            rubric = request.form.get(f'rubric_{q_no}')
            max_marks = request.form.get(f'max_marks_{q_no}')

            # Optional: validate here

            cursor.execute('''
                INSERT INTO test_questions (test_id, question_no, question_text, rubric, max_marks)
                VALUES (?, ?, ?, ?, ?)
            ''', (test_id, q_no, question_text, rubric, int(max_marks)))

        conn.commit()
        conn.close()

        return redirect('/teacher_dashboard')

    conn.close()
    return render_template('add_questions.html', test_id=test_id,total_questions=total_questions) # (modified - removed total_questions)


#routing my_tests (view test) - working fine
@app.route('/my_tests')
def my_tests():
    employee_id = session.get('employee_id')
    if not employee_id:
        flash("Please log in first.")
        return redirect(url_for('teacher_signin'))  # or your login route

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT test_id, subject, status, created_at
        FROM tests
        WHERE employee_id = ?
        ORDER BY created_at DESC
    ''', (employee_id,))
    
    tests = cursor.fetchall()  # List of tuples
    
    return render_template('my_tests.html', tests=tests)


#routing edit-test (edit_test.html) view test page - working fine
@app.route('/edit_test/<int:test_id>', methods=['GET', 'POST'])
def edit_test(test_id):
    # Check if teacher is logged in
    if 'employee_id' not in session:
        return redirect('teacher_signin')

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch test status and name
    cursor.execute("SELECT status, subject FROM tests WHERE test_id = ?", (test_id,))
    test_info = cursor.fetchone()
    if not test_info:
        flash('Test not found.')
        conn.close()
        return redirect('/teacher_dashboard')

    status, subject = test_info

    # POST: Only allow editing if status is 'draft'
    if request.method == 'POST':
        if status != 'draft':
            flash('You can only edit tests in draft status.')
            conn.close()
            return redirect('/teacher_dashboard')

        # Loop through submitted questions and update
        question_ids = request.form.getlist('question_id')
        for q_id in question_ids:
            question_text = request.form.get(f'question_text_{q_id}')
            rubric = request.form.get(f'rubric_{q_id}')
            max_marks = request.form.get(f'max_marks_{q_id}')
            cursor.execute('''
                UPDATE test_questions
                SET question_text = ?, rubric = ?, max_marks = ?
                WHERE question_id = ? AND test_id = ?
            ''', (question_text, rubric, int(max_marks), q_id, test_id))

        conn.commit()
        conn.close()
        flash('Test updated successfully!')
        return redirect('/teacher_dashboard')

    # GET: Fetch questions to pre-fill form
    cursor.execute('''
        SELECT question_id, question_no, question_text, rubric, max_marks
        FROM test_questions
        WHERE test_id = ?
        ORDER BY question_no
    ''', (test_id,))
    questions = cursor.fetchall()
    conn.close()

    return render_template(
        'edit_test.html',
        test_id=test_id,
        questions=questions,
        subject=subject,
        status=status
    )

#routing delete-test view test page- working fine
@app.route('/delete_test/<int:test_id>', methods=['POST'])
def delete_test(test_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Delete related questions first, if needed
    cursor.execute('DELETE FROM test_questions WHERE test_id = ?',( test_id, ))

    # Delete the test
    cursor.execute('DELETE FROM tests WHERE test_id = ?', (test_id,))
    
    conn.commit()
    conn.close()

    flash("Test deleted successfully.", "success")
    return redirect('/my_tests')

#routing-update status view test page - working fine
@app.route('/update_status/<int:test_id>', methods=['POST'])
def update_status(test_id):
    new_status = request.form.get('new_status')
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE tests SET status = ? WHERE test_id = ?', (new_status, test_id))
    conn.commit()
    conn.close()
    flash(f"Test status updated to '{new_status}'.", "success")
    return redirect('/my_tests')


@app.route('/view_students', methods=['GET', 'POST'])
def view_students():
    if 'employee_id' not in session:
        return redirect(url_for('teacher_signin'))

    teacher_id = session['employee_id']
    section = request.form.get('section') if request.method == 'POST' else None
    semester = request.form.get('semester') if request.method == 'POST' else None

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Get all students (optionally filtered by section/semester)
    if section and semester:
        cursor.execute('''
            SELECT usn, username AS name, section, semester
            FROM students
            WHERE section = ? AND semester = ?
        ''', (section, semester))
    else:
        cursor.execute('''
            SELECT usn, username AS name, section, semester
            FROM students
        ''')
    students = cursor.fetchall()

    # Get subjects for which the current teacher has created tests (optionally filtered by section/semester)
    if section and semester:
        cursor.execute('''
            SELECT DISTINCT subject
            FROM tests
            WHERE employee_id = ? AND section = ? AND semester = ?
        ''', (teacher_id, section, semester))
    else:
        cursor.execute('''
            SELECT DISTINCT subject
            FROM tests
            WHERE employee_id = ?
        ''', (teacher_id,))
    subjects = [row[0] for row in cursor.fetchall()]

    # For each student, check if they have taken each subject's test and calculate percentage
    results = []
    for student in students:
        usn = student[0]
        student_data = {
            'usn': usn,
            'name': student[1],
            'section': student[2],
            'semester': student[3],
            'subjects': {}
        }
        for subject in subjects:
            if section and semester:
                cursor.execute('''
                    SELECT sr.score, SUM(tq.max_marks) AS total_max_marks
                    FROM student_responses sr
                    JOIN tests t ON sr.test_id = t.test_id
                    JOIN test_questions tq ON tq.test_id = t.test_id
                    WHERE sr.usn = ? AND t.subject = ? AND t.section = ? AND t.semester = ?
                    GROUP BY sr.usn, sr.test_id, t.subject, t.section, t.semester
                ''', (usn, subject, section, semester))
            else:
                cursor.execute('''
                    SELECT sr.score, SUM(tq.max_marks) AS total_max_marks
                    FROM student_responses sr
                    JOIN tests t ON sr.test_id = t.test_id
                    JOIN test_questions tq ON tq.test_id = t.test_id
                    WHERE sr.usn = ? AND t.subject = ? AND t.employee_id = ?
                    GROUP BY sr.usn, sr.test_id, t.subject, t.employee_id
                ''', (usn, subject, teacher_id))
                
            result = cursor.fetchone()
            if result and result[0] is not None:  # Student has taken the test
                score, total_max_marks = result
                percentage = (score / total_max_marks) * 100
                student_data['subjects'][subject] = f"{percentage:.1f}%"
            else:
                student_data['subjects'][subject] = "Not Attended"
        results.append(student_data)

    conn.close()

    # Only show the table after filtering (on POST)
    show_table = request.method == 'POST'
    return render_template(
        'view_students.html',
        students=results,
        subjects=subjects,
        section=section,
        semester=semester,
        show_table=show_table
    )


#routing - student_signup (GET + POST) - working fine
@app.route('/student_signup', methods=['GET', 'POST'])
def student_signup():
    if request.method == 'POST':
        username = request.form['username']
        usn = request.form['usn']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm-password']
        section = request.form['section']
        semester = request.form['semester']  

        if password != confirm_password:
            flash("Passwords do not match", "student_error")
            return render_template('student_signup.html')

        try:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO students (username, usn, email, password, section, semester)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, usn, email, password,  section, semester))
            conn.commit()
            conn.close()
            flash("Student registered successfully!", "success")
            return redirect(url_for('student_signin'))
        except sqlite3.IntegrityError:
            flash("USN exists", "student_error")
            return render_template('student_signin.html')

    return render_template('student_signup.html')

#routing - student_signin - working fine
@app.route('/student_signin', methods=['GET', 'POST'])
def student_signin():
    if request.method == 'POST':
        usn = request.form['usn']
        password = request.form['password']

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM students WHERE usn = ? AND password = ?', (usn, password))
        student = cursor.fetchone()
        conn.close()

        if student:
            session['usn'] = student[1]
            flash('Login successful!', 'success')
            return redirect(url_for('student_dashboard',usn=usn))
        else:
            flash('Invalid USN or password', 'student_error')

    return render_template('student_signin.html')


#routing - student_dashboard working fine
@app.route('/student_dashboard')
def student_dashboard():
    usn = session.get('usn')
    if not usn:
        flash("Please sign in first.", "student_error")
        return redirect(url_for('student_signin'))
    
    session.pop('_flashes', None)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT test_id, subject,section,semester,total_questions, total_time, created_at FROM tests WHERE status = 'publish'")
    tests = cursor.fetchall()
    
     # Get test_ids that this student has already attempted
    cursor.execute("SELECT DISTINCT test_id FROM student_responses WHERE usn = ?", (usn,))
    attempted = set(row[0] for row in cursor.fetchall())
    conn.close()

    return render_template('student_dashboard.html', tests=tests,attempted=attempted,usn=session.get('usn'))


#routing start-test  working fine
@app.route('/start_test/<int:test_id>', methods=['GET', 'POST'])
def start_test(test_id):
    if 'usn' not in session:
        flash("Please sign in first.", "student_error")
        return redirect(url_for('student_signin'))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    if request.method == 'POST':
        usn = session['usn']
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        question_ids = request.form.getlist('question_id')
        answers = [request.form.get(f'answer_{qid}') for qid in question_ids]

        for qid, ans in zip(question_ids, answers):
            # Fetch question, rubric, max_marks for this question_id
            cursor.execute("SELECT question_text, rubric, max_marks FROM test_questions WHERE question_id = ?", (qid,))
            qrow = cursor.fetchone()
            if qrow:
                question_text, rubric, max_marks = qrow
                score, feedback = evaluate_answer_with_ollama(question_text, rubric, max_marks, ans)
            else:
                score, feedback = None, ""

            # Store answer, score, feedback in DB
            cursor.execute('''
                INSERT INTO student_responses (usn, test_id, question_id, answer_text, timestamp, score, feedback)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (usn, test_id, int(qid), ans, timestamp, score, feedback))

        conn.commit()
        conn.close()
        flash("Responses submitted and evaluated successfully!")
        return redirect(url_for('student_dashboard'))

    # GET method: fetch questions for this test #modified by joining 
    cursor.execute('''
        SELECT q.question_id, q.question_no, q.question_text, q.max_marks, t.subject, t.total_time
        FROM test_questions q
        JOIN tests t ON q.test_id = t.test_id
        WHERE q.test_id = ?
        ORDER BY q.question_no
    ''', (test_id,))
    questions = cursor.fetchall()
    subject = questions[0][4] if questions else "Unknown"
    total_time = questions[0][5] if questions else "Unknown"
    conn.close()


    if not questions:
        flash("No questions found for this test.", "student_error")
        return redirect(url_for('student_dashboard'))

    return render_template('start_test.html', test_id=test_id, questions=questions,subject=subject,total_time=total_time)


#routing answer evaluation working fine but takes time
def evaluate_answer_with_ollama(question, rubric, max_marks, answer):
    prompt = f"""
You are an exam evaluator. Here is the question, the rubric for grading, the maximum marks, and a student's answer.

Question: {question}
Rubric: {rubric}
Max Marks: {max_marks}
Student Answer: {answer}

Please:
1. Assign a score out of {max_marks} based on the rubric.
2. Provide a brief feedback in just 1 sentence explaining the score.

Respond in this format:
Score: <number>
Feedback: <brief feedback>
"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt},
            stream=True
        )
        result = ""
        for line in response.iter_lines():
            if line:
                data = line.decode('utf-8')
                try:
                    obj = json.loads(data)
                    if "response" in obj:
                        result += obj["response"]
                except Exception as e:
                    print("Error parsing Ollama response chunk:", e)
        # Extract score and feedback using regex
        score_match = re.search(r"Score:\s*(\d+)", result)
        feedback_match = re.search(r"Feedback:\s*(.*)", result, re.DOTALL)
        score = int(score_match.group(1)) if score_match else None
        feedback = feedback_match.group(1).strip() if feedback_match else ""
        return score, feedback
    except Exception as e:
        print("Ollama API exception:", e)
        return None, f"Automatic evaluation failed: {e}"


#routing view result working fine
@app.route('/view_test_result/<int:test_id>')
def view_test_result(test_id):
    if 'usn' not in session:
        flash("Please sign in first.", "student_error")
        return redirect(url_for('student_signin'))

    usn = session['usn']
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Fetch student name
    cursor.execute('SELECT username FROM students WHERE usn = ?', (usn,))
    student_row = cursor.fetchone()
    name = student_row[0] if student_row else usn
    
    
     # Fetch subject for this test_id
    cursor.execute('SELECT subject FROM tests WHERE test_id = ?', (test_id,))
    test_info = cursor.fetchone()
    subject = test_info[0] if test_info else "Unknown Subject"
    
    # Fetch all results for this student and test
    cursor.execute('''
        SELECT tq.question_no, tq.question_text, tq.rubric, tq.max_marks,
               sr.answer_text, sr.score, sr.feedback
        FROM student_responses sr
        JOIN test_questions tq ON sr.question_id = tq.question_id
        WHERE sr.usn = ? AND sr.test_id = ?
        ORDER BY tq.question_no
    ''', (usn, test_id))
    results = cursor.fetchall()
    
    # Calculate total obtained and total max marks
    total_obtained = sum(q[5] for q in results if q[5] is not None)
    total_max = sum(q[3] for q in results)
    percentage = (total_obtained / total_max * 100) if total_max > 0 else 0
    
    eligible = percentage > 35
    
    conn.close()

    return render_template('view_test_result.html', test_id=test_id, subject=subject,results=results,total_obtained=total_obtained,
        total_max=total_max,
        percentage=round(percentage, 2),
        eligible=eligible,
        name=name,
        usn=usn)


#routing download certificate
@app.route('/download_certificate/<int:test_id>', methods=['POST'])
def download_certificate(test_id):
    if 'usn' not in session:
        flash("Please sign in first.", "student_error")
        return redirect(url_for('student_signin'))

    usn = session['usn']
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM students WHERE usn = ?', (usn,))
    student_row = cursor.fetchone()
    name = student_row[0] if student_row else usn

    cursor.execute('SELECT subject FROM tests WHERE test_id = ?', (test_id,))
    test_info = cursor.fetchone()
    subject = test_info[0] if test_info else "Unknown Subject"

    cursor.execute('''
        SELECT tq.max_marks, sr.score
        FROM student_responses sr
        JOIN test_questions tq ON sr.question_id = tq.question_id
        WHERE sr.usn = ? AND sr.test_id = ?
    ''', (usn, test_id))
    marks = cursor.fetchall()
    total_obtained = sum(q[1] for q in marks if q[1] is not None)
    total_max = sum(q[0] for q in marks)
    percentage = (total_obtained / total_max * 100) if total_max > 0 else 0

    conn.close()

    # Only allow download if eligible
    if percentage <= 35:
        flash("You are not eligible for a certificate.", "error")
        return redirect(url_for('view_test_result', test_id=test_id))

    # Render certificate HTML
    certificate_html = render_template_string("""
    <html>
    <head>
        <style>
            body { background: #f7f7f7; font-family: 'Georgia', serif; }
            .cert-container {
                background: #fff;
                border: 8px solid #4b6cb7;
                border-radius: 18px;
                max-width: 650px;
                margin: 60px auto;
                padding: 48px 36px;
                box-shadow: 0 8px 32px rgba(75,108,183,0.18);
                text-align: center;
            }
            .cert-title {
                font-size: 2.5em;
                font-weight: bold;
                color: #4b6cb7;
                margin-bottom: 24px;
            }
            .cert-body {
                font-size: 1.3em;
                color: #222;
                margin-bottom: 32px;
            }
            .cert-footer {
                margin-top: 36px;
                font-size: 1em;
                color: #888;
            }
            .cert-highlight {
                color: #182848;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="cert-container">
            <div class="cert-title">Certificate of Completion</div>
            <div class="cert-body">
                This is to certify that<br><br>
                <span class="cert-highlight">{{ name }}</span> (USN: <span class="cert-highlight">{{ usn }}</span>)<br><br>
                has successfully completed the course<br>
                <span class="cert-highlight">{{ subject }}</span><br>
                in the year 2025 with a percentage of<br>
                <span class="cert-highlight">{{ percentage }}%</span>.
            </div>
            <div class="cert-footer">
                GradeMate &mdash; {{ now }}
            </div>
        </div>
    </body>
    </html>
    """, name=name, usn=usn, subject=subject, percentage=round(percentage, 2), now=datetime.now().strftime("%d %B %Y"))

    # Generate PDF
    
    pdf = pdfkit.from_string(certificate_html, False, configuration=config)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=certificate_{usn}_{test_id}.pdf'
    return response


# Logout route for both admin , teacher, student
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('home'))


#uplodas must be accessible from flask
@app.route('/uploads/<folder>/<filename>')
def uploaded_file(folder, filename):
    return send_from_directory(f'uploads/{folder}', filename)


if __name__ == '__main__':
    app.run(port=8080)
