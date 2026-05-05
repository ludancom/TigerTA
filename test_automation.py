#!/usr/bin/env python
#-----------------------------------------------------------------------
# test_automation.py
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
    python -m unittest test_automation.py -v

Run with coverage and generate a screenshot-able HTML report:
    coverage run --source=database -m unittest test_automation.py
    coverage report -m
    coverage html
    # then open htmlcov/index.html in your browser and screenshot it

To include the route handlers in the report too:
    coverage run --source=database,student,ta,admin -m unittest test_automation.py

NOTES
-----
* Tests connect to the database in DATABASE_URL (your .env file).
* Test rows use the 'tst' netID prefix; cleanup runs before and after,
  so existing TigerTA data is left alone.
* Email notifications and Google Sheet writes are mocked so running
  the tests doesn't send emails or modify the real shift log.
"""

import os
import time
import contextlib
import unittest
import concurrent.futures

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
        """find_student_place should be per-course (with COS 226/217
        sharing a combined 2XX queue) and 1-indexed.

        The shared database may have real students queued ahead of
        ours, so we count rows ahead at assertion time and assert
        relative to that baseline."""
        self._populate_students()

        # find_student_place treats 226 and 217 as one combined queue.
        QUEUE_OF = {
            'COS 126': ('COS 126',),
            'COS 226': ('COS 226', 'COS 217'),
            'COS 217': ('COS 226', 'COS 217'),
        }

        def _expected_place(course, sid):
            """Count rows ahead of `sid` (inclusive of itself) in the
            queue that find_student_place uses, by reading the same
            rows directly from the session table."""
            queue_courses = QUEUE_OF[course]
            placeholders = ','.join(['%s'] * len(queue_courses))
            with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
                with contextlib.closing(conn.cursor()) as cur:
                    cur.execute(
                        f"SELECT session_id FROM session "
                        f"WHERE student_netid = %s "
                        f"AND course IN ({placeholders}) "
                        f"AND ta_netid IS NULL",
                        (sid, *queue_courses))
                    row = cur.fetchone()
                    if row is None:
                        return None
                    my_sid = row[0]
                    cur.execute(
                        f"SELECT COUNT(*) FROM session "
                        f"WHERE course IN ({placeholders}) "
                        f"AND ta_netid IS NULL "
                        f"AND session_id <= %s",
                        (*queue_courses, my_sid))
                    return cur.fetchone()[0]

        first_126 = _student_id(1)
        first_226 = _student_id(2)
        first_217 = _student_id(3)
        self.assertEqual(
            database.find_student_place('COS 126', first_126),
            _expected_place('COS 126', first_126))
        self.assertEqual(
            database.find_student_place('COS 226', first_226),
            _expected_place('COS 226', first_226))
        self.assertEqual(
            database.find_student_place('COS 217', first_217),
            _expected_place('COS 217', first_217))

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
        """Counts of clocked-in TAs are scoped per course.

        Uses baselines so this passes against a shared database that
        may already have real TAs clocked in for either course."""
        base_126 = database.get_num_on_shift_tas('COS 126')
        base_2xx = database.get_num_on_shift_tas('COS 2XX')

        self._populate_tas()

        # Clock in three 126 TAs and two 2XX TAs
        for i in range(1, 4):
            database.clock_in(_ta_id(i))
        for i in range(TA_LINEUP_126 + 1, TA_LINEUP_126 + 3):
            database.clock_in(_ta_id(i))

        self.assertEqual(
            database.get_num_on_shift_tas('COS 126'), base_126 + 3)
        self.assertEqual(
            database.get_num_on_shift_tas('COS 2XX'), base_2xx + 2)

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

    # ------------------------------------------------------------------
    # Coverage tests for the remaining helper functions in database.py.
    # These exist mostly to drive every public function from the test
    # suite so the coverage report reflects real exercise of the data
    # layer (not just the many-to-many flow).
    # ------------------------------------------------------------------
    def test_15_get_session_info_student_and_ta_name(self):
        """After matching, both student-side helpers return the right
        info: get_session_info_student gives course/bug/session_id and
        get_session_ta_name gives the TA's display name."""
        self._populate_tas()
        self._populate_students(n_126=1, n_226=0, n_217=0)
        ta_netid = _ta_id(1)
        student_netid = _student_id(1)

        # Before match: no session info / no TA name
        self.assertIsNone(database.get_session_ta_name(student_netid))

        database.match(ta_netid)

        info = database.get_session_info_student(student_netid)
        self.assertIsNotNone(info)
        self.assertEqual(info['course'], 'COS 126')
        self.assertIn('help with COS 126', info['bug_description'])
        self.assertIsNotNone(info['session_id'])

        ta_name = database.get_session_ta_name(student_netid)
        self.assertEqual(ta_name, 'TA 1')

    def test_16_notify_next_in_line_sets_flag(self):
        """notify_next_in_line should mark the front-of-line student's
        notified_next flag in the session table."""
        self._populate_students(n_126=2, n_226=0, n_217=0)
        front = _student_id(1)

        # Initially notified_next is False (default)
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT notified_next FROM session "
                    "WHERE student_netid = %s", (front,))
                self.assertFalse(cur.fetchone()[0])

        database.notify_next_in_line('COS 126')

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT notified_next FROM session "
                    "WHERE student_netid = %s", (front,))
                self.assertTrue(cur.fetchone()[0])

        # Calling again is a no-op (already notified) -- exercises the
        # early-return branch.
        database.notify_next_in_line('COS 126')

        # On an empty queue it should also early-return without error.
        database.notify_next_in_line('COS 126 NONEXISTENT')

    def test_17_set_available_flips_flag(self):
        """set_available should flip a TA's available flag back to
        TRUE (used after match completes)."""
        self._populate_tas()
        ta_netid = _ta_id(1)

        # Manually set TA to unavailable (simulating mid-match state)
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "UPDATE ta SET available = FALSE WHERE ta_netid = %s",
                    (ta_netid,))
                conn.commit()

        database.set_available(ta_netid)

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT available FROM ta WHERE ta_netid = %s",
                    (ta_netid,))
                self.assertTrue(cur.fetchone()[0])

    def test_18_get_time_session_began(self):
        """After a match, time_session_began is set (not NULL); on a
        bogus session id, the function returns None."""
        self._populate_tas()
        self._populate_students(n_126=1, n_226=0, n_217=0)
        session_id = database.match(_ta_id(1))
        self.assertIsNotNone(session_id)

        ts = database.get_time_session_began(session_id)
        self.assertIsNotNone(ts)

        # Bogus id -> None
        self.assertIsNone(database.get_time_session_began(-1))

    def test_19_student_already_in_queue_in_session_state(self):
        """student_already_in_queue should return 'InSession' once a
        student has been matched with a TA."""
        self._populate_tas()
        self._populate_students(n_126=1, n_226=0, n_217=0)
        student_netid = _student_id(1)

        self.assertEqual(
            database.student_already_in_queue(student_netid), 'InQueue')

        database.match(_ta_id(1))

        self.assertEqual(
            database.student_already_in_queue(student_netid), 'InSession')

    def test_20_validate_admin(self):
        """validate_admin returns True for rows in the admin table and
        False for unknown netids. We add and remove a test admin row
        directly so we don't depend on production admin data."""
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "DELETE FROM admin WHERE admin_netid LIKE %s",
                    (f'{TEST_PREFIX}%',))
                cur.execute(
                    "INSERT INTO admin (admin_netid) VALUES (%s)",
                    (f'{TEST_PREFIX}adm1',))
                conn.commit()

        try:
            self.assertTrue(database.validate_admin(f'{TEST_PREFIX}adm1'))
            self.assertFalse(
                database.validate_admin(f'{TEST_PREFIX}nope'))
        finally:
            with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
                with contextlib.closing(conn.cursor()) as cur:
                    cur.execute(
                        "DELETE FROM admin WHERE admin_netid LIKE %s",
                        (f'{TEST_PREFIX}%',))
                    conn.commit()

    def test_21_match_returns_none_when_queue_empty(self):
        """If a TA tries to match with an empty queue, match() should
        return None (covers the empty-queue early return paths)."""
        self._populate_tas()  # TAs but no students
        self.assertIsNone(database.match(_ta_id(1)))                # 126 TA
        self.assertIsNone(
            database.match(_ta_id(TA_LINEUP_126 + 1)))              # 2XX TA

    def test_22_get_num_on_shift_tas_normalises_2xx(self):
        """Calling get_num_on_shift_tas with 'COS 226' or 'COS 217'
        should yield the same count as 'COS 2XX' (the function
        normalises both into the combined 2XX bucket)."""
        base_2xx = database.get_num_on_shift_tas('COS 2XX')
        base_226 = database.get_num_on_shift_tas('COS 226')
        base_217 = database.get_num_on_shift_tas('COS 217')
        self.assertEqual(base_2xx, base_226)
        self.assertEqual(base_2xx, base_217)

        self._populate_tas()
        for i in range(TA_LINEUP_126 + 1, TA_LINEUP_126 + 3):
            database.clock_in(_ta_id(i))

        self.assertEqual(
            database.get_num_on_shift_tas('COS 226'), base_2xx + 2)
        self.assertEqual(
            database.get_num_on_shift_tas('COS 217'), base_2xx + 2)

    # ------------------------------------------------------------------
    # Coverage tests for early-return / invalid-input branches.
    # These exist to push coverage on the defensive checks scattered
    # throughout database.py (rejecting bad courses, returning None /
    # False when the target row doesn't exist, etc).
    # ------------------------------------------------------------------
    def test_23_queue_entry_rejects_invalid_course(self):
        """queue_entry must return False if the course isn't one of
        the three courses TigerTA supports."""
        ok = database.queue_entry({
            'student_netid': _student_id(1),
            'student_name': 'Bad Course',
            'course': 'COS 999',
            'assignment': 'a1',
            'bug_description': 'x',
        })
        self.assertFalse(
            ok, 'queue_entry should reject unknown courses')

        # And the student should not have ended up in the queue.
        queue = [q for q in database.get_queue_students()
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), 0)

    def test_24_match_returns_none_for_unknown_ta(self):
        """match() must return None when the ta_netid isn't a known
        TA (no row in ta_courses)."""
        # No TAs added at all; the netid we pass simply doesn't exist.
        self.assertIsNone(database.match(f'{TEST_PREFIX}nope1'))

    def test_25_add_ta_rejects_invalid_course(self):
        """add_ta must return False for courses other than 'COS 126'
        or 'COS 2XX' (and must not insert a TA row)."""
        ok = database.add_ta(
            f'{TEST_PREFIX}badc1', 'Bad Course TA',
            f'{TEST_PREFIX}badc1@princeton.edu', 'COS 999')
        self.assertFalse(
            ok, 'add_ta should reject unsupported courses')

        # Verify the TA was not inserted.
        all_tas = database.get_all_tas()
        self.assertNotIn(
            f'{TEST_PREFIX}badc1',
            [t['ta_netid'] for t in all_tas])

    def test_26_clock_in_returns_false_for_unknown_ta(self):
        """clock_in must return False when no TA row matches (the
        rowcount == 0 branch)."""
        result = database.clock_in(f'{TEST_PREFIX}nope2')
        self.assertFalse(
            result, 'clock_in should fail for an unknown TA')

    def test_27_clock_out_returns_false_for_unknown_ta(self):
        """clock_out must return False when no TA row matches (the
        rowcount == 0 branch)."""
        result = database.clock_out(f'{TEST_PREFIX}nope3')
        self.assertFalse(
            result, 'clock_out should fail for an unknown TA')

    def test_28_clock_out_deletes_shift_when_log_succeeds(self):
        """When googlesheet.log_shift reports success, clock_out
        should DELETE the TA's shift row from the database (covers
        the success-path branch in clock_out)."""
        self._populate_tas()
        ta_netid = _ta_id(1)
        database.clock_in(ta_netid)

        # Temporarily make log_shift report success so clock_out
        # takes the "delete the shift row" branch. Restore in finally
        # so we don't leak state into other tests.
        original = googlesheet.log_shift
        googlesheet.log_shift = lambda *a, **kw: True
        try:
            self.assertTrue(database.clock_out(ta_netid))
        finally:
            googlesheet.log_shift = original

        # After a successful log, the shift row should be gone.
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM shifts WHERE ta_netid = %s",
                    (ta_netid,))
                self.assertEqual(cur.fetchone()[0], 0)

    def test_29_get_session_info_student_returns_none_for_unknown(self):
        """get_session_info_student must return None when the student
        isn't in the queue or any session."""
        self.assertIsNone(
            database.get_session_info_student(f'{TEST_PREFIX}nope4'))

    def test_30_get_session_ta_name_pre_match_returns_none(self):
        """get_session_ta_name must return None for a student who is
        in the queue but has not yet been matched to a TA."""
        sid = _student_id(1)
        database.queue_entry({
            'student_netid': sid, 'student_name': 'Solo',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': '.',
        })
        self.assertIsNone(database.get_session_ta_name(sid))

    def test_31_remove_session_returns_false_for_unknown_student(self):
        """remove_session must return False when there's no session
        or student row to remove (numRowsDeleted stays 0)."""
        result = database.remove_session(f'{TEST_PREFIX}nope5')
        self.assertFalse(
            result, 'remove_session should be False when nothing was '
            'deleted')

    def test_32_remove_ta_returns_false_for_unknown_ta(self):
        """remove_ta must return False when no rows in any of the
        TA-related tables match."""
        result = database.remove_ta(f'{TEST_PREFIX}nope6')
        self.assertFalse(
            result, 'remove_ta should be False when nothing was '
            'deleted')


# ---------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------
# These tests push the database layer with high volume and concurrent
# operations. They check:
#   * High-volume enqueue + drain still produces correct ordering and
#     counts, and finishes within a reasonable time budget.
#   * Concurrent match() calls never assign the same student to two TAs
#     and never produce duplicate active sessions.
#   * Concurrent queue_entry() calls all land in the queue with unique
#     session_ids and contiguous queue numbers.
#
# Sizes are tuned to be meaningful but to also fit in an 8-character
# netID (matches the rest of the suite, which uses tstta001 / tstst001
# style ids) and to keep total runtime reasonable on a shared database.
# ---------------------------------------------------------------------

STRESS_TA_126 = 10      # number of COS 126 TAs for stress runs
STRESS_TA_2XX = 8       # number of COS 2XX TAs for stress runs
STRESS_STUDENTS_126 = 60
STRESS_STUDENTS_226 = 40
STRESS_STUDENTS_217 = 25

CONCURRENT_TAS = 15          # threads racing to match() at once
CONCURRENT_STUDENTS = 30     # students available to those TAs
CONCURRENT_ENQUEUE = 40      # threads racing to queue_entry() at once


class StressTigerTATests(unittest.TestCase):
    """Stress / load tests for the database layer.

    Reuses the same 'tst' netID prefix and cleanup machinery as
    ManyToManyTigerTATests so it stays hermetic on a shared database.
    """

    @classmethod
    def setUpClass(cls):
        _cleanup_test_rows()

    @classmethod
    def tearDownClass(cls):
        _cleanup_test_rows()

    def setUp(self):
        _cleanup_test_rows()
        # Same safety guard as ManyToManyTigerTATests: refuse to run
        # against a database that already has real (non-test) sessions
        # in the queue, because match() looks at the entire queue and
        # could pull a real student into a test session.
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM session "
                    "WHERE student_netid NOT LIKE %s",
                    (f'{TEST_PREFIX}%',))
                live = cur.fetchone()[0]
                if live > 0:
                    self.skipTest(
                        f'Refusing to run stress test: {live} non-test '
                        f'session(s) exist in the queue.')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _populate_stress_tas(self):
        """Add STRESS_TA_126 + STRESS_TA_2XX TAs at once."""
        for i in range(1, STRESS_TA_126 + 1):
            database.add_ta(
                _ta_id(i), f'TA {i}',
                f'{_ta_id(i)}@princeton.edu', 'COS 126')
        for i in range(STRESS_TA_126 + 1,
                       STRESS_TA_126 + STRESS_TA_2XX + 1):
            database.add_ta(
                _ta_id(i), f'TA {i}',
                f'{_ta_id(i)}@princeton.edu', 'COS 2XX')

    def _populate_stress_students(self, n_126, n_226, n_217):
        """Enqueue (n_126 + n_226 + n_217) students with an
        interleaved course mix so the queue isn't trivially sorted."""
        idx = 1
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
                    idx += 1
        return idx - 1   # total students enqueued

    # ------------------------------------------------------------------
    # Stress tests
    # ------------------------------------------------------------------
    def test_stress_01_high_volume_drain(self):
        """Enqueue many students against many TAs and repeatedly call
        match() until the queue is empty. Asserts correctness only
        (no hard time budget, since database.py opens a fresh
        connection per call and remote-DB latency dominates)."""

        t0 = time.monotonic()
        self._populate_stress_tas()
        total_enqueued = self._populate_stress_students(
            STRESS_STUDENTS_126,
            STRESS_STUDENTS_226,
            STRESS_STUDENTS_217)
        enqueue_elapsed = time.monotonic() - t0

        # Sanity: every test student we tried to enqueue is in the queue
        queue = [q for q in database.get_queue_students()
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), total_enqueued)

        # Drain: walk through every TA once. With 35 TAs and ~250
        # students, the queue won't fully drain on a single pass --
        # so we loop until either the queue is empty or no TA was able
        # to match this round (overflow rules can leave 126-only TAs
        # idle once 126 students are exhausted).
        all_session_ids = []
        all_student_netids = []
        rounds = 0
        while True:
            rounds += 1
            matched_this_round = 0
            for i in range(1, STRESS_TA_126 + STRESS_TA_2XX + 1):
                ta_netid = _ta_id(i)
                # Free up the TA before each match call (set_available
                # flips them back to available so they can match again
                # in the next round).
                database.set_available(ta_netid)
                # End any active session for this TA so they're free
                info = database.get_session_info_ta(ta_netid)
                if info is not None:
                    student = info.get('student_netid')
                    if student is not None:
                        database.remove_session(student)

                session_id = database.match(ta_netid)
                if session_id is not None:
                    all_session_ids.append(session_id)
                    new_info = database.get_session_info_ta(ta_netid)
                    self.assertIsNotNone(new_info)
                    all_student_netids.append(new_info['student_netid'])
                    matched_this_round += 1

            if matched_this_round == 0:
                break
            self.assertLess(
                rounds, 100,
                'drain loop should never need this many rounds')

        # Tear down any remaining active sessions so we leave the
        # queue/sessions in a known state.
        for i in range(1, STRESS_TA_126 + STRESS_TA_2XX + 1):
            ta_netid = _ta_id(i)
            info = database.get_session_info_ta(ta_netid)
            if info is not None and info.get('student_netid') is not None:
                database.remove_session(info['student_netid'])

        elapsed = time.monotonic() - t0

        # Every student the system handed out should be unique --
        # nobody got matched twice.
        self.assertEqual(
            len(all_student_netids), len(set(all_student_netids)),
            'stress drain handed the same student to two TAs')

        # We should have matched as many students as we enqueued (or
        # extremely close, accounting for 126-TA-only-can-help-126
        # rules -- but our mix has more 126 students than 126 TAs, so
        # everyone should ultimately match).
        self.assertEqual(
            len(all_student_netids), total_enqueued,
            f'enqueued {total_enqueued} but only matched '
            f'{len(all_student_netids)}')

        # And the queue is empty of test students.
        leftover = [q for q in database.get_queue_students()
                    if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(leftover), 0)

        # Print timing as a soft signal -- not asserted, since wall
        # clock depends entirely on the remote DB's network latency.
        print(
            f'\n[stress_01 timing] enqueue {total_enqueued} students: '
            f'{enqueue_elapsed:.1f}s | full drain + cleanup: '
            f'{elapsed:.1f}s')

    def test_stress_02_concurrent_match_no_double_assignment(self):
        """Spawn many threads each calling match() at the same time.

        The critical invariant: no student may be assigned to two
        different TAs in the session table, even under contention.
        match() reads the front of the queue and writes the assignment
        in two separate statements with no row lock, so this is the
        most likely place a real concurrency bug would show up."""

        # Set up: enough TAs and students that all TAs would *want*
        # to match if there were no contention.
        for i in range(1, CONCURRENT_TAS + 1):
            database.add_ta(
                _ta_id(i), f'TA {i}',
                f'{_ta_id(i)}@princeton.edu', 'COS 126')
        for i in range(1, CONCURRENT_STUDENTS + 1):
            database.queue_entry({
                'student_netid': _student_id(i),
                'student_name': f'Student {i}',
                'course': 'COS 126',
                'assignment': 'a1',
                'bug_description': f'concurrent match #{i}',
            })

        # All TAs race to match at the same time.
        ta_netids = [_ta_id(i) for i in range(1, CONCURRENT_TAS + 1)]
        results = []
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=CONCURRENT_TAS) as pool:
            futures = [pool.submit(database.match, n) for n in ta_netids]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # ----- Invariant 1: no duplicate active sessions per student
        # Read every active session in the test slice and assert each
        # student_netid appears at most once.
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT student_netid, ta_netid FROM session "
                    "WHERE ta_netid IS NOT NULL "
                    "AND student_netid LIKE %s",
                    (f'{TEST_PREFIX}%',))
                active = cur.fetchall()

        active_students = [row[0] for row in active]
        active_tas = [row[1] for row in active]
        self.assertEqual(
            len(active_students), len(set(active_students)),
            'concurrent match() assigned the same student to two TAs')
        self.assertEqual(
            len(active_tas), len(set(active_tas)),
            'concurrent match() put the same TA in two sessions')

        # ----- Invariant 2: count sanity
        # We had CONCURRENT_TAS TAs and CONCURRENT_STUDENTS students
        # available; the number of active sessions can't exceed
        # min(TAs, students).
        self.assertLessEqual(
            len(active),
            min(CONCURRENT_TAS, CONCURRENT_STUDENTS),
            'more active sessions than TAs/students should allow')

        # ----- Invariant 3: returned session_ids point at real, unique
        # session rows when non-None.
        successful = [r for r in results if r is not None]
        self.assertEqual(
            len(successful), len(set(successful)),
            'match() returned the same session_id from two different '
            'concurrent calls')

    def test_stress_03_concurrent_enqueue(self):
        """Many students enqueue at the same instant. All of them
        should land in the queue, each with a unique session_id and
        contiguous 1..N queue_numbers in the test slice."""

        def _enqueue_one(i):
            database.queue_entry({
                'student_netid': _student_id(i),
                'student_name': f'Student {i}',
                'course': 'COS 126',
                'assignment': 'a1',
                'bug_description': f'concurrent enqueue #{i}',
            })

        ids = list(range(1, CONCURRENT_ENQUEUE + 1))
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=20) as pool:
            list(pool.map(_enqueue_one, ids))

        # All students made it in.
        queue = [q for q in database.get_queue_students()
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), CONCURRENT_ENQUEUE)

        # All session_ids are unique (no duplicate row insertion).
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT session_id, student_netid FROM session "
                    "WHERE student_netid LIKE %s",
                    (f'{TEST_PREFIX}%',))
                rows = cur.fetchall()

        session_ids = [r[0] for r in rows]
        student_netids = [r[1] for r in rows]
        self.assertEqual(
            len(session_ids), len(set(session_ids)),
            'duplicate session_ids after concurrent enqueue')
        self.assertEqual(
            len(student_netids), len(set(student_netids)),
            'duplicate student rows after concurrent enqueue')

        # queue_numbers in the test slice should be 1..N.
        nums = sorted(q['queue_number'] for q in queue)
        self.assertEqual(nums, list(range(1, CONCURRENT_ENQUEUE + 1)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
