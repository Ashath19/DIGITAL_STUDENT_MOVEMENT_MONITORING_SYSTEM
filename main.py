import streamlit as st
from Google import Create_Service
import base64
import cv2
import os
import mysql.connector
from datetime import datetime, timedelta, time
from PIL import Image
import numpy as np
import pandas as pd
import re
import json
from email.mime.text import MIMEText
import threading
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import plotly.express as px

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="sdmit",
        database="hostelmovement"
    )

# Utility Functions
def validate_student_inputs(name, usn):
    if not re.match(r'^[a-zA-Z\s]+$', name):
        return False, "Name must contain only letters and spaces."
    if not re.match(r'^[a-zA-Z0-9]+$', usn):
        return False, "USN must be alphanumeric."
    return True, ""


def load_haarcascade(filepath="haarcascade_frontalface_default.xml"):
    if not os.path.isfile(filepath):
        st.error(f"Haar cascade file missing: {filepath}")
        return None
    try:
        cascade = cv2.CascadeClassifier(filepath)
        if cascade.empty():
            raise ValueError("Failed to load Haar cascade file.")
        return cascade
    except Exception as e:
        st.error(f"Error loading Haar cascade: {e}")
        return None

def format_time(mysql_time):
    if pd.isnull(mysql_time) or mysql_time is None:
        return None
    if isinstance(mysql_time, timedelta):
        total_seconds = int(mysql_time.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    elif isinstance(mysql_time, time):
        return mysql_time.strftime("%H:%M:%S")
    elif isinstance(mysql_time, str):
        return mysql_time
    else:
        return None

# Authentication Functions
def verify_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

def setup_email_service():
    try:
        CLIENT_SECRET_FILE = 'client_secret.json'
        API_NAME = 'gmail'
        API_VERSION = 'v1'
        SCOPES = ['https://mail.google.com/']
        
        service = Create_Service(CLIENT_SECRET_FILE, API_NAME, API_VERSION, SCOPES)
        return service
    except Exception as e:
        st.error(f"Email service setup failed: {e}")
        return None

def generate_attendance_pie_chart(selected_date):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch total number of students
    cursor.execute("SELECT COUNT(*) as total_students FROM student_details")
    total_students = cursor.fetchone()['total_students']

    # Fetch attendance data
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN a.arrival_time IS NULL AND a.departure_time IS NOT NULL THEN 1 END) as still_out,
            COUNT(CASE WHEN a.arrival_time IS NOT NULL AND TIMESTAMPDIFF(HOUR, a.departure_time, a.arrival_time) <= 1 THEN 1 END) as on_time,
            COUNT(CASE WHEN a.arrival_time IS NOT NULL AND TIMESTAMPDIFF(HOUR, a.departure_time, a.arrival_time) > 1 THEN 1 END) as late
        FROM attendance a
        WHERE a.date = %s
    """, (selected_date,))
    attendance_data = cursor.fetchone()
    conn.close()

    still_out = attendance_data['still_out']
    on_time = attendance_data['on_time']
    late = attendance_data['late']
    not_departed = total_students - (still_out + on_time + late)

    labels = ['Still Out', 'On Time', 'Late', 'Not Departed']
    values = [still_out, on_time, late, not_departed]

    fig = px.pie(values=values, names=labels, title=f'Attendance Pie Chart for {selected_date}', hole=0.3)
    st.plotly_chart(fig)


def send_overtime_email(service, student_email, student_name, departure_time):
    def send_email():
        try:
            email_msg = f"""
            Dear Parent/Guardian,
            
            This is to inform you that {student_name} has not returned to the hostel within the expected time.
            Departure Time: {departure_time}
            Current Time: {datetime.now().strftime('%H:%M:%S')}
            
            Please contact the hostel authorities for more information.
            
            Regards,
            Hostel Management
            """
            
            mime_message = MIMEMultipart()
            mime_message['to'] = student_email
            mime_message['subject'] = 'Student Overtime Alert'
            mime_message.attach(MIMEText(email_msg, 'plain'))
            
            raw_string = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
            
            service.users().messages().send(
                userId='me', 
                body={'raw': raw_string}
            ).execute()
            
            st.success(f"Email sent to {student_email}")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

    # Run the send_email function in a separate thread
    email_thread = threading.Thread(target=send_email)
    email_thread.start()

def check_overtime_students(time_limit):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    current_time = datetime.now()
    
    # Get students who haven't returned within time limit
    query = """
    SELECT a.usn, a.departure_time, s.name, s.email
    FROM attendance a
    JOIN student_details s ON a.usn = s.usn
    WHERE a.date = CURDATE()
    AND a.departure_time IS NOT NULL 
    AND a.arrival_time IS NULL
    AND TIMESTAMPDIFF(HOUR, a.departure_time, NOW()) >= %s
    """
    
    cursor.execute(query, (time_limit,))
    overtime_students = cursor.fetchall()
    
    if overtime_students:
        email_service = setup_email_service()
        if email_service:
            for student in overtime_students:
                send_overtime_email(
                    email_service,
                    student['email'],
                    student['name'],
                    format_time(student['departure_time'])
                )
                st.warning(f"Overtime alert sent for {student['name']}")
    
    conn.close()
    return overtime_students

def login():
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = verify_user(username, password)
        if user:
            st.session_state['logged_in'] = True
            st.session_state['user'] = user
            st.success(f"Logged in as {user['role']}")
            st.rerun()
        else:
            st.error("Invalid username or password")

# Core Functionalities
def register_student(name, usn, batch, branch, parent_phone, student_phone, address, father_name, mother_name, room_number, email):
    conn = get_db_connection()
    cursor = conn.cursor()
    is_valid, error_message = validate_student_inputs(name, usn)
    if not is_valid:
        st.error(error_message)
        return
    try:
        cursor.execute("""
            INSERT INTO student_details 
            (name, usn, batch, branch, parent_phone, student_phone, address, father_name, mother_name, room_number, email, face_registered)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, usn, batch, branch, parent_phone, student_phone, address, father_name, mother_name, room_number, email, False))
        conn.commit()
        st.success(f"Student {name} registered successfully!")
    except mysql.connector.IntegrityError:
        st.error("USN already exists! Please check the student details.")
    finally:
        conn.close()

def take_images(usn):
    detector = load_haarcascade()
    if detector is None:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_details WHERE usn = %s", (usn,))
    student = cursor.fetchone()
    if not student:
        st.error("Student USN not found! Please register the student first.")
        conn.close()
        return
    if student[-1]:
        st.error("Face already registered for this student.")
        conn.close()
        return
    name = student[1]
    cap = cv2.VideoCapture(0)
    sampleNum = 0
    st.info("Capturing images. Please look at the camera.")
    if not os.path.exists("TrainingImage/"):
        os.makedirs("TrainingImage/")
    
    # Create a placeholder for the video frame
    video_placeholder = st.empty()
    
    while sampleNum < 100:
        ret, frame = cap.read()
        if not ret:
            st.error("Failed to access the camera.")
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces:
            sampleNum += 1
            cv2.imwrite(f"TrainingImage/{usn}_{sampleNum}.jpg", gray[y:y+h, x:x+w])
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
        # Update the video frame in the placeholder
        video_placeholder.image(frame, channels="BGR", use_container_width=True)
    cap.release()
    cursor.execute("UPDATE student_details SET face_registered = %s WHERE usn = %s", (True, usn))
    conn.commit()
    conn.close()
    st.success(f"Images captured successfully for {name} and face registered!")

def train_model():
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    faces = []
    labels = []
    usn_to_label = {}
    label_to_usn = {}
    current_label = 0
    image_paths = [os.path.join("TrainingImage", f) for f in os.listdir("TrainingImage") if f.endswith(".jpg")]
    
    for image_path in image_paths:
        try:
            img = Image.open(image_path).convert('L')
            img_np = np.array(img, 'uint8')
            usn = os.path.basename(image_path).split("_")[0]
            
            if usn not in usn_to_label:
                usn_to_label[usn] = current_label
                label_to_usn[current_label] = usn
                current_label += 1
            label = usn_to_label[usn]
            faces.append(img_np)
            labels.append(label)
        except Exception as e:
            st.error(f"Error processing file {image_path}: {e}")
    
    if faces and labels:
        recognizer.train(faces, np.array(labels))
        if not os.path.exists("TrainingImageLabel"):
            os.makedirs("TrainingImageLabel")
        recognizer.save("TrainingImageLabel/Trainer.yml")
        
        # Save the label mapping
        with open("TrainingImageLabel/label_mapping.json", "w") as f:
            json.dump(label_to_usn, f)
        
        st.success("Model trained successfully!")
    else:
        st.error("No valid training data found.")

def get_todays_movements():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    today = datetime.now().date()
    
    query = """
    SELECT a.usn, s.name, a.departure_time, a.arrival_time, a.destination
    FROM attendance a
    JOIN student_details s ON a.usn = s.usn
    WHERE a.date = %s
    """
    
    cursor.execute(query, (today,))
    movements = cursor.fetchall()
    conn.close()
    if movements:
        print("Keys in the first movement record:", movements[0].keys())  # Debugging statement
    return movements

def take_attendance():
    detector = load_haarcascade()
    if detector is None:
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    if not os.path.isfile("TrainingImageLabel/Trainer.yml"):
        st.error("No training data found. Please train the model first.")
        return
    recognizer.read("TrainingImageLabel/Trainer.yml")

    # Load the label mapping
    try:
        with open("TrainingImageLabel/label_mapping.json", "r") as f:
            label_to_usn = json.load(f)
    except Exception as e:
        st.error("Failed to load label mapping.")
        return

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Attendance type
    attendance_type = st.radio(
        "Select Attendance Type",
        ["Departing (Enter Destination)", "Returning"],
        index=0
    )

    if attendance_type == "Departing (Enter Destination)":
        destination = st.text_input("Enter Destination")
        if not destination:
            st.warning("Please provide a destination.")
            return
    else:
        destination = None  # Returning students don't need a destination

    if st.button("Start Face Scan"):
        cap = cv2.VideoCapture(0)  # Initialize the camera
        placeholder = st.empty()  # Create a placeholder for the video frame
        scanned = False

        start_time = time.time()
        countdown = 3  # 3 seconds countdown

        try:
            while not scanned:
                ret, frame = cap.read()
                if not ret:
                    st.error("Could not access the webcam.")
                    break

                elapsed_time = time.time() - start_time
                countdown = 3 - int(elapsed_time)

                # Overlay countdown on the frame
                cv2.putText(frame, f"Countdown: {countdown}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

                for (x, y, w, h) in faces:
                    serial, conf = recognizer.predict(gray[y:y+h, x:x+w])
                    if conf < 80:  # Adjust the confidence threshold as needed
                        label = serial
                        usn = label_to_usn.get(str(label))
                        if usn:
                            cursor.execute("SELECT * FROM student_details WHERE usn = %s", (usn,))
                            student = cursor.fetchone()
                            if student:
                                name = student['name']
                                current_date = datetime.now().date()
                                current_time = datetime.now().time()

                                if attendance_type == "Departing (Enter Destination)":
                                    # Check if student already departed
                                    cursor.execute("""
                                        SELECT departure_time 
                                        FROM attendance 
                                        WHERE usn = %s AND date = %s AND departure_time IS NOT NULL
                                    """, (usn, current_date))
                                    existing_departure = cursor.fetchone()
                                    
                                    if existing_departure:
                                        departure_time = format_time(existing_departure['departure_time'])
                                        st.warning(f"{name} has already departed today at {departure_time}")
                                        scanned = True
                                    else:
                                        cursor.execute("""
                                            INSERT INTO attendance (usn, date, departure_time, destination)
                                            VALUES (%s, %s, %s, %s)
                                            ON DUPLICATE KEY UPDATE departure_time = %s, destination = %s
                                        """, (usn, current_date, current_time, destination, current_time, destination))
                                        st.success(f"Departure marked for {name} to {destination}")
                                        conn.commit()
                                        scanned = True
                                elif attendance_type == "Returning":
                                    cursor.execute("""
                                        UPDATE attendance
                                        SET arrival_time = %s
                                        WHERE usn = %s AND date = %s AND arrival_time IS NULL
                                    """, (current_time, usn, current_date))
                                    st.success(f"Arrival marked for {name}")
                                conn.commit()
                                scanned = True
                            else:
                                st.error("Student not found in the database.")
                        else:
                            st.error("Unrecognized label.")
                    else:
                        cv2.putText(frame, "Unknown", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    # Draw a rectangle around the detected face
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

                # Update the placeholder with the current frame
                placeholder.image(frame, channels="BGR", use_container_width=True)

                if elapsed_time >= 3:
                    break

        finally:
            cap.release()  # Release the camera resource
            conn.close()
            st.success("Attendance cycle completed. Restart to process the next student.")
# Supervisor Dashboard
def supervisor_dashboard():
    st.subheader("Supervisor Dashboard")
    st.write("Manage all users, roles, and attendance records.")
    
    menu = ["Manage Users", "View Attendance Records", "View Deleted Records", "Overtime Settings"]
    choice = st.sidebar.selectbox("Select Action", menu)

    if choice == "Overtime Settings":
        st.subheader("Overtime Monitoring Settings")
        
        # Enable/Disable Monitoring
        if 'overtime_monitoring' not in st.session_state:
            st.session_state['overtime_monitoring'] = False
            
        st.session_state['overtime_monitoring'] = st.toggle("Enable Overtime Monitoring")
        
        time_limit = st.number_input("Time Limit (hours)", 
                                   min_value=1, 
                                   max_value=24, 
                                   value=1)
        
        check_interval = st.number_input("Check Interval (minutes)", 
                                       min_value=1,
                                       max_value=60,
                                       value=1)
        
        if st.session_state['overtime_monitoring']:
            st.info("Overtime monitoring is active")
            if 'last_check' not in st.session_state:
                st.session_state['last_check'] = datetime.now()
                print(st.session_state['last_check'])
                
            current_time = datetime.now()
            if (current_time - st.session_state['last_check']).seconds >= (check_interval * 60):
                overtime_students = check_overtime_students(time_limit)
                if overtime_students:
                    st.warning(f"Found {len(overtime_students)} students over time limit")
                st.session_state['last_check'] = current_time
        else:
            st.info("Overtime monitoring is paused")
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if choice == "Manage Users":
        st.subheader("User Management")
        crud_action = st.selectbox("Select Action", 
                              ["Create User", "View Users", "Update User", "Delete User", "Manage Supervisors"],
                              index=0)
        
        if crud_action == "Create User":
            st.subheader("Create New User")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["Supervisor", "Admin", "Warden", "Attendance Desk"])
            
            if st.button("Create User"):
                try:
                    cursor.execute("""
                        INSERT INTO users (username, password, role) 
                        VALUES (%s, %s, %s)
                    """, (username, password, role))
                    conn.commit()
                    st.success(f"{role} {username} created successfully!")
                except mysql.connector.IntegrityError:
                    st.error("Username already exists!")
                    
        elif crud_action == "View Users":
            st.subheader("Current Users")
            cursor.execute("SELECT id, username, role FROM users")
            users = cursor.fetchall()
            if users:
                df = pd.DataFrame(users, columns=["ID", "Username", "Role"])
                st.dataframe(df)
            else:
                st.info("No users found")
                
        elif crud_action == "Update User":
            st.subheader("Update User")
            cursor.execute("SELECT username, role FROM users")
            users = cursor.fetchall()
            if users:
                selected_user = st.selectbox("Select User", 
                                           [f"{user[0]} ({user[1]})" for user in users])
                username = selected_user.split(" (")[0]
                
                new_password = st.text_input("New Password", type="password")
                new_role = st.selectbox("New Role", 
                                      ["Supervisor", "Admin", "Warden", "Attendance Desk"])
                
                if st.button("Update User"):
                    if new_password:
                        cursor.execute("""
                            UPDATE users 
                            SET password = %s, role = %s 
                            WHERE username = %s
                        """, (new_password, new_role, username))
                    else:
                        cursor.execute("""
                            UPDATE users 
                            SET role = %s 
                            WHERE username = %s
                        """, (new_role, username))
                    conn.commit()
                    st.success(f"User {username} updated to {new_role}!")
            else:
                st.info("No users found")
                
        elif crud_action == "Delete User":
            st.subheader("Delete User")
            cursor.execute("SELECT username, role FROM users")
            users = cursor.fetchall()
            if users:
                selected_user = st.selectbox("Select User to Delete", 
                                           [f"{user[0]} ({user[1]})" for user in users])
                username = selected_user.split(" (")[0]
                
                if st.button("Delete User"):
                    cursor.execute("DELETE FROM users WHERE username = %s", (username,))
                    conn.commit()
                    st.success(f"User {username} deleted successfully!")
            else:
                st.info("No users found")
                
        elif crud_action == "Manage Supervisors":
            st.subheader("Manage Supervisors")
            
            # View current supervisors
            cursor.execute("SELECT username FROM users WHERE role = 'Supervisor'")
            supervisors = cursor.fetchall()
            if supervisors:
                st.write("Current Supervisors:")
                for sup in supervisors:
                    st.write(f"- {sup[0]}")
            else:
                st.info("No supervisors found")
    
    elif choice == "View Attendance Records":
        st.subheader("View Attendance Records")

        # Default date to today's date
        today = datetime.today().date()

        # Filters
        st.write("**Filters**")
        cursor.execute("SELECT usn, name FROM student_details")
        students = cursor.fetchall()
        student_options = {f"{row[1]} ({row[0]})": row[0] for row in students}
        student_filter = st.selectbox("Filter by Student", ["All"] + list(student_options.keys()))

        # Date filters
        date_filter = st.date_input("Select Date", value=today)
        range_filter = st.checkbox("Filter by Date Range")
        if range_filter:
            start_date = st.date_input("Start Date", value=today)
            end_date = st.date_input("End Date", value=today)
        else:
            start_date = end_date = date_filter

        # Hour filters
        hour_filter = st.checkbox("Filter by Hour")
        if hour_filter:
            start_hour = st.number_input("Start Hour (0-23)", min_value=0, max_value=23, value=0, step=1)
            end_hour = st.number_input("End Hour (0-23)", min_value=0, max_value=23, value=23, step=1)
        else:
            start_hour, end_hour = None, None

        # Build query with filters
        query = """
            SELECT id, usn, date, departure_time, arrival_time, destination
            FROM attendance
            WHERE deleted = FALSE
            AND date BETWEEN %s AND %s
        """
        params = [start_date, end_date]

        if student_filter != "All":
            query += " AND usn = %s"
            params.append(student_options[student_filter])

        if hour_filter:
            query += " AND (HOUR(departure_time) BETWEEN %s AND %s OR HOUR(arrival_time) BETWEEN %s AND %s)"
            params.extend([start_hour, end_hour, start_hour, end_hour])

        # Fetch and display records
        cursor.execute(query, params)
        records = cursor.fetchall()

        if records:
            df = pd.DataFrame(records, columns=["ID", "USN", "Date", "Departure Time", "Arrival Time", "Destination"])
            df["Departure Time"] = df["Departure Time"].apply(format_time)
            df["Arrival Time"] = df["Arrival Time"].apply(format_time)
            st.dataframe(df, use_container_width=True)
            st.write(f"Total Records: {len(df)}")
        else:
            st.info("No attendance records found for the selected criteria.")

    elif choice == "View Deleted Records":
        st.subheader("View Deleted Attendance Records")

        # Default date to today's date
        today = datetime.today().date()

        # Filters
        st.write("**Filters**")
        date_filter = st.date_input("Select Date", value=today)
        range_filter = st.checkbox("Filter by Date Range")
        if range_filter:
            start_date = st.date_input("Start Date", value=today)
            end_date = st.date_input("End Date", value=today)
        else:
            start_date = end_date = date_filter

        hour_filter = st.checkbox("Filter by Hour")
        if hour_filter:
            start_hour = st.number_input("Start Hour (0-23)", min_value=0, max_value=23, value=0, step=1)
            end_hour = st.number_input("End Hour (0-23)", min_value=0, max_value=23, value=23, step=1)
        else:
            start_hour, end_hour = None, None

        query = """
            SELECT id, usn, date, departure_time, arrival_time, destination
            FROM attendance
            WHERE deleted = TRUE
            AND date BETWEEN %s AND %s
        """
        params = [start_date, end_date]

        if hour_filter:
            query += " AND (HOUR(departure_time) BETWEEN %s AND %s OR HOUR(arrival_time) BETWEEN %s AND %s)"
            params.extend([start_hour, end_hour, start_hour, end_hour])

        cursor.execute(query, params)
        records = cursor.fetchall()

        if records:
            df = pd.DataFrame(records, columns=["ID", "USN", "Date", "Departure Time", "Arrival Time", "Destination"])
            df["Departure Time"] = df["Departure Time"].apply(format_time)
            df["Arrival Time"] = df["Arrival Time"].apply(format_time)
            df["Status"] = "Deleted"
            st.dataframe(df, use_container_width=True)
            st.write(f"Total Records: {len(df)}")
        else:
            st.info("No deleted attendance records found.")

    conn.close()

def admin_dashboard():
    st.subheader("Admin Dashboard")
    st.write("Manage users and attendance records.")

    menu = ["Manage Users", "View Attendance Records", "Delete Attendance Record"]
    choice = st.sidebar.selectbox("Select Action", menu)

    conn = get_db_connection()
    cursor = conn.cursor()

    if choice == "Manage Users":
        st.subheader("Manage Users")

        user_menu = ["Create User", "View Users", "Delete User"]
        user_choice = st.selectbox("Select User Action", user_menu)

        if user_choice == "Create User":
            st.subheader("Create New User")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["Admin", "Warden", "Attendance Desk"])  # Exclude Supervisor
            if st.button("Create User"):
                try:
                    cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", 
                                   (username, password, role))
                    conn.commit()
                    st.success(f"User {username} created successfully with role {role}!")
                except mysql.connector.IntegrityError:
                    st.error("Username already exists!")

        elif user_choice == "View Users":
            st.subheader("List of Users")
            cursor.execute("SELECT id, username, role FROM users WHERE role != 'Supervisor'")
            records = cursor.fetchall()
            if records:
                df = pd.DataFrame(records, columns=["ID", "Username", "Role"])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No users found.")

        elif user_choice == "Delete User":
            st.subheader("Delete User")
            cursor.execute("SELECT username FROM users WHERE role != 'Supervisor'")
            records = cursor.fetchall()
            if records:
                users = [row[0] for row in records]
                selected_user = st.selectbox("Select User to Delete", users)
                if st.button("Delete User"):
                    cursor.execute("DELETE FROM users WHERE username = %s", (selected_user,))
                    conn.commit()
                    st.success(f"User {selected_user} deleted successfully!")
            else:
                st.info("No users found.")

    elif choice == "View Attendance Records":
        st.subheader("View Attendance Records")
        today = datetime.today().date()

        # Filters
        st.write("**Filters**")
        cursor.execute("SELECT usn, name FROM student_details")
        students = cursor.fetchall()
        student_options = {f"{row[1]} ({row[0]})": row[0] for row in students}
        student_filter = st.selectbox("Filter by Student", ["All"] + list(student_options.keys()))

        date_filter = st.date_input("Select Date", value=today)
        range_filter = st.checkbox("Filter by Date Range")
        if range_filter:
            start_date = st.date_input("Start Date", value=today)
            end_date = st.date_input("End Date", value=today)
        else:
            start_date = end_date = date_filter

        # Build query with filters
        query = """
            SELECT id, usn, date, departure_time, arrival_time, destination
            FROM attendance
            WHERE deleted = FALSE
            AND date BETWEEN %s AND %s
        """
        params = [start_date, end_date]

        if student_filter != "All":
            query += " AND usn = %s"
            params.append(student_options[student_filter])

        # Fetch and display records
        cursor.execute(query, params)
        records = cursor.fetchall()

        if records:
            df = pd.DataFrame(records, columns=["ID", "USN", "Date", "Departure Time", "Arrival Time", "Destination"])
            df["Departure Time"] = df["Departure Time"].apply(format_time)
            df["Arrival Time"] = df["Arrival Time"].apply(format_time)
            st.dataframe(df, use_container_width=True)
            st.write(f"Total Records: {len(df)}")
        else:
            st.info("No attendance records found for the selected criteria.")

    elif choice == "Delete Attendance Record":
        st.subheader("Delete Attendance Record")
        cursor.execute("""
            SELECT id, usn, date, departure_time, arrival_time, destination 
            FROM attendance 
            WHERE deleted = FALSE
        """)
        records = cursor.fetchall()

        if records:
            df = pd.DataFrame(records, columns=["ID", "USN", "Date", "Departure Time", "Arrival Time", "Destination"])
            df["Departure Time"] = df["Departure Time"].apply(format_time)
            df["Arrival Time"] = df["Arrival Time"].apply(format_time)
            st.dataframe(df, use_container_width=True)

            record_id = st.number_input("Enter Record ID to Delete", min_value=1, step=1)
            if st.button("Delete Record"):
                cursor.execute("UPDATE attendance SET deleted = TRUE WHERE id = %s", (record_id,))
                conn.commit()
                st.success(f"Record {record_id} marked as deleted.")
        else:
            st.info("No attendance records available to delete.")

    conn.close()

def warden_dashboard():
    st.subheader("Warden Dashboard")
    st.write("Manage student details and attendance reports.")
    
    menu = ["View Today's Movements", "Generate Attendance Report", "Add Student", "Take Photos for Training", "View Attendance Pie Chart"]
    choice = st.sidebar.selectbox("Select Action", menu)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if choice == "View Today's Movements":
        st.subheader("Today's Movements")
        movements = get_todays_movements()
        if movements:
            df = pd.DataFrame(movements)
            df.rename(columns={
                'usn': 'USN',
                'name': 'Name',
                'departure_time': 'Departure Time',
                'arrival_time': 'Arrival Time',
                'destination': 'Destination'
            }, inplace=True)
            df["Departure Time"] = df["Departure Time"].apply(format_time)
            df["Arrival Time"] = df["Arrival Time"].apply(format_time)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No movements recorded for today.")
    
    elif choice == "Generate Attendance Report":
        st.subheader("Generate Attendance Report")
        cursor.execute("SELECT usn, name FROM student_details")
        students = cursor.fetchall()
        student_options = {f"{row[1]} ({row[0]})": row[0] for row in students}
        student_filter = st.selectbox("Select Student for Report", ["All"] + list(student_options.keys()))
        
        date_filter = st.date_input("Select Date", value=datetime.today().date())
        range_filter = st.checkbox("Filter by Date Range")
        if range_filter:
            start_date = st.date_input("Start Date", value=datetime.today().date())
            end_date = st.date_input("End Date", value=datetime.today().date())
        else:
            start_date = end_date = date_filter
        
        query = """
            SELECT a.usn, s.name, a.date, a.departure_time, a.arrival_time, a.destination
            FROM attendance a
            INNER JOIN student_details s ON a.usn = s.usn
            WHERE a.date BETWEEN %s AND %s
        """
        params = [start_date, end_date]
        
        if student_filter != "All":
            query += " AND a.usn = %s"
            params.append(student_options[student_filter])
        
        cursor.execute(query, params)
        records = cursor.fetchall()
        
        if records:
            df= pd.DataFrame(records, columns=["USN", "Name", "Date", "Departure Time", "Arrival Time", "Destination"])
            df["Departure Time"] = df["Departure Time"].apply(format_time)
            df["Arrival Time"] = df["Arrival Time"].apply(format_time)
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Report as CSV",
                data=csv,
                file_name="attendance_report.csv",
                mime="text/csv",
            )
        else:
            st.info("No attendance records found for the selected criteria.")
    
    elif choice == "Add Student":
        st.subheader("Add Student")
        name = st.text_input("Student Name")
        usn = st.text_input("USN")
        batch = st.text_input("Batch")
        branch = st.text_input("Branch")
        parent_phone = st.text_input("Parent Phone")
        student_phone = st.text_input("Student Phone")
        address = st.text_area("Address")
        father_name = st.text_input("Father's Name")
        mother_name = st.text_input("Mother's Name")
        room_number = st.text_input("Room Number")
        email = st.text_input("Email")
        
        if st.button("Add Student"):
            is_valid, error_message = validate_student_inputs(name, usn)
            if not is_valid:
                st.error(error_message)
            else:
                try:
                    cursor.execute("""
                        INSERT INTO student_details 
                        (name, usn, batch, branch, parent_phone, student_phone, address, father_name, mother_name, room_number, email, face_registered)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (name, usn, batch, branch, parent_phone, student_phone, address, father_name, mother_name, room_number, email, False))
                    conn.commit()
                    st.success(f"Student {name} added successfully!")
                except mysql.connector.IntegrityError:
                    st.error("USN already exists!")
    
    elif choice == "Take Photos for Training":
        st.subheader("Take Photos for Training")
        
        cursor.execute("SELECT usn, name FROM student_details WHERE face_registered = FALSE")
        students = cursor.fetchall()
        student_options = {f"{row[1]} ({row[0]})": row[0] for row in students}
        
        if student_options:
            usn = st.selectbox("Select Student", list(student_options.keys()))
            usn_value = student_options[usn]
            if st.button("Capture Photos"):
                take_images(usn_value)
        else:
            st.info("No students found with unregistered faces.")
        if st.button("Train Model"):
            train_model()
    
    elif choice == "View Attendance Pie Chart":
        st.subheader("Attendance Pie Chart")
        selected_date = st.date_input("Select Date", value=datetime.today().date())
        generate_attendance_pie_chart(selected_date)
    
    conn.close()

def attendance_desk_dashboard():
    st.subheader("Attendance Desk")
    st.write("This section is for taking attendance only.")
    detector = load_haarcascade()
    if detector is None:
        return
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    if not os.path.isfile("TrainingImageLabel/Trainer.yml"):
        st.error("No training data found. Please train the model first.")
        return
    recognizer.read("TrainingImageLabel/Trainer.yml")
    conn = get_db_connection()
    cursor = conn.cursor()
    # Attendance type
    attendance_type = st.radio(
        "Select Attendance Type",
        ["Departing (Enter Destination)", "Returning"],
        index=0
    )
    if attendance_type == "Departing (Enter Destination)":
        destination = st.text_input("Enter Destination")
        if not destination:
            st.warning("Please provide a destination.")
            return
    else:
        destination = None  # Returning students don't need a destination
    if st.button("Start Face Scan"):
        cap = cv2.VideoCapture(0)  # Initialize the camera
        placeholder = st.empty()  # Create a placeholder for the video frame
        scanned = False
        try:
            while not scanned:
                ret, frame = cap.read()
                if not ret:
                    st.error("Could not access the webcam.")
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
                for (x, y, w, h) in faces:
                    serial, conf = recognizer.predict(gray[y:y+h, x:x+w])
                    with open("TrainingImageLabel/label_mapping.json", "r") as f:
                        label_to_usn = json.load(f)
                    usn = label_to_usn.get(str(serial))
                    if conf < 80:
                        cursor.execute("SELECT * FROM student_details WHERE USN = %s", (usn,))
                        student = cursor.fetchone()
                        if student:
                            usn, name = student[2], student[1]
                            current_date = datetime.now().date()
                            current_time = datetime.now().time()
                            if attendance_type == "Departing (Enter Destination)":
                                # Check if student already departed
                                cursor.execute("""
                                    SELECT departure_time 
                                    FROM attendance 
                                    WHERE usn = %s AND date = %s AND departure_time IS NOT NULL
                                """, (usn, current_date))
                                existing_departure = cursor.fetchone()
                                
                                if existing_departure:
                                    departure_time = format_time(existing_departure[0])
                                    st.warning(f"{name} has already departed today at {departure_time}")
                                    scanned = True
                                else:
                                    cursor.execute("""
                                        INSERT INTO attendance (usn, date, departure_time, destination)
                                        VALUES (%s, %s, %s, %s)
                                        ON DUPLICATE KEY UPDATE departure_time = %s, destination = %s
                                    """, (usn, current_date, current_time, destination, current_time, destination))
                                    st.success(f"Departure marked for {name} to {destination}")
                                    conn.commit()
                                    scanned = True
                            elif attendance_type == "Returning":
                                cursor.execute("""
                                    UPDATE attendance
                                    SET arrival_time = %s
                                    WHERE usn = %s AND date = %s AND arrival_time IS NULL
                                """, (current_time, usn, current_date))
                                st.success(f"Arrival marked for {name}")
                                print(serial)
                            conn.commit()
                            scanned = True
                        else:
                            cv2.putText(frame, "Student not recognized!", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    else:
                        cv2.putText(frame, "Unknown", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    # Draw a rectangle around the detected face
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

                # Update the placeholder with the current frame
                placeholder.image(frame, channels="BGR", use_container_width=True)

        finally:
            cap.release()
            conn.close()
            st.success("Attendance cycle completed. Restart to process the next student.")
# Main Application
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user'] = None
    if not st.session_state['logged_in']:
        login()
    else:
        user = st.session_state['user']
        role = user['role']
        st.sidebar.title(f"Logged in as {role}")
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()
        if role == "Supervisor":
            supervisor_dashboard()
        elif role == "Admin":
            admin_dashboard()
        elif role == "Warden":
            warden_dashboard()
        elif role == "Attendance Desk":
            attendance_desk_dashboard()
        else:
            st.error("Unknown role! Please contact the administrator.")

if __name__ == "__main__":
    main()