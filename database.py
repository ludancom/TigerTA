#!/usr/bin/env python
#-----------------------------------------------------------------------
#database.py
#-----------------------------------------------------------------------

import os
import sys
import notifications
import psycopg
import dotenv
import contextlib
import time
from datetime import datetime
import random
import googlesheet

dotenv.load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

#----------------------------------------------------------------------

def main():
    """ Method that creates the tables for the database. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                #-------------------------------------------------------

                cursor.execute('DROP TABLE IF EXISTS ta_courses')
                cursor.execute('DROP TABLE IF EXISTS session')
                cursor.execute('DROP TABLE IF EXISTS shifts')
                cursor.execute('DROP TABLE IF EXISTS admin')
                cursor.execute('DROP TABLE IF EXISTS ta')
                cursor.execute('DROP TABLE IF EXISTS student')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ta (
                    ta_netid TEXT NOT NULL,
                    ta_name TEXT NOT NULL,
                    ta_email TEXT NOT NULL,
                    available BOOLEAN NOT NULL,
                    clocked_in BOOLEAN NOT NULL,
                    PRIMARY KEY (ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS student (
                    student_netid TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    PRIMARY KEY (student_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ta_courses (
                    ta_netid TEXT NOT NULL,
                    course TEXT NOT NULL,
                    PRIMARY KEY (ta_netid, course),
                    FOREIGN KEY (ta_netid) REFERENCES ta(ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session (
                    session_id BIGSERIAL NOT NULL,
                    student_netid TEXT NOT NULL,
                    ta_netid TEXT,
                    course TEXT NOT NULL,
                    assignment TEXT NOT NULL,
                    bug_description TEXT NOT NULL,
                    time_joined TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    time_session_began TIMESTAMP,
                    notified_next BOOLEAN NOT NULL DEFAULT FALSE,
                    notified_matched BOOLEAN NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (session_id),
                    UNIQUE (student_netid),
                    FOREIGN KEY (student_netid) REFERENCES student(student_netid),
                    FOREIGN KEY (ta_netid) REFERENCES ta(ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                    shift_id BIGSERIAL NOT NULL,
                    ta_netid TEXT NOT NULL,
                    clock_in TIMESTAMP NOT NULL,
                    clock_out TIMESTAMP,
                    students_helped INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (shift_id),
                    FOREIGN KEY (ta_netid) REFERENCES ta(ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin (
                    admin_netid TEXT NOT NULL,
                    PRIMARY KEY (admin_netid)
                    )
                ''')

                connection.commit()
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

#-----------------------------------------------------------------------
# Student functions
#-----------------------------------------------------------------------

def queue_entry(session):
    """ Method that enters a student's information into the 
    database after entering the queue. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                #-------------------------------------------------------
                # Create variables for session information
                student_netid = session['student_netid']
                student_name = session['student_name']
                course = session['course']
                assignment = session['assignment']
                bug_description = session['bug_description']

                # Add this student to student table
                cursor.execute('''
                    INSERT INTO student (student_netid, student_name)
                    VALUES (%s, %s)
                ''', [student_netid, student_name])

                # Add this session to session table (TA will be added later once matched)
                # Add TA back
                cursor.execute('''
                INSERT INTO session (student_netid, course, assignment, bug_description) 
                VALUES (%s, %s, %s, %s)
                ''', [student_netid, course, assignment, bug_description])
                connection.commit()

    except Exception as ex:
        print("ERROR:", ex)


def find_student_place(course, student_netid):
    """ Method that finds and returns a student's place in the queue. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 
                
                #Find place of student
                statement_str = """SELECT row_num FROM 
                (
                SELECT student_netid,
                ROW_NUMBER() OVER (ORDER BY session.session_id ASC) AS row_num
                FROM session
                WHERE course = %s
                AND ta_netid IS NULL
                ) AS iguessbro
                WHERE student_netid = %s
                """
                cursor.execute(statement_str, (course, student_netid))
                table = cursor.fetchone()
                
                return table[0] if table else None
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_num_on_shift_tas(course):
    """ Method that finds and returns the number of TAs that are on shift for a specific course. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 
                # Get the number of TAs teaching a specific course
                statement_str = """
                SELECT COUNT(*)
                FROM ta, ta_courses
                WHERE ta.ta_netid = ta_courses.ta_netid
                AND ta_courses.course = %s
                AND ta.clocked_in = TRUE
                """
                # AND ta.clockin_expire IS NOT NULL
                # AND ta.clockin_expire > NOW()
                cursor.execute(statement_str, (course,))
                row = cursor.fetchone()
                num_on_shift_tas = row[0]

                # Return TA name to display to users
                return num_on_shift_tas
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def notify_next_in_line(course):
    """ Check if the student now at position 1 in the queue for `course` 
    should receive a 'you're next in line' email, and send it if so. 
    Only sends if a TA is on shift for the course and the student
    hasn't already been notified. """
    try:
        # First check: is there a TA on shift for this course?
        if get_num_on_shift_tas(course) == 0:
            return

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT s.student_netid, st.student_name, s.session_id
                    FROM session s
                    JOIN student st ON s.student_netid = st.student_netid
                    WHERE s.course = %s
                    AND s.ta_netid IS NULL
                    AND s.notified_next = FALSE
                    ORDER BY s.session_id ASC
                    LIMIT 1
                """, (course,))
                row = cursor.fetchone()
                if row is None:
                    return
                student_netid, student_name, session_id = row

                # Mark notified BEFORE sending email, prevents double-send
                cursor.execute("""
                    UPDATE session
                    SET notified_next = TRUE
                    WHERE session_id = %s
                """, (session_id,))
                connection.commit()

        notifications.send_next_in_line(student_netid, student_name, course)

    except Exception as ex:
        print(f'notify_next_in_line: {ex}', file=sys.stderr)

# Ensure that the student is not rejoining the queue
def student_already_in_queue(student_netid):
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                statement_str = """SELECT ta_netid
                FROM session
                WHERE student_netid = %s 
                """
                cursor.execute(statement_str, (student_netid,))
                row = cursor.fetchone()
                if row is None: 
                    return "DoesNotExist"
                db_ta_netid = row[0]
                # Student is in queue
                if(db_ta_netid is None):
                    status = "InQueue"
                # Student is being helped
                if(db_ta_netid is not None):
                    status = "InSession"
                return status
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_session_info_student(student_netid):
    """ Method that checks for a student's session information and
    returns relevant info. """

    # Select session information for the student's session
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT course, bug_description, session_id
                    FROM session
                    WHERE session.student_netid = %s
                    ORDER BY session_id DESC
                """, (student_netid,))
                table = cursor.fetchall()

                # In case the session does not exist
                if not table:
                    return None
                
                # Otherwise, return session information
                session_info = {
                    'course': table[0][0],
                    'bug_description': table[0][1],
                    'session_id': table[0][2]
                }

                return session_info
    
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_session_ta_name(student_netid):
    """ Method that checks for a student's session and gets
    their already matched TA. """

    # Select TA name
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT ta_name
                    FROM ta, session
                    WHERE session.student_netid = %s
                    AND ta.ta_netid = session.ta_netid
                    ORDER BY session_id DESC
                """, (student_netid,))
                table = cursor.fetchall()

                # In case the session does not exist
                if not table:
                    return None

                # Otherwise, return TA name
                ta_name = table[0][0]

                return ta_name
    
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

#-----------------------------------------------------------------------
# TA functions
#-----------------------------------------------------------------------

def match(ta_netid):
    """ Method that matches a TA to a student by finding their netid,
    changing their availability, and adding their information to the
    session table. Handles overflow. Returns their net id. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Find the ta course
                cursor.execute("""
                    SELECT course
                    FROM ta_courses
                    WHERE ta_netid = %s
                """, (ta_netid,))
                ta_course = cursor.fetchone()[0]
                

                # Check if overflow handling is necessary
                # AKA if there are no 200 level students in the queue,
                # 200 level TAs can help with 100 level classes
                overflow = detect_overflow()


                # If the TA is a 2xx level TA:
                if ta_course == 'COS 2XX':

                    # If there is overflow, 2xx level TAs can match to
                    # any student
                    if overflow:
                        statement_str = """SELECT student_netid
                        FROM session
                        WHERE ta_netid IS NULL 
                        ORDER BY session_id ASC
                        LIMIT 1
                        """
                        cursor.execute(statement_str)
                        row = cursor.fetchone()
                        if row is None:
                            return None

                        student_netid = row[0]

                    # Otherwise, if there is no overflow, 2xx level TAs
                    # can only match to 2xx students
                    else:
                        statement_str = """SELECT student_netid
                        FROM session
                        WHERE ta_netid IS NULL 
                        AND (course = 'COS 226' OR course = 'COS 217')
                        ORDER BY session_id ASC
                        LIMIT 1"""
                        cursor.execute(statement_str)
                        row = cursor.fetchone()
                        if row is None:
                            return None

                        student_netid = row[0]

                # If the TA is 126 TA, match with 126 student
                else:               
                    statement_str = """SELECT student_netid
                    FROM session
                    WHERE ta_netid IS NULL 
                    AND course = 'COS 126'
                    ORDER BY session_id ASC
                    LIMIT 1"""
                    cursor.execute(statement_str)
                    row = cursor.fetchone()
                    if row is None:
                        return None

                    student_netid = row[0]
                

                # Set TA to unavailable
                statement_str = """UPDATE ta 
                SET available = FALSE
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                
                # Add TA's netid to session table
                statement_str = """UPDATE session 
                SET ta_netid = %s
                WHERE student_netid = %s"""
                cursor.execute(statement_str, (ta_netid, student_netid))
                connection.commit()

                # add the session start time + mark notified_matched
                statement_str = """UPDATE session 
                SET time_session_began = CURRENT_TIMESTAMP,
                    notified_matched = TRUE
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                connection.commit()

                # gather info needed for the email + return session id
                cursor.execute("""
                    SELECT s.session_id, st.student_name, t.ta_name, s.course
                    FROM session s
                    JOIN student st ON s.student_netid = st.student_netid
                    JOIN ta t ON s.ta_netid = t.ta_netid
                    WHERE s.student_netid = %s
                    AND s.ta_netid = %s
                    LIMIT 1
                """, (student_netid, ta_netid))
                row = cursor.fetchone()
                if row is None:
                    return None
                session_id, student_name, ta_name, course = row

        # send the matched email outside the connection block
        notifications.send_matched(student_netid, student_name, ta_name, course)

        # the queue just shifted, so let the new front student know
        notify_next_in_line(course)

        return session_id
                

    except Exception as ex:
        print(f'match: {ex}', file=sys.stderr)
        return None

def detect_overflow():
    """ Method that detects if there are no 200 level students in the queue.
    If there are none, return true. Otherwise, return false. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                
                # Extract the queue entries
                statement_str = """SELECT course
                FROM session
                WHERE ta_netid IS NULL"""
                cursor.execute(statement_str)
                table = cursor.fetchall()
                num_200_students = sum([i.count('COS 226') for i in table]) + sum([i.count('COS 217') for i in table])

                # If there are no 200 level students in the queue, return true
                if num_200_students == 0:
                    return True
                
                else:
                    return False

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)


def get_session_info_ta(ta_netid):
    """ Method that checks for a TA's session information. If they are
    matched to a session, returns relevant info. If they are not matched,
    return None. """
    # Select session information for the TA's session
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT student_name, session.student_netid, course, assignment,
                    bug_description, session_id
                    FROM session, student
                    WHERE ta_netid = %s
                    AND session.student_netid = student.student_netid
                    ORDER BY session_id DESC
                """, (ta_netid,))
                table = cursor.fetchall()

                # If the table doesn't exist, then the TA is not matched
                if not table:
                    return None

                # Otherwise, return session information
                session_info = {
                    'student_name': table[0][0],
                    'student_netid': table[0][1],
                    'course': table[0][2],
                    'assignment': table[0][3],
                    'bug_description': table[0][4],
                    'session_id': table[0][5]
                }

                return session_info
    
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def set_available(ta_netid):
    """ Method that updates a TA's availability to true. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:

                # Set TA to available
                statement_str = """UPDATE ta 
                SET available = TRUE
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))

                connection.commit()

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def remove_session(student_netid):
    """ Method that removes a session from the session list after it has
    ended. Also triggers a notification check for the next student
    in that course's queue. """
    try:
        course = None
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT course FROM session WHERE student_netid = %s
                """, (student_netid,))
                row = cursor.fetchone()
                if row is not None:
                    course = row[0]

                statement_str = """DELETE FROM session
                WHERE student_netid = %s
                """
                cursor.execute(statement_str, (student_netid,))

                statement_str = """DELETE FROM student
                WHERE student_netid = %s
                """
                cursor.execute(statement_str, (student_netid,))
                connection.commit()

        if course is not None:
            notify_next_in_line(course)
                
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def clock_in(ta_netid):
    """ Method that collects the date and netid of the ta after 
    they clock in. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Set TA to clocked in
                statement_str = """UPDATE ta
                SET clocked_in = TRUE
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))

                # INSERT INTO ta (ta_netid, ta_name, available, clockin, clockin_expire)
                # VALUES (%s, %s, TRUE, TRUE, NULL)
                # ON CONFLICT (ta_netid)
                # DO UPDATE SET
                    #clockin = TRUE

                # Adds their shift to table in database
                cursor.execute("""
                    INSERT INTO shifts (ta_netid, clock_in, clock_out, students_helped)
                    VALUES (%s, %s, NULL, 0)
                """, (ta_netid, datetime.now()))
                connection.commit()
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def clock_out(ta_netid):
    """ Method that clocks the TA out and saves their shift information into the Google Sheet. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Set TA to clocked out
                statement_str = """UPDATE ta 
                SET clocked_in = FALSE
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))

                # Note time shift ends
                statement_str = """UPDATE shifts
                SET clock_out = %s
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (datetime.now(), ta_netid))
                connection.commit()

                # Get TA's name 
                statement_str = """SELECT ta_name
                FROM ta
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                row = cursor.fetchone()
                ta_name = row[0]

                # Get shift information from database
                statement_str = """SELECT clock_in, clock_out, students_helped
                FROM shifts
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                row = cursor.fetchone()

                # Save shift information into the Google Sheet
                if row is not None:
                    googlesheet.log_shift(ta_netid, ta_name, row[0].strftime("%m-%d-%Y"), row[0].strftime("%H:%M"), row[1].strftime("%H:%M"), str(row[2]))

                # If shift is successfully added to sheet, delete shift from database (maybe check later first if was successfully added to sheet before deleting)
                cursor.execute("""
                    DELETE FROM shifts WHERE ta_netid = %s
                """, (ta_netid,))
                connection.commit()

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def check_if_clocked_in(ta_netid):
    """ Method that updates the number of students a TA helped during their shift."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT clocked_in
                    FROM ta
                    WHERE ta_netid = %s
                """, (ta_netid,))
                row = cursor.fetchone()
                return row[0] if row else None

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def update_num_students_helped(ta_netid):
    """ Method that updates the number of students a TA helped during their shift."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Add 1 to the number of students helped
                statement_str = """UPDATE shifts 
                SET students_helped = students_helped + 1
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                connection.commit()

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
                
def validate_ta(netid):
    """ Method that validates if a user with ta_netid is truly a TA."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT ta_netid
                    FROM ta
                    WHERE ta_netid = %s
                """, (netid,))
                row = cursor.fetchone()
                return row is not None
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def set_clockin_expire(ta_netid, expires_epoch):
    """ Method that sets the time that clock in expires for the TA. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE ta
                    SET clockin = TRUE,
                        clockin_expire = TO_TIMESTAMP(%s)
                    WHERE ta_netid = %s
                """, (int(expires_epoch), ta_netid))
                connection.commit()
    except Exception as ex:
        print(f'set_clockin_expire: {ex}', file=sys.stderr)

def get_clockin_expire(ta_netid):
    """ Method that gets the updated remaining time for the TAs shift. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT EXTRACT(EPOCH FROM clockin_expire)::BIGINT
                    FROM ta
                    WHERE ta_netid = %s
                """, (ta_netid,))
                row = cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
    except Exception as ex:
        print(f'get_clockin_expire: {ex}', file=sys.stderr)
        return 0
    
def refresh_clockin_status(ta_netid):
    """Mark a TA as no longer clocked in if their shift expired."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE ta
                    SET clockin = FALSE,
                        available = FALSE
                    WHERE ta_netid = %s
                      AND clockin_expire IS NOT NULL
                      AND clockin_expire <= NOW()
                """, (ta_netid,))
                connection.commit()
    except Exception as ex:
        print(f'refresh_clockin_status: {ex}', file=sys.stderr)

def get_time_session_began(session_id):
    """Return the time the session began."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT time_session_began
                    FROM session
                    WHERE session_id = %s
                """, (session_id,))
                table = cursor.fetchall()

                # In case the session does not exist
                if not table:
                    return None

                # Otherwise, return the time the session began
                time_session_began = table[0][0]

                return time_session_began

    except Exception as ex:
        print(f'get_queue_students: {ex}', file=sys.stderr)
        return []

def get_queue_students():
    """Return all students currently waiting in queue."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT s.session_id, s.student_netid, st.student_name,
                           s.course, s.assignment, s.bug_description
                    FROM session s
                    LEFT JOIN student st ON s.student_netid = st.student_netid
                    WHERE s.ta_netid IS NULL
                    ORDER BY s.session_id ASC
                """)
                rows = cursor.fetchall()

                result = []
                i = 1
                for r in rows:
                    result.append({
                        'session_id': r[0],
                        'student_netid': r[1],
                        'student_name': r[2],
                        'course': r[3],
                        'assignment': r[4],
                        'bug_description': r[5],
                        'queue_number': i
                    })
                    i += 1
                return result

    except Exception as ex:
        print(f'get_queue_students: {ex}', file=sys.stderr)
        return []
    
def get_active_sessions():
    """Return all active sessions."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT s.session_id, s.student_netid, s.ta_netid,
                           st.student_name, s.course, s.assignment, s.bug_description
                    FROM session s
                    LEFT JOIN student st ON s.student_netid = st.student_netid
                    WHERE s.ta_netid IS NOT NULL
                    ORDER BY s.session_id ASC
                """)
                rows = cursor.fetchall()

                result = []
                for r in rows:
                    result.append({
                        'session_id': r[0],
                        'student_netid': r[1],
                        'ta_netid': r[2],
                        'student_name': r[3],
                        'course': r[4],
                        'assignment': r[5],
                        'bug_description': r[6]
                    })
                return result

    except Exception as ex:
        print(f'get_active_sessions: {ex}', file=sys.stderr)
        return []
    
#-----------------------------------------------------------------------
# Admin functions
#-----------------------------------------------------------------------

def add_ta(ta_netid, ta_name, ta_email, course):
   """ Method that adds a TA to the database. """ 
   try: 
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    INSERT INTO ta (ta_netid, ta_name, ta_email, available, clocked_in)
                    VALUES (%s, %s, %s, FALSE, FALSE)
                    ON CONFLICT (ta_netid)
                    DO UPDATE SET
                        ta_name = EXCLUDED.ta_name,
                        ta_email = EXCLUDED.ta_email
                """, (ta_netid, ta_name, ta_email))

                cursor.execute("""
                    INSERT INTO ta_courses (ta_netid, course)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (ta_netid, course))
                connection.commit()
   except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def remove_ta(ta_netid):
    """ Method that removes a TA from the database. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    DELETE FROM ta_courses WHERE ta_netid = %s
                """, (ta_netid,))
                cursor.execute("""
                    DELETE FROM ta WHERE ta_netid = %s
                """, (ta_netid,))
                connection.commit()
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_all_tas():
    """ Method that returns all TAs in the database. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT ta.ta_netid,
                           ta.ta_name,
                           ta.ta_email,
                           ta.available,
                           STRING_AGG(ta_courses.course, ', ' ORDER BY ta_courses.course) AS courses
                    FROM ta
                    LEFT JOIN ta_courses ON ta.ta_netid = ta_courses.ta_netid
                    GROUP BY ta.ta_netid, ta.ta_name, ta.ta_email, ta.available
                    ORDER BY ta.ta_name ASC
                """)
                rows = cursor.fetchall()
                tas = []
                for row in rows:
                    tas.append({
                        'ta_netid': row[0],
                        'ta_name': row[1],
                        'ta_email': row[2],
                        'available': row[3],
                        'courses': row[4] or ''
                    })
                return tas
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return []

def validate_admin(admin_netid):
    """ Method that validates if a user is truly an admin. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT admin_netid FROM admin
                    WHERE admin_netid = %s
                """, (admin_netid,))
                return cursor.fetchone() is not None
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False
        

def edit_ta(ta_netid, name, email, courses):
    """ Method that edits a TA in the database. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE ta
                    SET ta_name = %s,
                        ta_email = %s
                    WHERE ta_netid = %s
                """, (name, email, ta_netid))

                cursor.execute("""
                    DELETE FROM ta_courses
                    WHERE ta_netid = %s
                """, (ta_netid,))

                for course in [c.strip() for c in courses.split(',') if c.strip()]:
                    cursor.execute("""
                        INSERT INTO ta_courses (ta_netid, course)
                        VALUES (%s, %s)
                    """, (ta_netid, course))

                connection.commit()
    except Exception as ex:
        print(f'edit_ta: {ex}', file=sys.stderr)
    
if __name__ == '__main__':
    main()