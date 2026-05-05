#!/usr/bin/env python
#-----------------------------------------------------------------------
# database.py
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
                    PRIMARY KEY (ta_netid),
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
# Student Functions
#-----------------------------------------------------------------------

def queue_entry(session):
    """ Method that enters a student's information into the 
    database after entering the queue. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Parameter testing
                assert (session is not None)

                # Create variables for session information
                student_netid = session['student_netid']
                student_name = session['student_name']
                course = session['course']
                assignment = session['assignment']
                bug_description = session['bug_description']

                # Paramater testing
                assert(student_netid is not None)
                if (course != 'COS 126' and course != 'COS 226' and course != 'COS 217'):
                    return False
                if(not bug_description or not student_name
                or len(bug_description) > 200 or len(student_name) > 100):
                    return False
                
                # Add student to student table (upsert so a stale row
                # left over from a bad session end doesn't block queue entry)
                cursor.execute('''
                    INSERT INTO student (student_netid, student_name)
                    VALUES (%s, %s)
                    ON CONFLICT (student_netid) DO UPDATE
                    SET student_name = EXCLUDED.student_name
                ''', [student_netid, student_name])

                # Add session to session table (TA will be added later once matched)
                cursor.execute('''
                INSERT INTO session (student_netid, course, assignment, bug_description) 
                VALUES (%s, %s, %s, %s)
                ''', [student_netid, course, assignment, bug_description])
                connection.commit()

        # If student is successfully added to queue...
        return True

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False

def find_student_place(course, student_netid):
    """ Method that finds and returns a student's place in the queue. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 

                # Parameter testing
                assert (student_netid is not None)

                # Find place of student if they are a 126 student
                # (queue consists of only 126 students)
                if course == 'COS 126':
                    statement_str = """SELECT row_num FROM 
                    (
                    SELECT student_netid,
                    ROW_NUMBER() OVER (ORDER BY session.session_id ASC) AS row_num
                    FROM session
                    WHERE course = 'COS 126'
                    AND ta_netid IS NULL
                    ) AS iguessbro
                    WHERE student_netid = %s
                    """
                    cursor.execute(statement_str, (student_netid,))
                    row = cursor.fetchone()
                    
                    return row[0] if row else None
                
                # Otherwise find the place of students who are in the 2XX
                # queue, who could be either COS 217 or 226
                else:
                    statement_str = """SELECT row_num FROM 
                    (
                    SELECT student_netid,
                    ROW_NUMBER() OVER (ORDER BY session.session_id ASC) AS row_num
                    FROM session
                    WHERE (course = 'COS 226' OR course = 'COS 217')
                    AND ta_netid IS NULL
                    ) AS iguessbro
                    WHERE student_netid = %s
                    """
                    cursor.execute(statement_str, (student_netid,))
                    row = cursor.fetchone()
                    
                    return row[0] if row else None

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_num_on_shift_tas(course):
    """ Method that finds and returns the number of TAs that are on shift for a specific course. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 
                if course == 'COS 226' or course == 'COS 217':
                    course = 'COS 2XX'
                
                # Get number of TAs teaching a specific course
                statement_str = """
                SELECT COUNT(*)
                FROM ta, ta_courses
                WHERE ta.ta_netid = ta_courses.ta_netid
                AND ta_courses.course = %s
                AND ta.clocked_in = TRUE
                """
                cursor.execute(statement_str, (course,))
                row = cursor.fetchone()

                if row is None:
                    return None

                num_on_shift_tas = row[0]

                # Return TA's name to display to students
                return num_on_shift_tas

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def notify_next_in_line(course):
    """ Method that checks if the student now at position 1 in the queue for 'course'
    should receive a 'you're next in line' email, and sends it if so.
    Fires as soon as someone is at position 1, regardless of whether a
    TA is on shift. Only skipped if that student was already notified. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT s.student_netid, st.student_name,
                           s.session_id, s.notified_next
                    FROM session s
                    JOIN student st ON s.student_netid = st.student_netid
                    WHERE s.course = %s
                    AND s.ta_netid IS NULL
                    ORDER BY s.session_id ASC
                    LIMIT 1
                """, (course,))
                row = cursor.fetchone()

                if row is None:
                    return None

                student_netid, student_name, session_id, already_notified = row

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE session
                    SET notified_next = TRUE
                    WHERE session_id = %s
                    AND notified_next = FALSE
                    RETURNING session_id
                """, (session_id,))

                updated = cursor.fetchone()
                connection.commit()
                if updated: 
                    notifications.send_next_in_line(student_netid, student_name, course)

    except Exception as ex:
        print(f'notify_next_in_line: {ex}', file=sys.stderr)

def student_already_in_queue(student_netid):
    """ Method that determines if a student is already in the queue or in a session 
    (being helped by a TA). """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Parameter testing
                assert (student_netid is not None)

                statement_str = """SELECT ta_netid
                FROM session
                WHERE student_netid = %s 
                """
                cursor.execute(statement_str, (student_netid,))
                row = cursor.fetchone()
                # Student is neither in queue or in a session
                if row is None: 
                    return "DoesNotExist"
                db_ta_netid = row[0]
                # Student is in queue
                if(db_ta_netid is None):
                    status = "InQueue"
                # Student is in a session (student is being helped)
                if(db_ta_netid is not None):
                    status = "InSession"
                return status
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_session_info_student(student_netid):
    """ Method that checks for a student's session information and
    returns relevant info. """
    
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Parameter testing
                assert (student_netid is not None)

                # Select session information for student's session
                cursor.execute("""
                    SELECT course, bug_description, session_id
                    FROM session
                    WHERE session.student_netid = %s
                    ORDER BY session_id DESC
                """, (student_netid,))
                table = cursor.fetchall()

                # If session does not exist...
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
                
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:

                # Parameter testing
                assert (student_netid is not None)

                # Select TA's name
                cursor.execute("""
                    SELECT ta_name
                    FROM ta, session
                    WHERE session.student_netid = %s
                    AND ta.ta_netid = session.ta_netid
                    ORDER BY session_id DESC
                """, (student_netid,))
                row = cursor.fetchone()

                # If session does not exist...
                if not row:
                    return None

                # Otherwise, return TA name
                ta_name = row[0]

                return ta_name
    
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

#-----------------------------------------------------------------------
# TA Functions
#-----------------------------------------------------------------------

def match(ta_netid):
    """ Method that matches a TA to a student by finding their netID,
    changing their availability, and adding their information to the
    session table. Handles overflow. Returns their netID. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:

                # Parameter testing
                assert (ta_netid is not None)

                # Ensure TA is not currently helping another student 
                statement_str = """SELECT 1 FROM session 
                WHERE ta_netid = %s
                LIMIT 1"""
                cursor.execute(statement_str, (ta_netid,))
                row = cursor.fetchone()

                if row is not None:
                    return None
                    
                # Find TA's course
                cursor.execute("""
                    SELECT course
                    FROM ta_courses
                    WHERE ta_netid = %s
                """, (ta_netid,))
                
                row = cursor.fetchone()

                if row is None:
                    return None

                ta_course = row[0]
                
                # Check if overflow handling is necessary
                # (if there are no 200 level students in the queue,
                # 200 level TAs can help with 100 level classes)
                overflow = detect_overflow()

                # If TA is a 2xx level TA...
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

                # If TA is a 126 TA, only match with 126 student
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
                
                # Add TA's netID to session table
                statement_str = """UPDATE session 
                SET ta_netid = %s
                WHERE student_netid = %s"""
                cursor.execute(statement_str, (ta_netid, student_netid))
                connection.commit()

                # Add session start time and mark notified_matched
                statement_str = """UPDATE session 
                SET time_session_began = CURRENT_TIMESTAMP,
                    notified_matched = TRUE
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                connection.commit()

                # Gather info needed for email notification and return session ID
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

        # Send matched email outside the connection block
        notifications.send_matched(student_netid, student_name, ta_name, course)

        # Queue just shifted, so notify student that is now 1st in line
        notify_next_in_line(course)

        return session_id
                
    except Exception as ex:
        print(f'match: {ex}', file=sys.stderr)
        return None

def detect_overflow():
    """ Method that detects if there are no 2xx level students in the queue.
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

                # If there are no 2xx level students in the queue, return true
                return num_200_students == 0

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)


def get_session_info_ta(ta_netid):
    """ Method that checks for a TA's session information. If they are
    matched to a session, returns relevant info. If they are not matched,
    return None. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:

                # Parameter testing
                assert (ta_netid is not None)

                # Get session information for TA's session
                cursor.execute("""
                    SELECT student_name, session.student_netid, course, assignment,
                    bug_description, session_id
                    FROM session, student
                    WHERE ta_netid = %s
                    AND session.student_netid = student.student_netid
                    ORDER BY session_id DESC
                """, (ta_netid,))
                table = cursor.fetchall()

                # If the query returned no rows, then TA was not matched with a student
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

                # Parameter testing
                assert (ta_netid is not None)

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
    ended and triggers a notification check for the next student
    in that course's queue. """

    try:
        course = None
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Parameter testing
                assert (student_netid is not None)
                
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
                numRowsDeleted = cursor.rowcount

                statement_str = """DELETE FROM student
                WHERE student_netid = %s
                """
                cursor.execute(statement_str, (student_netid,))
                numRowsDeleted += cursor.rowcount
                connection.commit()

        # if course is not None:
            notify_next_in_line(course)

        # If session is successfully removed...
            return numRowsDeleted > 0
                
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False

def clock_in(ta_netid):
    """ Method that collects the date and netID of a TA after 
    they clock in. """

    try:
        courses = []
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Parameter testing
                assert (ta_netid is not None)

                # Set TA to clocked in
                statement_str = """UPDATE ta
                SET clocked_in = TRUE
                WHERE ta_netid = %s
                AND clocked_in = FALSE"""
                cursor.execute(statement_str, (ta_netid,))

                # If TA is not successfully marked as clocked in...
                if cursor.rowcount == 0:
                    return False

                # Add shift to database
                cursor.execute("""
                    INSERT INTO shifts (ta_netid, clock_in, clock_out, students_helped)
                    VALUES (%s, %s, NULL, 0)
                """, (ta_netid, datetime.now()))
                connection.commit()

                # Grab the courses TA covers so we know which queues
                # might now have a newly-notifiable front-of-line student
                cursor.execute(
                    "SELECT course FROM ta_courses WHERE ta_netid = %s",
                    (ta_netid,)
                )
                courses = [r[0] for r in cursor.fetchall()]

        # for course in courses:
            notify_next_in_line(course)

        # If TA is successfully clocked in...
            return True

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False

def clock_out(ta_netid):
    """ Method that clocks the TA out and saves their shift information into the Google Sheet. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
               
                # Parameter testing
                assert (ta_netid is not None)

                # Set TA to clocked out
                statement_str = """UPDATE ta 
                SET clocked_in = FALSE
                WHERE ta_netid = %s
                AND clocked_in = TRUE"""
                cursor.execute(statement_str, (ta_netid,))
                
                # If TA is not successfully marked as clocked out...
                if cursor.rowcount == 0:
                    return False

                # Note time shift ends
                statement_str = """UPDATE shifts
                SET clock_out = %s
                WHERE ta_netid = %s
                AND clock_out IS NULL"""
                cursor.execute(statement_str, (datetime.now(), ta_netid))
                connection.commit()

                # Get TA's name 
                statement_str = """SELECT ta_name
                FROM ta
                WHERE ta_netid = %s"""
                cursor.execute(statement_str, (ta_netid,))
                row = cursor.fetchone()

                if row is not None: 
                    ta_name = row[0]
                else:
                    ta_name = "N/A"

                # Get shift information (of most recent shift) from database
                statement_str = """SELECT clock_in, clock_out, students_helped
                FROM shifts
                WHERE ta_netid = %s
                ORDER BY clock_out DESC
                LIMIT 1"""
                cursor.execute(statement_str, (ta_netid,))
                row = cursor.fetchone()

                # Save shift information into the Google Sheet
                logSuccessful = False
                if row is not None:
                    clock_in, clock_out, num_students_helped = row
                    # Check if clock_out time is NULL before inserting
                    if clock_out:
                        clock_out_str = clock_out.strftime("%H:%M")
                    else: 
                        clock_out_str = "N/A"

                    logSuccessful = googlesheet.log_shift(ta_netid, 
                    ta_name, 
                    clock_in.strftime("%m-%d-%Y"), 
                    clock_in.strftime("%H:%M"), 
                    clock_out_str, 
                    str(num_students_helped))

                # If shift is successfully added to sheet, delete shift from database
                if logSuccessful: 
                    cursor.execute("""
                        DELETE FROM shifts WHERE ta_netid = %s
                    """, (ta_netid,))
                    connection.commit()

                # If TA is successfully clocked out... 
                return logSuccessful

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False

def check_if_clocked_in(ta_netid):
    """ Method that checks if a TA is clocked in."""

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                
                # Parameter testing
                assert (ta_netid is not None)

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
                
                # Parameter testing
                assert (ta_netid is not None)

                # Add 1 to the number of students helped (in database)
                statement_str = """UPDATE shifts 
                SET students_helped = students_helped + 1
                WHERE ta_netid = %s
                AND clock_out IS NULL"""
                cursor.execute(statement_str, (ta_netid,))
                connection.commit()

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
                
def validate_ta(ta_netid):
    """ Method that validates if a user with ta_netid is truly a TA."""

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                
                # Parameter testing
                assert (ta_netid is not None)

                cursor.execute("""
                    SELECT ta_netid
                    FROM ta
                    WHERE ta_netid = %s
                """, (ta_netid,))
                row = cursor.fetchone()
                return row is not None

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def get_time_session_began(session_id):
    """Method that returns the time the session began."""

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:

                # Parameter testing
                assert (session_id is not None)
                
                cursor.execute("""
                    SELECT time_session_began
                    FROM session
                    WHERE session_id = %s
                """, (session_id,))
                row = cursor.fetchone()

                # In the case that session does not exist
                if row is None:
                    return None

                # Otherwise, return time session began
                time_session_began = row[0]

                return time_session_began

    except Exception as ex:
        print(f'get_queue_students: {ex}', file=sys.stderr)
        return []

def get_queue_students():
    """Method that returns all students currently waiting in queue."""

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
                table = cursor.fetchall()

                result = []
                i = 1
                for r in table:
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
    """Method that returns all active sessions."""

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
                table = cursor.fetchall()

                result = []
                for r in table:
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
# Admin Functions
#-----------------------------------------------------------------------

def add_ta(ta_netid, ta_name, ta_email, course):
   """ Method that adds a TA to the database. """

   try: 
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Paramater testing
                if (course != 'COS 126' and course != 'COS 2XX'):
                    return False
                if(not ta_netid or not ta_name or not ta_email or
                len(ta_netid) > 8 or len(ta_name) > 100 or len(ta_email) > 254):
                    return False
                
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
                
                # If TA is successfully added... 
                return True

   except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False

def remove_ta(ta_netid):
    """ Method that removes a TA from the database. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    DELETE FROM session WHERE ta_netid = %s
                """, (ta_netid,))
                numRowsDeleted = cursor.rowcount
                cursor.execute("""
                    DELETE FROM shifts WHERE ta_netid = %s
                """, (ta_netid,))
                numRowsDeleted += cursor.rowcount
                cursor.execute("""
                    DELETE FROM ta_courses WHERE ta_netid = %s
                """, (ta_netid,))
                numRowsDeleted += cursor.rowcount
                cursor.execute("""
                    DELETE FROM ta WHERE ta_netid = %s
                """, (ta_netid,))
                numRowsDeleted += cursor.rowcount
                connection.commit()
                
                # If TA is successfully removed...
                return numRowsDeleted > 0

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False

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
                    ORDER BY LOWER(TRIM(ta.ta_name)) ASC, ta.ta_name ASC
                """)
                table = cursor.fetchall()
                tas = []
                for r in table:
                    tas.append({
                        'ta_netid': r[0],
                        'ta_name': r[1],
                        'ta_email': r[2],
                        'available': r[3],
                        'courses': r[4] or ''
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

                # Parameter testing
                assert (admin_netid is not None)

                cursor.execute("""
                    SELECT admin_netid FROM admin
                    WHERE admin_netid = %s
                """, (admin_netid,))
                return cursor.fetchone() is not None

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        return False
        
def edit_ta(ta_netid, ta_name, ta_email, courses):
    """ Method that edits a TA in the database. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:

                # Parameter testing
                if(not ta_netid or not ta_name or not ta_email or
                len(ta_netid) > 8 or len(ta_name) > 100 or len(ta_email) > 254):
                    return False

                cursor.execute("""
                    UPDATE ta
                    SET ta_name = %s,
                        ta_email = %s
                    WHERE ta_netid = %s
                """, (ta_name, ta_email, ta_netid))

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