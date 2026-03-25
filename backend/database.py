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
                    PRIMARY KEY (net_id))
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE student (
                    net_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    PRIMARY KEY (net_id))
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE course (
                    course INTEGER NOT NULL,
                    PRIMARY KEY (course)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE assignment (
                    assignment TEXT NOT NULL,
                    course INTEGER NOT NULL,
                    PRIMARY KEY (assignment))
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE session (
                    session_id INTEGER NOT NULL,
                    student TEXT NOT NULL,
                    name TEXT NOT NULL,
                    available BOOLEAN NOT NULL,
                    available list NOT NULL,
                    PRIMARY KEY (net_id))
                    )
                ''')
                
#remove from session, add to session, add student, select ta(course)
