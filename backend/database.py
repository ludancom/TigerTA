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
import random

dotenv.load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

#----------------------------------------------------------------------

def main():
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                #-------------------------------------------------------

                cursor.execute('DROP TABLE IF EXISTS ta')
                cursor.execute('DROP TABLE IF EXISTS student')
                cursor.execute('DROP TABLE IF EXISTS ta_courses')
                cursor.execute('DROP TABLE IF EXISTS session')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ta (
                    ta_netid TEXT NOT NULL,
                    ta_name TEXT NOT NULL,
                    available BOOLEAN NOT NULL,
                    PRIMARY KEY (ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS student (
                    student_netid TEXT NOT NULL,
                    student_name TEXT,
                    PRIMARY KEY (student_netid)
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
                    session_id INTEGER NOT NULL,
                    student_netid TEXT NOT NULL,
                    ta_netid TEXT,
                    course TEXT NOT NULL,
                    assignment TEXT,
                    bug_description TEXT,
                    time_joined TEXT,
                    PRIMARY KEY (session_id)
                    )
                ''')

                connection.commit()
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)


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
                session_id = random.randint(1, 9999)

                # Add student to student table
                cursor.execute('''
                    INSERT INTO student (student_netid, student_name)
                    VALUES (%s, %s)
                ''', [student_netid, student_name])

                # Add session to session table (TA will be added later once matched)
                # Add TA back
                cursor.execute('''
                INSERT INTO session (session_id, student_netid, course, assignment, bug_description) 
                VALUES (%s, %s, %s, %s, %s)
                ''', [session_id, student_netid, course, assignment, bug_description])
                connection.commit()

    except Exception as ex:
        print("ERROR:", ex)

# Find student place in queue 
#def find_student_place():
    #try:
        #with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            #with contextlib.closing(connection.cursor()) as cursor: 
                # Find place of student
                # statement_str = """SELECT student_netid
                # FROM student
                #WHERE course = ?
                #ORDER BY time_joined ASC
                #"""
                #cursor.execute(statement_str, (f"%{course}%"))
                #table = cursor.fetchall()
    #except Exception as ex:
        #print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

# Find name of the matched TA 
def find_ta_name(session):
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor: 
                # Match student with a TA
                ta_netid = find_ta_netid(session)

                # Get TA name
                statement_str = """SELECT ta_name 
                FROM ta
                WHERE ta_netid = %s 
                """
                cursor.execute(statement_str, (ta_netid, ))
                table = cursor.fetchall()
                ta_name = table[0][0]

                # Return TA name to display to users
                return ta_name
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)

# Find netid of a TA that is available and teaches course, update TA availability
def find_ta_netid(session):
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                # Get student's course and netid
                course = session['course']
                student_netid = session['student_netid']

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
                
# Remove from session, add to session, add student, select TA(course)

if __name__ == '__main__':
    main()