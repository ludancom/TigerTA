#!/usr/bin/env python
#-----------------------------------------------------------------------
#database.py
#-----------------------------------------------------------------------

import os
import sys
import psycopg
import dotenv
import contextlib
import time
from datetime import datetime
import random

dotenv.load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

#----------------------------------------------------------------------

def main():
    """ Method that creates the tables for the database. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                #-------------------------------------------------------

                cursor.execute('DROP TABLE IF EXISTS ta')
                cursor.execute('DROP TABLE IF EXISTS student')
                cursor.execute('DROP TABLE IF EXISTS ta_courses')
                cursor.execute('DROP TABLE IF EXISTS session')
                cursor.execute('DROP TABLE IF EXISTS shifts')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ta (
                    ta_netid TEXT NOT NULL,
                    ta_name TEXT NOT NULL,
                    available BOOLEAN NOT NULL,
                    clockin_expire TIMESTAMP,
                    PRIMARY KEY (ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS student (
                    student_netid TEXT NOT NULL,
                    student_name TEXT,
                    PRIMARY KEY (student_netid),
                    UNIQUE (student_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ta_courses (
                    ta_netid TEXT NOT NULL,
                    course TEXT NOT NULL,
                    PRIMARY KEY (ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session (
                    session_id BIGSERIAL,
                    student_netid TEXT NOT NULL,
                    ta_netid TEXT,
                    course TEXT NOT NULL,
                    assignment TEXT,
                    bug_description TEXT,
                    time_joined TEXT,
                    PRIMARY KEY (session_id),
                    UNIQUE (student_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                    shift_id BIGSERIAL,
                    ta_netid TEXT,
                    date TIMESTAMP NOT NULL,
                    PRIMARY KEY (shift_id)
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
                ) AS iguessbro
                WHERE student_netid = %s
                """
                cursor.execute(statement_str, (course, student_netid))
                table = cursor.fetchone()
                
                return table[0]


    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)


def find_ta_name(course, student_netid):
    """ Method that finds and returns the name of a student's matched TA. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 
                # Match student with a TA
                ta_netid = match(course, student_netid)

                # Get TA name
                statement_str = """SELECT ta_name 
                FROM ta
                WHERE ta_netid = %s 
                """
                cursor.execute(statement_str, (ta_netid,))
                table = cursor.fetchall()
                ta_name = table[0][0]

                # Return TA name to display to users
                return ta_name

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)


def match(course, student_netid):
    """ Method that matches a TA to a student by finding their netid,
    changing their availability, and adding their information to the
    session table. Returns their net id. """

    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Get TA netid
                statement_str = """SELECT ta.ta_netid
                FROM ta, ta_courses
                WHERE ta_courses.course = %s
                AND ta_courses.ta_netid = ta.ta_netid
                AND ta.available = TRUE"""
                cursor.execute(statement_str, (course,))
                table = cursor.fetchall()
                ta_netid = table[0][0]

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
                return ta_netid

    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

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

#-----------------------------------------------------------------------
# TA functions
#-----------------------------------------------------------------------

def get_session_info(ta_netid):
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

def remove_session(session_id, student_netid):
    """ Method that reomves a session from the session list after it has
    ended. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 
                statement_str = """DELETE FROM session
                WHERE session_id = %s
                """
                cursor.execute(statement_str, (session_id,))

                statement_str = """DELETE FROM student
                WHERE student_netid = %s
                """
                cursor.execute(statement_str, (student_netid,))
                connection.commit()
                
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def clock_in(ta_netid):
    """ Method that collects the date and netid of the ta after 
    they clock in. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                #make sure that the TA exists already
                cursor.execute("""
                    INSERT INTO ta (ta_netid, ta_name, available)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (ta_netid) DO NOTHING
                """, (ta_netid, ta_netid))
                
                # Create a new shift entry
                cursor.execute('''
                    INSERT INTO shifts (ta_netid, date)
                    VALUES (%s, %s)
                ''', (ta_netid, datetime.now()))
                connection.commit()
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
                
def validate_ta(netid):
    """ Method that validates if a user with ta_netid is truly a TA."""
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Get Student name
                statement_str = """SELECT ta_netid 
                FROM ta
                WHERE ta_netid = %s 
                """
                cursor.execute(statement_str, (netid,))
                table = cursor.fetchone()
                ta_netid = table[0]
                # if there is no 
                if ta_netid == None:
                    return False
                return True
                
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

def set_clockin_expire(ta_netid, expires_epoch):
    """ Method that sets the time that clock in expires for the TA. """
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE ta
                    SET clockin_expire = TO_TIMESTAMP(%s)
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
            

if __name__ == '__main__':
    main()