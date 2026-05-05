#!/usr/bin/env python
#-----------------------------------------------------------------------
# test_boundary.py
#-----------------------------------------------------------------------
"""
Automated test script for the TigerTA database layer.

Populates the database with many TAs and many students, exercises the
matching / queueing logic, and verifies that data flows correctly
through the system. Designed to satisfy the test automation +
many-to-many requirements.

USAGE
-----
Run the tests directly:
    python -m unittest test_boundary.py -v

Run with coverage and generate a screenshot-able HTML report:
    coverage run --source=database -m unittest test_boundary.py
    coverage report -m
    coverage html
    # then open htmlcov/index.html in your browser and screenshot it

To include the route handlers in the report too:
    coverage run --source=database,student,ta,admin -m unittest test_boundary.py

NOTES
-----
* Tests connect to the database in DATABASE_URL (your .env file).
* Test rows use the 'tst' netID prefix; cleanup runs before and after,
  so existing TigerTA data is left alone.
* Email notifications and Google Sheet writes are mocked so running
  the tests doesn't send emails or modify the real shift log.
"""

import os
import contextlib
import unittest

import psycopg
import dotenv

dotenv.load_dotenv()

# ---------------------------------------------------------------------
# Mock side-effecting modules BEFORE importing database.py.
# database.py calls notifications.send_* and googlesheet.log_shift; we
# replace those with no-ops so the tests are hermetic.
# ---------------------------------------------------------------------
import notifications
import googlesheet

notifications.send_matched = lambda *args, **kwargs: None
notifications.send_next_in_line = lambda *args, **kwargs: None
googlesheet.log_shift = lambda *args, **kwargs: None

import database  # noqa: E402  -- must come after the mocks above


DATABASE_URL = os.environ['DATABASE_URL']
TEST_PREFIX = 'tst'  # All test netIDs start with this; cleanup uses LIKE 'tst%'


def _cleanup_test_rows():
    """ Delete every test row from every table. Safe to call repeatedly.
    Order matters because of foreign-key constraints. """

    with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
        with contextlib.closing(conn.cursor()) as cur:
            cur.execute(
                "DELETE FROM session "
                "WHERE student_netid LIKE %s OR ta_netid LIKE %s",
                (f'{TEST_PREFIX}%', f'{TEST_PREFIX}%'))
            cur.execute(
                "DELETE FROM shifts WHERE ta_netid LIKE %s",
                (f'{TEST_PREFIX}%',))
            cur.execute(
                "DELETE FROM ta_courses WHERE ta_netid LIKE %s",
                (f'{TEST_PREFIX}%',))
            cur.execute(
                "DELETE FROM student WHERE student_netid LIKE %s",
                (f'{TEST_PREFIX}%',))
            cur.execute(
                "DELETE FROM ta WHERE ta_netid LIKE %s",
                (f'{TEST_PREFIX}%',))
            conn.commit()


def _ta_id(n):
    return f'{TEST_PREFIX}ta{n:03d}'   # tstta001, tstta002, ... (8 chars)


def _student_id(n):
    return f'{TEST_PREFIX}st{n:03d}'   # tstst001, tstst002, ... (8 chars)

class BoundaryTigerTATests(unittest.TestCase):
    """ End-to-end exercise of the database layer with TAs and
    students, with a focus on edge cases. Each test is 
    independent: setUp wipes the test slice
    of every table so tests can run in any order. """

    @classmethod
    def setUpClass(cls):
        _cleanup_test_rows()

    @classmethod
    def tearDownClass(cls):
        _cleanup_test_rows()

    def setUp(self):
        _cleanup_test_rows()
        # Safety guard: refuse to run if real (non-test) sessions exist.
        # Tests 05/06/07 use database.match() and database.detect_overflow(),
        # which look at the entire queue -- a real student in the queue
        # could be matched to a test TA and then wiped during cleanup.
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM session "
                    "WHERE student_netid NOT LIKE %s",
                    (f'{TEST_PREFIX}%',))
                live = cur.fetchone()[0]
                if live > 0:
                    self.skipTest(
                        f'Refusing to run: {live} non-test session(s) '
                        f'exist in the queue. Run against an empty or '
                        f'dedicated test database.')

    # ------------------------------------------------------------------
    # Tests: Duplicate Insertions 
    # ------------------------------------------------------------------

    def test_01_duplicate_tas(self):
        """ Adding a TA twice should update their information instead 
        of creating two rows in the ta table with the same TA. """
        
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as connection:
            with contextlib.closing(connection.cursor()) as cursor:
                ta_netid = _ta_id(1)
                database.add_ta(
                    _ta_id(1), f'John',
                    f'{_ta_id(1)}@princeton.edu', 'COS 2XX')
                database.add_ta(
                    _ta_id(1), f'Doe',
                    f'{_ta_id(1)}@princeton.edu', 'COS 2XX')
                
                # Ensure there is one row 
                cursor.execute("""
                SELECT COUNT(*) FROM ta WHERE ta_netid = %s
                """, (ta_netid,))
                self.assertEqual(cursor.fetchone()[0], 1)

                cursor.execute("""
                SELECT ta_name FROM ta WHERE ta_netid = %s
                """, (ta_netid,))
                row = cursor.fetchone()

                self.assertEqual(row[0], 'Doe')

    def test_02_duplicate_sessions(self):
        """ Students should not be able to join the queue if 
        they are already in the queue or in an active session. """

        # Ensure students cannot join queue if they are already 
        # in the queue
        id1 = 1
        sid = _student_id(id1)
        course = "COS 217"
        result1 = database.queue_entry({
            'student_netid': sid,
            'student_name': f'Student {id1}',
            'course': course,
            'assignment': 'a1',
            'bug_description': f'help with {course} #{id1}',
        })

        result2 = database.queue_entry({
            'student_netid': sid,
            'student_name': f'Student {id1}',
            'course': course,
            'assignment': 'a1',
            'bug_description': f'help with {course} #{id1}',
        })
        
        self.assertTrue(result1)
        self.assertFalse(result2)

        # Ensure students cannot join queue if they are already 
        # in a session

        ta_netid = _ta_id(1)  # This is a 2XX TA
        database.add_ta(_ta_id(1), f'TA {1}',
        f'{_ta_id(1)}@princeton.edu', 'COS 2XX')
        result3 = database.match(ta_netid) # TA should match with student
        self.assertIsNotNone(result3)

        result4 = database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })
        self.assertFalse(result4)

    # ------------------------------------------------------------------
    # Tests: Working With Nonexistent or Invalid Fields
    # ------------------------------------------------------------------

    def test_03_remove_nonexistent_session(self):
            """ A nonexistent session should not be removed. """

            result = database.remove_session("hello")
            self.assertFalse(
                result)

    def test_04_remove_nonexistent_ta(self):
            """ A nonexistent TA should not be removed. """

            result = database.remove_ta("hello")
            self.assertFalse(result)

    def test_05_get_nonexistent_session_information(self):
            """ A nonexistent session should not have information. """

            result1 = database.get_session_ta_name("hello")
            self.assertIsNone(result1)

            result2 = database.get_session_info_student("hello")
            self.assertIsNone(result2)

            result3 = database.get_session_info_ta("hello")
            self.assertIsNone(result3)

    def test_06_add_student_with_nonexistent_netid(self):
            """ A student cannot be added to the queue without a netID. """

            id1 = 1
            course = "COS 217"
            result = database.queue_entry({
                'student_netid': None,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })
            
            self.assertFalse(result)

    def test_07_long_bug_description(self):
            """ A user cannot add input with a length greater than the character limit. """

            id1 = 1
            sid = _student_id(id1)
            course = "COS 217"
            bug_description = "lol" * 100
            result = database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': bug_description,
            })
            
            self.assertFalse(result)
    
    # ------------------------------------------------------------------
    # Tests: Queue Boundaries
    # ------------------------------------------------------------------

    def test_08_queue_empty_after_removal(self):
            """ A queue should be empty after the only 
            student in the queue leaves the queue. """
            
            queue = database.get_queue_students()
            self.assertEqual(len(queue), 0)

            id1 = 1
            sid = _student_id(id1)
            course = "COS 217"
            database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })
            queue = database.get_queue_students()
            self.assertEqual(len(queue), 1)

            database.remove_session(sid)
            queue = database.get_queue_students()
            self.assertEqual(len(queue), 0)

    def test_09_queue_empty_after_match(self):
            """ A queue should be empty after the only 
            student in the queue matches with a TA. """

            queue = database.get_queue_students()
            self.assertEqual(len(queue), 0)

            id1 = 1
            sid = _student_id(id1)
            course = "COS 217"
            database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })
            queue = database.get_queue_students()
            self.assertEqual(len(queue), 1)

            ta_netid = _ta_id(1)  # This is a 2XX TA
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')
            result3 = database.match(ta_netid) # TA should match with student
            queue = database.get_queue_students()
            self.assertEqual(len(queue), 0)

    # ------------------------------------------------------------------
    # Tests: Match Edge Cases
    # ------------------------------------------------------------------

    def test_10_two_TAs_attempt_match_with_one_student(self):
            """ Two TAs should not be able to match with the same 
            student. A TA should not be able to match when there are no
            students in the queue. """

            id1 = 1
            sid = _student_id(id1)
            course = "COS 217"
            database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })
            queue = database.get_queue_students()
            self.assertEqual(len(queue), 1)

            ta_netid1 = _ta_id(1)  # This is a 2XX TA
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')

            ta_netid2 = _ta_id(2)  # This is a 2XX TA
            database.add_ta(_ta_id(2), f'TA {2}',
            f'{_ta_id(2)}@princeton.edu', 'COS 2XX')

            result1 = database.match(ta_netid1) # First TA should match with student
            result2 = database.match(ta_netid2) # Second TA should not match with student
            
            self.assertIsNotNone(result1)
            self.assertIsNone(result2)

    def test_11_TA_attempts_match_with_two_students(self):
            """ One TA cannot help (or match with) two students at the same time. """

            id1 = 1
            sid1 = _student_id(id1)
            course = "COS 217"
            database.queue_entry({
                'student_netid': sid1,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })

            id2 = 2
            sid2 = _student_id(id2)
            database.queue_entry({
                'student_netid': sid2,
                'student_name': f'Student {id2}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id2}',
            })

            ta_netid = _ta_id(1)
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')

            result1 = database.match(ta_netid)
            result2 = database.match(ta_netid)  
            
            self.assertIsNotNone(result1)
            self.assertIsNone(result2)

    def test_12_student_leaves_during_attempt_match(self):
            """ If a student leaves the queue right before the 
            TA presses 'Start Session', they should not match. """

            id1 = 1
            sid = _student_id(id1)
            course = "COS 217"
            database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })

            ta_netid = _ta_id(1)  # this is a 2XX TA
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')

            database.remove_session(sid)
            result = database.match(ta_netid) # TA should not match with student
            
            self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Tests: Clock In and Out
    # ------------------------------------------------------------------

    def test_13_two_clockin_attempts(self):
            """ A TA should not be able to clock in twice without
            clocking out. """

            ta_netid = _ta_id(1)  # This is a 2XX TA
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')

            result1 = database.clock_in(ta_netid) 
            result2 = database.clock_in(ta_netid) 
            
            self.assertTrue(result1)
            self.assertFalse(result2)

    def test_14_two_clockout_attempts(self):
            """ A TA should not be able to clock out twice without
            clocking in. """

            ta_netid = _ta_id(1)  # This is a 2XX TA
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')

            result1 = database.clock_in(ta_netid)
            result2 = database.clock_out(ta_netid) 
            self.assertFalse(database.check_if_clocked_in(ta_netid))
            result3 = database.clock_out(ta_netid) 
            
            self.assertTrue(result1)
            self.assertFalse(result3)

    def test_15_clockout_attempt_without_clockin(self):
            """ A TA should not be able to clock out if they did not clock in. """

            ta_netid = _ta_id(1)  # This is a 2XX TA
            database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX')

            result = database.clock_out(ta_netid)
            
            self.assertFalse(result)

    # ------------------------------------------------------------------
    # Tests: Courses
    # ------------------------------------------------------------------

    def test_16_two_TA_courses(self):
            """ A TA should not be able to be assigned to multiple 
            courses at the same time (a 2XX TA, can however, 
            sometimes help 126 students). """

            result = database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', 'COS 2XX, COS 126')

            self.assertFalse(result)

    def test_17_no_TA_course(self):
            """ A TA must be assigned to a valid course. """

            result = database.add_ta(_ta_id(1), f'TA {1}',
            f'{_ta_id(1)}@princeton.edu', ' ')

            self.assertFalse(result)

    def test_18_invalid_student_course(self):
            """ A student must be assigned to a valid course. """

            id1 = 1
            sid = _student_id(id1)
            course = " "
            result = database.queue_entry({
                'student_netid': sid,
                'student_name': f'Student {id1}',
                'course': course,
                'assignment': 'a1',
                'bug_description': f'help with {course} #{id1}',
            })

            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main(verbosity=2)
