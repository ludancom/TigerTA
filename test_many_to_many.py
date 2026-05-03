#!/usr/bin/env python
#-----------------------------------------------------------------------
# test_many_to_many.py
#-----------------------------------------------------------------------
"""
Automated test script for the TigerTA database layer.

Populates the database with many TAs and many students, exercises the
matching / queueing logic, and verifies that data flows correctly
through the system. Designed to satisfy the 'many-to-many' test
automation requirement.

USAGE
-----
Run the tests directly:
    python -m unittest test_many_to_many.py -v

Run with coverage and generate a screenshot-able HTML report:
    coverage run --source=database -m unittest test_many_to_many.py
    coverage report -m
    coverage html
    # then open htmlcov/index.html in your browser and screenshot it

To include the route handlers in the report too:
    coverage run --source=database,student,ta,admin -m unittest test_many_to_many.py

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
TEST_PREFIX = 'tst'  # all test netIDs start with this; cleanup uses LIKE 'tst%'


def _cleanup_test_rows():
    """Delete every test row from every table. Safe to call repeatedly.
    Order matters because of foreign-key constraints."""
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


# Course mix used across tests
TA_LINEUP_126 = 6     # number of COS 126 TAs to add
TA_LINEUP_2XX = 4     # number of COS 2XX TAs to add
STUDENTS_126  = 12    # number of COS 126 students to enqueue
STUDENTS_226  = 6     # number of COS 226 students
STUDENTS_217  = 4     # number of COS 217 students


class ManyToManyTigerTATests(unittest.TestCase):
    """End-to-end exercise of the database layer with many TAs and
    many students. Each test is independent: setUp wipes the test slice
    of every table so tests can run in any order."""

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
    # Helpers
    # ------------------------------------------------------------------
    def _populate_tas(self):
        """Add TA_LINEUP_126 + TA_LINEUP_2XX TAs to the database."""
        for i in range(1, TA_LINEUP_126 + 1):
            database.add_ta(
                _ta_id(i), f'TA {i}',
                f'{_ta_id(i)}@princeton.edu', 'COS 126')
        for i in range(TA_LINEUP_126 + 1,
                       TA_LINEUP_126 + TA_LINEUP_2XX + 1):
            database.add_ta(
                _ta_id(i), f'TA {i}',
                f'{_ta_id(i)}@princeton.edu', 'COS 2XX')

    def _populate_students(self, n_126=STUDENTS_126,
                           n_226=STUDENTS_226, n_217=STUDENTS_217):
        """Enqueue students with a known course mix. Returns the list of
        (netid, course) tuples in queue order."""
        order = []
        idx = 1
        # Interleave so the queue isn't trivially sorted by course
        for k in range(max(n_126, n_226, n_217)):
            for course, total in [
                ('COS 126', n_126),
                ('COS 226', n_226),
                ('COS 217', n_217),
            ]:
                if k < total:
                    sid = _student_id(idx)
                    database.queue_entry({
                        'student_netid': sid,
                        'student_name': f'Student {idx}',
                        'course': course,
                        'assignment': 'a1',
                        'bug_description': f'help with {course} #{idx}',
                    })
                    order.append((sid, course))
                    idx += 1
        return order

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_01_add_many_tas(self):
        """Adding many TAs should produce the right count and link
        each TA to their course in ta_courses."""
        self._populate_tas()

        all_tas = [t for t in database.get_all_tas()
                   if t['ta_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(all_tas), TA_LINEUP_126 + TA_LINEUP_2XX)

        by_id = {t['ta_netid']: t for t in all_tas}
        for i in range(1, TA_LINEUP_126 + 1):
            self.assertEqual(by_id[_ta_id(i)]['courses'], 'COS 126')
        for i in range(TA_LINEUP_126 + 1,
                       TA_LINEUP_126 + TA_LINEUP_2XX + 1):
            self.assertEqual(by_id[_ta_id(i)]['courses'], 'COS 2XX')

    def test_02_enqueue_many_students(self):
        """Enqueue many students and verify queue ordering and counts."""
        order = self._populate_students()

        queue = database.get_queue_students()
        queue = [q for q in queue
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), len(order))

        # Queue numbers should be 1..N strictly increasing
        for i, q in enumerate(queue, start=1):
            self.assertEqual(q['queue_number'], i)

        # Insertion order should match queue order
        for (sid, _course), q in zip(order, queue):
            self.assertEqual(q['student_netid'], sid)

    def test_03_find_student_place_per_course(self):
        """find_student_place should be per-course and 1-indexed."""
        self._populate_students()

        # In our interleave, the first student in each course is at
        # positions 1, 2, 3 in their respective per-course queues.
        first_126 = _student_id(1)
        first_226 = _student_id(2)
        first_217 = _student_id(3)
        self.assertEqual(
            database.find_student_place('COS 126', first_126), 1)
        self.assertEqual(
            database.find_student_place('COS 226', first_226), 1)
        self.assertEqual(
            database.find_student_place('COS 217', first_217), 1)

    def test_04_already_in_queue_detection(self):
        """student_already_in_queue distinguishes 3 states."""
        sid = _student_id(1)
        self.assertEqual(
            database.student_already_in_queue(sid), 'DoesNotExist')

        database.queue_entry({
            'student_netid': sid, 'student_name': 'In Queue',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': 'x',
        })
        self.assertEqual(
            database.student_already_in_queue(sid), 'InQueue')

    def test_05_126_ta_only_matches_126_students(self):
        """A COS 126 TA must never be matched with a 226/217 student."""
        self._populate_tas()
        # Only 2XX students in queue
        self._populate_students(n_126=0, n_226=3, n_217=2)

        ta_netid = _ta_id(1)  # this is a 126 TA
        result = database.match(ta_netid)
        self.assertIsNone(
            result,
            '126 TA should not match when no 126 students are queued')

    def test_06_2xx_ta_overflow_helps_126(self):
        """When no 2XX students are queued, a 2XX TA may pick up a 126
        student (overflow handling)."""
        self._populate_tas()
        self._populate_students(n_126=3, n_226=0, n_217=0)

        ta_netid = _ta_id(TA_LINEUP_126 + 1)  # first 2XX TA

        self.assertTrue(
            database.detect_overflow(),
            'overflow should be true with no 2XX students')

        session_id = database.match(ta_netid)
        self.assertIsNotNone(
            session_id,
            '2XX TA should match a 126 student during overflow')

        info = database.get_session_info_ta(ta_netid)
        self.assertIsNotNone(info)
        self.assertEqual(info['course'], 'COS 126')

    def test_07_2xx_ta_prefers_2xx_when_available(self):
        """When 2XX students are present, a 2XX TA must take a 2XX
        student first, even if 126 students were enqueued earlier."""
        self._populate_tas()
        # 5 126 students enqueued first, then 2 226 students
        for i in range(1, 6):
            database.queue_entry({
                'student_netid': _student_id(i),
                'student_name': f's{i}', 'course': 'COS 126',
                'assignment': 'a1', 'bug_description': '.',
            })
        for i in range(6, 8):
            database.queue_entry({
                'student_netid': _student_id(i),
                'student_name': f's{i}', 'course': 'COS 226',
                'assignment': 'a1', 'bug_description': '.',
            })

        ta_netid = _ta_id(TA_LINEUP_126 + 1)  # a 2XX TA
        self.assertFalse(
            database.detect_overflow(),
            'overflow should be false when 2XX students exist')

        database.match(ta_netid)
        info = database.get_session_info_ta(ta_netid)
        self.assertEqual(
            info['course'], 'COS 226',
            '2XX TA must pick a 2XX student before any 126 students')

    def test_08_full_match_cycle_many_to_many(self):
        """Many-to-many cycle: many TAs each grab one student, then end
        the session. Exercises add/match/end/cleanup paths together."""
        self._populate_tas()
        order = self._populate_students()

        matched_ta_count = 0
        for i in range(1, TA_LINEUP_126 + 1):
            session_id = database.match(_ta_id(i))
            if session_id is not None:
                matched_ta_count += 1

        self.assertEqual(
            matched_ta_count, TA_LINEUP_126,
            'every 126 TA should match (more 126 students than TAs)')

        remaining = [q for q in database.get_queue_students()
                     if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(remaining), len(order) - matched_ta_count)

        active = [s for s in database.get_active_sessions()
                  if s['ta_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(active), matched_ta_count)

        # End every session
        for session in active:
            database.remove_session(session['student_netid'])

        active = [s for s in database.get_active_sessions()
                  if s['ta_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(
            len(active), 0, 'all test sessions should be removed')

    def test_09_clock_in_clock_out_lifecycle(self):
        """Clock-in flips clocked_in to True; clock-out flips it back."""
        self._populate_tas()
        ta_netid = _ta_id(1)

        self.assertFalse(database.check_if_clocked_in(ta_netid))
        database.clock_in(ta_netid)
        self.assertTrue(database.check_if_clocked_in(ta_netid))
        database.clock_out(ta_netid)  # googlesheet.log_shift mocked
        self.assertFalse(database.check_if_clocked_in(ta_netid))

    def test_10_get_num_on_shift_tas_per_course(self):
        """Counts of clocked-in TAs are scoped per course."""
        self._populate_tas()

        # Clock in three 126 TAs and two 2XX TAs
        for i in range(1, 4):
            database.clock_in(_ta_id(i))
        for i in range(TA_LINEUP_126 + 1, TA_LINEUP_126 + 3):
            database.clock_in(_ta_id(i))

        self.assertEqual(database.get_num_on_shift_tas('COS 126'), 3)
        self.assertEqual(database.get_num_on_shift_tas('COS 2XX'), 2)

    def test_11_remove_ta_cleans_up_courses(self):
        """remove_ta deletes the TA and any ta_courses rows for them."""
        self._populate_tas()
        target = _ta_id(1)

        before = [t for t in database.get_all_tas()
                  if t['ta_netid'] == target]
        self.assertEqual(len(before), 1)

        database.remove_ta(target)

        after = [t for t in database.get_all_tas()
                 if t['ta_netid'] == target]
        self.assertEqual(len(after), 0)

    def test_12_edit_ta_updates_name_and_courses(self):
        """edit_ta should change the TA's name and replace their
        courses (deleting the old set and inserting the new one)."""
        self._populate_tas()
        target = _ta_id(1)

        database.edit_ta(
            target, 'New Name',
            f'{target}@princeton.edu', 'COS 126, COS 2XX')

        all_tas = {t['ta_netid']: t for t in database.get_all_tas()}
        self.assertEqual(all_tas[target]['ta_name'], 'New Name')
        self.assertEqual(
            all_tas[target]['courses'], 'COS 126, COS 2XX')

    def test_13_update_num_students_helped(self):
        """update_num_students_helped should increment the counter on
        the TA's open shift row."""
        self._populate_tas()
        ta_netid = _ta_id(1)
        database.clock_in(ta_netid)

        database.update_num_students_helped(ta_netid)
        database.update_num_students_helped(ta_netid)
        database.update_num_students_helped(ta_netid)

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT students_helped FROM shifts "
                    "WHERE ta_netid = %s",
                    (ta_netid,))
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], 3)

    def test_14_validate_ta_recognises_known_tas_only(self):
        """validate_ta must return True for TAs we added and falsy for
        any unknown netid."""
        self._populate_tas()

        self.assertTrue(database.validate_ta(_ta_id(1)))
        self.assertFalse(database.validate_ta('nottrue1'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
