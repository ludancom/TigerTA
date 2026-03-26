 #!/usr/bin/env python
 #-----------------------------------------------------------------------
 #database.py
 #-----------------------------------------------------------------------

 import os
 import sys
 import psycopg
 import dotenv

 dotenv.load_dotenv()
 DATABASE_URL = os.environ['DATABASE_URL']

 #----------------------------------------------------------------------

 def main():
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.curser() as cursor:
                #-------------------------------------------------------

                cursor.execute('''
                    CREATE TABLE ta (
                    net_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    available BOOLEAN NOT NULL,
                    available list NOT NULL,
                    PRIMARY KEY (net_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE student (
                    net_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    PRIMARY KEY (net_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE ta_course (
                    net_id TEXT NOT NULL,
                    course_code INTEGER
                    PRIMARY KEY (net_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE assignment (
                    assignment_id INTEGER NOT NULL,
                    course_code INTEGER NOT NULL,
                    name text
                    PRIMARY KEY (assignment_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE session (
                    session_id INTEGER NOT NULL,
                    student TEXT NOT NULL,
                    ta TEXT NOT NULL,
                    assignment TEXT,
                    bug_description TEXT,
                    PRIMARY KEY (net_id)
                    )
                ''')


def queue_entry(session):
    """ Method that enters a student's information into the 
    database after entering the queue. """

    # Create variables for session information
    student_netid = session['student_netid']
    student_name = session['student_name']
    course = session['course']
    assignment = session['assignment']
    bug_description = session['bug_description']

    # Add student to student table
    cursor.execute('''
        INSERT INTO student (student_netid, student_name)
        VALUES (?, ?)
    ''', [f'%{student_netid}%', f'%{student_name}%'])

    # Match student with a TA
    ta = find_ta(course)

    # Add session to the session table
    cursor.execute('''
    INSERT INTO session (student_netid, student_name, course, assignment, bug_description, ta)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', [f'%{student_netid}%', f'%{student_name}%', f'%{course}%',
    f'%{assignment}%', f'%{bug_description}%', f'%{ta}'])
                
#remove from session, add to session, add student, select ta(course)
