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
                cursor.execute('DROP TABLE IF EXISTS ta_course')
                cursor.execute('DROP TABLE IF EXISTS assignment')
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
                    CREATE TABLE IF NOT EXISTS ta_course (
                    ta_netid TEXT NOT NULL,
                    course_code INTEGER,
                    PRIMARY KEY (ta_netid)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS assignment (
                    assignment_id INTEGER NOT NULL,
                    course_code INTEGER NOT NULL,
                    name text,
                    PRIMARY KEY (assignment_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session (
                    session_id SERIAL PRIMARY KEY,
                    student_netid TEXT NOT NULL,
                    ta_netid TEXT,
                    course TEXT NOT NULL,
                    assignment TEXT,
                    bug_description TEXT,
                    time_joined TEXT
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

                # Add student to student table
                cursor.execute('''
                    INSERT INTO student (student_netid, student_name)
                    VALUES (%s, %s)
                ''', [student_netid, student_name])
                
                # Match student with a TA
                #ta = find_ta(course)

                #get ta info
                #statement_str = """SELECT ta_netid, ta_name 
                #FROM ta
                #WHERE ta_netid = ? 
                #"""
                #cursor.execute(statement_str, (f"%{ta}%"))
                #table = cursor.fetchall()
                #ta_name = table[0][1]

                #find place of student
                #statement_str = """SELECT student_netid
                #FROM student
                #WHERE course = ?
                #ORDER BY time_joined ASC
                #"""
                #cursor.execute(statement_str, (f"%{course}%"))
                #table = cursor.fetchall()
                #place = table.index(student_netid)

                # Add session to the session table
                #add ta back
                cursor.execute('''
                INSERT INTO session (session_id, student_netid, course, assignment, bug_description) 
                VALUES (%s, %s, %s, %s, %s)
                ''', [session_id, student_netid, course, assignment, bug_description])
                connection.commit()
                #return [place]
    except Exception as ex:
        print("ERROR:", ex)
        raise

#finding tas that are available and match code, update ta availability
def find_ta(course):
    try:
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                statement_str = """SELECT ta_courses.ta_netid, ta.ta_netid, ta.available 
                FROM ta_courses, ta 
                WHERE course_code = ? 
                AND ta_courses.ta_netid = ta.ta_netid
                AND available = TRUE"""
                cursor.execute(statement_str, (f"%{course}%"))
                table = cursor.fetchall()
                ta = table[0][0]
                statement_str = "UPDATE ta SET available = False WHERE ta_netid=?"
                cursor.execute(statement_str, (f"%{ta}%"))

                connection.commit()
                return ta
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
                
#remove from session, add to session, add student, select ta(course)

if __name__ == '__main__':
    main()