#!/usr/bin/env python
#-----------------------------------------------------------------------
# test_automation.py
#-----------------------------------------------------------------------
"""
Automated tests for TigerTA.

Run all tests:
    python -m unittest test_automation.py -v

Run with coverage:
    coverage run --source=database,student,ta,admin -m unittest test_automation.py
    coverage report -m
    coverage html

Test rows use the 'tst' netID prefix and are cleaned up before and
after each test so real data isn't touched. Emails and Google Sheet
writes are mocked.
"""

import os
import time
import contextlib
import unittest
import concurrent.futures

import psycopg
import dotenv

dotenv.load_dotenv()

# Mock notifications and googlesheet so tests don't send real emails
# or write to the real shift log.
import notifications
import googlesheet

notifications.send_matched = lambda *args, **kwargs: None
notifications.send_next_in_line = lambda *args, **kwargs: None
googlesheet.log_shift = lambda *args, **kwargs: None
googlesheet.log_feedback = lambda *args, **kwargs: None

import database


DATABASE_URL = os.environ['DATABASE_URL']
TEST_PREFIX = 'tst'


def _cleanup_test_rows():
    """Delete all test rows from every table. Order matters because
    of foreign-key constraints."""
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
    return f'{TEST_PREFIX}ta{n:03d}'


def _student_id(n):
    return f'{TEST_PREFIX}st{n:03d}'


TA_LINEUP_126 = 6
TA_LINEUP_2XX = 4
STUDENTS_126  = 12
STUDENTS_226  = 6
STUDENTS_217  = 4


# =====================================================================
# Functional / integration tests  (tests 01-22)
# =====================================================================
# These tests walk through the normal flow of TigerTA from the
# database layer's point of view. They cover the full lifecycle of
# a TA (add, edit, clock in, match, end session, clock out, remove),
# the full lifecycle of a student (enqueue, find place in line,
# match, end session), and the admin operations sitting on top of
# them. They also pin down the trickier matching rules: the merged
# COS 217 / 226 queue, 2XX overflow into 126, and 2XX TAs preferring
# 2XX students when both are available. Together they show that the
# core data flow of the app behaves the way the rest of the site
# assumes it does.
# =====================================================================


class ManyToManyTigerTATests(unittest.TestCase):
    """Tests for the database layer."""

    @classmethod
    def setUpClass(cls):
        _cleanup_test_rows()

    @classmethod
    def tearDownClass(cls):
        _cleanup_test_rows()

    def setUp(self):
        _cleanup_test_rows()
        # Skip if a real student is in the queue, since match() looks
        # at the entire queue and could pull them into a test session.
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM session "
                    "WHERE student_netid NOT LIKE %s",
                    (f'{TEST_PREFIX}%',))
                live = cur.fetchone()[0]
                if live > 0:
                    self.skipTest(
                        f'{live} non-test session(s) in queue.')

    def _populate_tas(self):
        """Add TA_LINEUP_126 + TA_LINEUP_2XX TAs."""
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
        """Enqueue students. Returns (netid, course) pairs in order."""
        order = []
        idx = 1
        # Interleave courses so the queue order isn't sorted by course.
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

    def test_01_add_many_tas(self):
        """Adding many TAs produces the right count and course links."""
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
        """Enqueued students appear in the queue in insertion order."""
        order = self._populate_students()

        queue = database.get_queue_students()
        queue = [q for q in queue
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), len(order))

        for i, q in enumerate(queue, start=1):
            self.assertEqual(q['queue_number'], i)

        for (sid, _course), q in zip(order, queue):
            self.assertEqual(q['student_netid'], sid)

    def test_03_find_student_place_per_course(self):
        """find_student_place is per-course, with 226 and 217 sharing
        one combined 2XX queue."""
        self._populate_students()

        QUEUE_OF = {
            'COS 126': ('COS 126',),
            'COS 226': ('COS 226', 'COS 217'),
            'COS 217': ('COS 226', 'COS 217'),
        }

        def _expected_place(course, sid):
            """Compute sid's expected place by reading the session
            table directly."""
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
        """student_already_in_queue distinguishes the 3 states."""
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
        """A 126 TA never matches a 226/217 student."""
        self._populate_tas()
        self._populate_students(n_126=0, n_226=3, n_217=2)

        ta_netid = _ta_id(1)
        result = database.match(ta_netid)
        self.assertIsNone(result)

    def test_06_2xx_ta_overflow_helps_126(self):
        """A 2XX TA picks up a 126 student when no 2XX students are
        queued."""
        self._populate_tas()
        self._populate_students(n_126=3, n_226=0, n_217=0)

        ta_netid = _ta_id(TA_LINEUP_126 + 1)

        self.assertTrue(database.detect_overflow())

        session_id = database.match(ta_netid)
        self.assertIsNotNone(session_id)

        info = database.get_session_info_ta(ta_netid)
        self.assertIsNotNone(info)
        self.assertEqual(info['course'], 'COS 126')

    def test_07_2xx_ta_prefers_2xx_when_available(self):
        """A 2XX TA picks a 2XX student first, even if 126 students
        joined the queue earlier."""
        self._populate_tas()
        # 5 126 students first, then 2 226 students.
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

        ta_netid = _ta_id(TA_LINEUP_126 + 1)
        self.assertFalse(database.detect_overflow())

        database.match(ta_netid)
        info = database.get_session_info_ta(ta_netid)
        self.assertEqual(info['course'], 'COS 226')

    def test_08_full_match_cycle_many_to_many(self):
        """Many TAs match many students, all sessions end cleanly."""
        self._populate_tas()
        order = self._populate_students()

        matched_ta_count = 0
        for i in range(1, TA_LINEUP_126 + 1):
            session_id = database.match(_ta_id(i))
            if session_id is not None:
                matched_ta_count += 1

        self.assertEqual(matched_ta_count, TA_LINEUP_126)

        remaining = [q for q in database.get_queue_students()
                     if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(remaining), len(order) - matched_ta_count)

        active = [s for s in database.get_active_sessions()
                  if s['ta_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(active), matched_ta_count)

        for session in active:
            database.remove_session(session['student_netid'])

        active = [s for s in database.get_active_sessions()
                  if s['ta_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(active), 0)

    def test_09_clock_in_clock_out_lifecycle(self):
        """Clock-in flips clocked_in to True; clock-out flips it back."""
        self._populate_tas()
        ta_netid = _ta_id(1)

        self.assertFalse(database.check_if_clocked_in(ta_netid))
        database.clock_in(ta_netid)
        self.assertTrue(database.check_if_clocked_in(ta_netid))
        database.clock_out(ta_netid)
        self.assertFalse(database.check_if_clocked_in(ta_netid))

    def test_10_get_num_on_shift_tas_per_course(self):
        """Counts of clocked-in TAs are scoped per course.
        Uses baselines so the test works against a shared DB that
        may already have real TAs clocked in."""
        base_126 = database.get_num_on_shift_tas('COS 126')
        base_2xx = database.get_num_on_shift_tas('COS 2XX')

        self._populate_tas()

        for i in range(1, 4):
            database.clock_in(_ta_id(i))
        for i in range(TA_LINEUP_126 + 1, TA_LINEUP_126 + 3):
            database.clock_in(_ta_id(i))

        self.assertEqual(
            database.get_num_on_shift_tas('COS 126'), base_126 + 3)
        self.assertEqual(
            database.get_num_on_shift_tas('COS 2XX'), base_2xx + 2)

    def test_11_remove_ta_cleans_up_courses(self):
        """remove_ta deletes the TA and their ta_courses rows."""
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
        """edit_ta updates the TA's name and replaces their course."""
        self._populate_tas()
        target = _ta_id(1)

        database.edit_ta(
            target, 'New Name',
            f'{target}@princeton.edu', 'COS 2XX')

        all_tas = {t['ta_netid']: t for t in database.get_all_tas()}
        self.assertEqual(all_tas[target]['ta_name'], 'New Name')
        self.assertEqual(
            all_tas[target]['courses'], 'COS 2XX')

    def test_13_update_num_students_helped(self):
        """update_num_students_helped increments the shift counter."""
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
        """validate_ta returns True for known TAs and False otherwise."""
        self._populate_tas()

        self.assertTrue(database.validate_ta(_ta_id(1)))
        self.assertFalse(database.validate_ta('nottrue1'))

    def test_15_get_session_info_student_and_ta_name(self):
        """After matching, get_session_info_student returns the right
        course/bug/session_id and get_session_ta_name returns the TA's
        name."""
        self._populate_tas()
        self._populate_students(n_126=1, n_226=0, n_217=0)
        ta_netid = _ta_id(1)
        student_netid = _student_id(1)

        # Pre-match: no TA name yet.
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
        """notify_next_in_line sets the notified_next flag on the
        front-of-line student."""
        self._populate_students(n_126=2, n_226=0, n_217=0)
        front = _student_id(1)

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

        # Already notified -- should be a no-op.
        database.notify_next_in_line('COS 126')
        # Empty queue -- should not raise.
        database.notify_next_in_line('COS 126 NONEXISTENT')

    def test_17_set_available_flips_flag(self):
        """set_available flips the TA's available flag back to TRUE."""
        self._populate_tas()
        ta_netid = _ta_id(1)

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
        """time_session_began is set after a match; bogus id returns None."""
        self._populate_tas()
        self._populate_students(n_126=1, n_226=0, n_217=0)
        session_id = database.match(_ta_id(1))
        self.assertIsNotNone(session_id)

        ts = database.get_time_session_began(session_id)
        self.assertIsNotNone(ts)

        self.assertIsNone(database.get_time_session_began(-1))

    def test_19_student_already_in_queue_in_session_state(self):
        """student_already_in_queue returns 'InSession' after match."""
        self._populate_tas()
        self._populate_students(n_126=1, n_226=0, n_217=0)
        student_netid = _student_id(1)

        self.assertEqual(
            database.student_already_in_queue(student_netid), 'InQueue')

        database.match(_ta_id(1))

        self.assertEqual(
            database.student_already_in_queue(student_netid), 'InSession')

    def test_20_validate_admin(self):
        """validate_admin returns True for admin rows and False for
        unknown netids."""
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
        """match() returns None when the queue is empty."""
        self._populate_tas()
        self.assertIsNone(database.match(_ta_id(1)))
        self.assertIsNone(database.match(_ta_id(TA_LINEUP_126 + 1)))

    def test_22_get_num_on_shift_tas_normalises_2xx(self):
        """get_num_on_shift_tas treats 'COS 226' and 'COS 217' as
        'COS 2XX'."""
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

    # =================================================================
    # Database-layer coverage tests  (tests 23-32)
    # =================================================================
    # These tests aim every defensive branch in database.py at a
    # bad input: unknown netIDs, courses TigerTA doesn't support,
    # students who aren't queued, TAs who aren't clocked in, and
    # rows that don't exist. Instead of checking the happy path,
    # they make sure the database returns False / None / an empty
    # result and leaves state untouched, so a malformed request can
    # never crash a route or corrupt the queue.
    # =================================================================

    def test_23_queue_entry_rejects_invalid_course(self):
        """queue_entry returns False for an unknown course."""
        ok = database.queue_entry({
            'student_netid': _student_id(1),
            'student_name': 'Bad Course',
            'course': 'COS 999',
            'assignment': 'a1',
            'bug_description': 'x',
        })
        self.assertFalse(ok)

        queue = [q for q in database.get_queue_students()
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), 0)

    def test_24_match_returns_none_for_unknown_ta(self):
        """match() returns None for an unknown ta_netid."""
        self.assertIsNone(database.match(f'{TEST_PREFIX}nope1'))

    def test_25_add_ta_rejects_invalid_course(self):
        """add_ta returns False and inserts nothing for an invalid course."""
        ok = database.add_ta(
            f'{TEST_PREFIX}badc1', 'Bad Course TA',
            f'{TEST_PREFIX}badc1@princeton.edu', 'COS 999')
        self.assertFalse(ok)

        all_tas = database.get_all_tas()
        self.assertNotIn(
            f'{TEST_PREFIX}badc1',
            [t['ta_netid'] for t in all_tas])

    def test_26_clock_in_returns_false_for_unknown_ta(self):
        """clock_in returns False for an unknown TA."""
        self.assertFalse(database.clock_in(f'{TEST_PREFIX}nope2'))

    def test_27_clock_out_returns_false_for_unknown_ta(self):
        """clock_out returns False for an unknown TA."""
        self.assertFalse(database.clock_out(f'{TEST_PREFIX}nope3'))

    def test_28_clock_out_deletes_shift_when_log_succeeds(self):
        """When log_shift returns True, clock_out deletes the shift row."""
        self._populate_tas()
        ta_netid = _ta_id(1)
        database.clock_in(ta_netid)

        # Patch log_shift to return True for this test only.
        original = googlesheet.log_shift
        googlesheet.log_shift = lambda *a, **kw: True
        try:
            self.assertTrue(database.clock_out(ta_netid))
        finally:
            googlesheet.log_shift = original

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM shifts WHERE ta_netid = %s",
                    (ta_netid,))
                self.assertEqual(cur.fetchone()[0], 0)

    def test_29_get_session_info_student_returns_none_for_unknown(self):
        """get_session_info_student returns None for an unknown student."""
        self.assertIsNone(
            database.get_session_info_student(f'{TEST_PREFIX}nope4'))

    def test_30_get_session_ta_name_pre_match_returns_none(self):
        """get_session_ta_name returns None for a queued, unmatched student."""
        sid = _student_id(1)
        database.queue_entry({
            'student_netid': sid, 'student_name': 'Solo',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': '.',
        })
        self.assertIsNone(database.get_session_ta_name(sid))

    def test_31_remove_session_returns_false_for_unknown_student(self):
        """remove_session returns False when nothing was deleted."""
        self.assertFalse(database.remove_session(f'{TEST_PREFIX}nope5'))

    def test_32_remove_ta_returns_false_for_unknown_ta(self):
        """remove_ta returns False when nothing was deleted."""
        self.assertFalse(database.remove_ta(f'{TEST_PREFIX}nope6'))


# =====================================================================
# Stress tests  (3 tests)
# =====================================================================
# These tests push the database layer past the volume and timing
# patterns the functional tests use, to surface any bug that only
# shows up under load.
#   * High-volume drain: 18 TAs working through a queue of ~125
#     students. Confirms that with many rounds of matches and session
#     teardowns the queue still drains completely, no student is
#     matched twice, and the totals add up.
#   * Concurrent match: 15 TAs all call match() at the same moment.
#     Catches race conditions where two TAs could otherwise grab the
#     same student or one TA could end up in two active sessions.
#   * Concurrent enqueue: 40 students hit queue_entry() in parallel.
#     Verifies every insert lands, session IDs stay unique, and the
#     queue numbers come out as a contiguous 1..N.
# =====================================================================

STRESS_TA_126 = 10
STRESS_TA_2XX = 8
STRESS_STUDENTS_126 = 60
STRESS_STUDENTS_226 = 40
STRESS_STUDENTS_217 = 25

CONCURRENT_TAS = 15
CONCURRENT_STUDENTS = 30
CONCURRENT_ENQUEUE = 40


class StressTigerTATests(unittest.TestCase):
    """High-volume and concurrent tests for the database layer."""

    @classmethod
    def setUpClass(cls):
        _cleanup_test_rows()

    @classmethod
    def tearDownClass(cls):
        _cleanup_test_rows()

    def setUp(self):
        _cleanup_test_rows()
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM session "
                    "WHERE student_netid NOT LIKE %s",
                    (f'{TEST_PREFIX}%',))
                live = cur.fetchone()[0]
                if live > 0:
                    self.skipTest(
                        f'{live} non-test session(s) in queue.')

    def _populate_stress_tas(self):
        """Add STRESS_TA_126 + STRESS_TA_2XX TAs."""
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
        """Enqueue (n_126 + n_226 + n_217) students, interleaved."""
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
        return idx - 1

    def test_stress_01_high_volume_drain(self):
        """Enqueue many students, repeatedly match TAs until the queue
        is empty, and check that every student was matched exactly once."""

        t0 = time.monotonic()
        self._populate_stress_tas()
        total_enqueued = self._populate_stress_students(
            STRESS_STUDENTS_126,
            STRESS_STUDENTS_226,
            STRESS_STUDENTS_217)
        enqueue_elapsed = time.monotonic() - t0

        queue = [q for q in database.get_queue_students()
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), total_enqueued)

        # Loop: each round, every TA tries to match. Stop when no TA
        # matched (some 126-only TAs may end up idle).
        all_session_ids = []
        all_student_netids = []
        rounds = 0
        while True:
            rounds += 1
            matched_this_round = 0
            for i in range(1, STRESS_TA_126 + STRESS_TA_2XX + 1):
                ta_netid = _ta_id(i)
                database.set_available(ta_netid)
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
            self.assertLess(rounds, 100)

        for i in range(1, STRESS_TA_126 + STRESS_TA_2XX + 1):
            ta_netid = _ta_id(i)
            info = database.get_session_info_ta(ta_netid)
            if info is not None and info.get('student_netid') is not None:
                database.remove_session(info['student_netid'])

        elapsed = time.monotonic() - t0

        self.assertEqual(
            len(all_student_netids), len(set(all_student_netids)),
            'a student was matched to two TAs')

        self.assertEqual(
            len(all_student_netids), total_enqueued,
            f'enqueued {total_enqueued} but matched '
            f'{len(all_student_netids)}')

        leftover = [q for q in database.get_queue_students()
                    if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(leftover), 0)

        print(
            f'\n[stress_01 timing] enqueue {total_enqueued} students: '
            f'{enqueue_elapsed:.1f}s | drain + cleanup: '
            f'{elapsed:.1f}s')

    def test_stress_02_concurrent_match_no_double_assignment(self):
        """Many TAs call match() at the same time. No student should
        be assigned to two TAs."""

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

        ta_netids = [_ta_id(i) for i in range(1, CONCURRENT_TAS + 1)]
        results = []
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=CONCURRENT_TAS) as pool:
            futures = [pool.submit(database.match, n) for n in ta_netids]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # No student or TA should appear in two active sessions.
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
            len(active_students), len(set(active_students)))
        self.assertEqual(len(active_tas), len(set(active_tas)))

        # Active sessions can't exceed min(TAs, students).
        self.assertLessEqual(
            len(active),
            min(CONCURRENT_TAS, CONCURRENT_STUDENTS))

        # match() should return unique session_ids.
        successful = [r for r in results if r is not None]
        self.assertEqual(len(successful), len(set(successful)))

    def test_stress_03_concurrent_enqueue(self):
        """Many students enqueue at once. All land in the queue with
        unique session_ids and contiguous 1..N queue numbers."""

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

        queue = [q for q in database.get_queue_students()
                 if q['student_netid'].startswith(TEST_PREFIX)]
        self.assertEqual(len(queue), CONCURRENT_ENQUEUE)

        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT session_id, student_netid FROM session "
                    "WHERE student_netid LIKE %s",
                    (f'{TEST_PREFIX}%',))
                rows = cur.fetchall()

        session_ids = [r[0] for r in rows]
        student_netids = [r[1] for r in rows]
        self.assertEqual(len(session_ids), len(set(session_ids)))
        self.assertEqual(len(student_netids), len(set(student_netids)))

        nums = sorted(q['queue_number'] for q in queue)
        self.assertEqual(nums, list(range(1, CONCURRENT_ENQUEUE + 1)))


# =====================================================================
# Flask route tests  (47 tests)
# =====================================================================
# These tests drive TigerTA through Flask's test client, hitting the
# real route handlers in student.py, ta.py, and admin.py. Every
# user-facing workflow is covered end-to-end:
#   * Student: home page, role selection, joining the queue,
#     polling for a match, entering a session, leaving the queue,
#     submitting feedback, and ending the session.
#   * TA: work hub, clock in / clock out, starting a session,
#     in-session view, and ending a session.
#   * Admin: admin page, adding / editing / removing TAs, including
#     each error redirect (?error=ta_not_added, etc.).
# Both the success paths and the error-redirect branches are
# exercised, so a regression in any handler shows up here before it
# reaches a real user.
#
# CAS auth is bypassed by writing a username straight into the
# session, CSRF is disabled, and every request uses a base_url with
# a port so the before_request HTTP->HTTPS redirect doesn't fire.
# =====================================================================

import app as _app_module
_flask_app = _app_module.app
_flask_app.config['TESTING'] = True
_flask_app.config['WTF_CSRF_ENABLED'] = False
if not _flask_app.secret_key:
    _flask_app.secret_key = 'test-secret-key-for-route-tests'

_TEST_BASE_URL = 'http://localhost:5000'


class RouteTests(unittest.TestCase):
    """Tests for the Flask route handlers."""

    @classmethod
    def setUpClass(cls):
        _cleanup_test_rows()

    @classmethod
    def tearDownClass(cls):
        _cleanup_test_rows()

    def setUp(self):
        _cleanup_test_rows()
        self.client = _flask_app.test_client()
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM session "
                    "WHERE student_netid NOT LIKE %s",
                    (f'{TEST_PREFIX}%',))
                live = cur.fetchone()[0]
                if live > 0:
                    self.skipTest(
                        f'{live} non-test session(s) in queue.')

    def _login_as(self, netid):
        """Set the session username (skip CAS)."""
        with self.client.session_transaction() as sess:
            sess['username'] = netid

    def _get(self, path, **kwargs):
        return self.client.get(
            path, base_url=_TEST_BASE_URL, **kwargs)

    def _post(self, path, **kwargs):
        return self.client.post(
            path, base_url=_TEST_BASE_URL, **kwargs)

    def test_route_01_homepage_returns_200(self):
        """GET / and GET /home render the homepage."""
        for path in ('/', '/home'):
            r = self._get(path)
            self.assertEqual(r.status_code, 200, f'{path} not 200')

    def test_route_02_roleselection_get_renders(self):
        """GET /roleselection renders for a logged-in user."""
        self._login_as(f'{TEST_PREFIX}stu1')
        r = self._get('/roleselection')
        self.assertEqual(r.status_code, 200)

    def test_route_03_roleselection_post_student_redirects_to_queueentry(self):
        """Picking 'student' redirects to /queueentry."""
        self._login_as(f'{TEST_PREFIX}stu2')
        r = self._post('/roleselection', data={'role': 'Student'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/queueentry', r.headers['Location'])

    def test_route_04_roleselection_post_ta_for_non_ta_redirects_with_error(self):
        """A non-TA picking 'TA' is redirected with error=not_ta."""
        self._login_as(f'{TEST_PREFIX}stu3')
        r = self._post('/roleselection', data={'role': 'TA'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=not_ta', r.headers['Location'])

    def test_route_05_roleselection_post_admin_for_non_admin_redirects_with_error(self):
        """A non-admin picking 'Admin' is redirected with error=not_admin."""
        self._login_as(f'{TEST_PREFIX}stu4')
        r = self._post('/roleselection', data={'role': 'Admin'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=not_admin', r.headers['Location'])

    def test_route_06_queueentry_get_renders(self):
        """GET /queueentry renders the form."""
        self._login_as(f'{TEST_PREFIX}stu5')
        r = self._get('/queueentry')
        self.assertEqual(r.status_code, 200)

    def test_route_07_queueentry_post_inserts_into_queue(self):
        """A valid /queueentry POST adds the student and redirects
        to /queuestatus."""
        netid = f'{TEST_PREFIX}stu6'
        self._login_as(netid)
        r = self._post('/queueentry', data={
            'student_name': 'Route Student',
            'course': 'COS 126',
            'assignment': 'a1',
            'bug_description': 'route test',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/queuestatus', r.headers['Location'])
        queue = [q for q in database.get_queue_students()
                 if q['student_netid'] == netid]
        self.assertEqual(len(queue), 1)

    def test_route_08_queuestatus_redirects_to_queueentry_when_no_session(self):
        """A student with no session is sent from /queuestatus to /queueentry."""
        self._login_as(f'{TEST_PREFIX}stu7')
        r = self._get('/queuestatus')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/queueentry', r.headers['Location'])

    def test_route_09_trymatch_returns_json_for_unknown_student(self):
        """/trymatch returns the expected JSON for an unknown student."""
        self._login_as(f'{TEST_PREFIX}stu8')
        r = self._get('/trymatch')
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn('matched', body)
        self.assertEqual(body['in_database'], False)

    def test_route_10_insessionstudent_redirects_when_no_session(self):
        """A student with no session is sent from /insessionstudent to
        /endsessionstudent."""
        self._login_as(f'{TEST_PREFIX}stu9')
        r = self._get('/insessionstudent')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/endsessionstudent', r.headers['Location'])

    def test_route_11_endsessionstudent_get_renders(self):
        """GET /endsessionstudent renders without state."""
        r = self._get('/endsessionstudent')
        self.assertEqual(r.status_code, 200)

    def test_route_12_submit_feedback_logs_and_redirects(self):
        """POST /submitfeedback redirects to /endsessionstudent."""
        r = self._post('/submitfeedback', data={
            'rating': '5',
            'feedback_text': 'Great help!',
            'ta_name': 'TA One',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/endsessionstudent', r.headers['Location'])

    def test_route_13_workhub_get_renders_for_ta(self):
        """A clocked-out TA gets the /workhub page."""
        ta_netid = f'{TEST_PREFIX}ta01'
        database.add_ta(
            ta_netid, 'Work Hub TA',
            f'{ta_netid}@princeton.edu', 'COS 126')
        self._login_as(ta_netid)
        r = self._get('/workhub')
        self.assertEqual(r.status_code, 200)

    def test_route_14_workhub_post_clock_in_succeeds(self):
        """POST clock_in for a real TA succeeds."""
        ta_netid = f'{TEST_PREFIX}ta02'
        database.add_ta(
            ta_netid, 'Clocker',
            f'{ta_netid}@princeton.edu', 'COS 126')
        self._login_as(ta_netid)
        r = self._post('/workhub', data={'action': 'clock_in'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/workhub', r.headers['Location'])
        self.assertTrue(database.check_if_clocked_in(ta_netid))

    def test_route_15_workhub_post_clock_in_for_unknown_ta_redirects_with_error(self):
        """POST clock_in for an unknown TA returns error=not_clocked_in."""
        self._login_as(f'{TEST_PREFIX}nope9')
        r = self._post('/workhub', data={'action': 'clock_in'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=not_clocked_in', r.headers['Location'])

    def test_route_16_workhub_status_returns_json(self):
        """/workhub_status returns the expected JSON keys."""
        self._login_as(f'{TEST_PREFIX}ta03')
        r = self._get('/workhub_status')
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn('matched', body)
        self.assertIn('queue_students', body)
        self.assertIn('active_sessions', body)

    def test_route_17_insessionta_redirects_when_no_session(self):
        """A TA with no session is sent from /insessionta to /workhub."""
        self._login_as(f'{TEST_PREFIX}ta04')
        r = self._get('/insessionta')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/workhub', r.headers['Location'])

    def test_route_18_endsessionta_get_renders(self):
        """GET /endsessionta renders without the student_name cookie."""
        self._login_as(f'{TEST_PREFIX}ta05')
        r = self._get('/endsessionta')
        self.assertEqual(r.status_code, 200)

    def test_route_19_adminpage_renders(self):
        """GET /adminpage renders with the TA list."""
        r = self._get('/adminpage')
        self.assertEqual(r.status_code, 200)

    def test_route_20_add_ta_post_succeeds(self):
        """POST /add_ta inserts the TA and redirects to /adminpage."""
        ta_netid = f'{TEST_PREFIX}ta06'
        r = self._post('/add_ta', data={
            'ta_net_id': ta_netid,
            'ta_name': 'Added Via Route',
            'course': 'COS 126',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/adminpage', r.headers['Location'])
        self.assertTrue(database.validate_ta(ta_netid))

    def test_route_21_add_ta_post_invalid_course_redirects_with_error(self):
        """POST /add_ta with an invalid course returns error=ta_not_added."""
        ta_netid = f'{TEST_PREFIX}ta07'
        r = self._post('/add_ta', data={
            'ta_net_id': ta_netid,
            'ta_name': 'Bad Course',
            'course': 'COS 999',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=ta_not_added', r.headers['Location'])

    def test_route_22_remove_ta_post_succeeds(self):
        """POST /remove_ta deletes the TA and redirects to /adminpage."""
        ta_netid = f'{TEST_PREFIX}ta08'
        database.add_ta(
            ta_netid, 'Removable',
            f'{ta_netid}@princeton.edu', 'COS 126')
        r = self._post('/remove_ta', data={'ta_net_id': ta_netid})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/adminpage', r.headers['Location'])
        self.assertFalse(database.validate_ta(ta_netid))

    def test_route_23_remove_ta_post_for_unknown_ta_redirects_with_error(self):
        """POST /remove_ta for an unknown TA returns error=ta_not_removed."""
        r = self._post('/remove_ta', data={
            'ta_net_id': f'{TEST_PREFIX}nope10',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=ta_not_removed', r.headers['Location'])

    def test_route_24_edit_ta_post_updates_and_redirects(self):
        """POST /edit_ta updates the TA and redirects to /adminpage."""
        ta_netid = f'{TEST_PREFIX}ta09'
        database.add_ta(
            ta_netid, 'Old Name',
            f'{ta_netid}@princeton.edu', 'COS 126')
        r = self._post('/edit_ta', data={
            'ta_netid': ta_netid,
            'ta_name': 'New Name',
            'ta_email': f'{ta_netid}@princeton.edu',
            'ta_courses': 'COS 2XX',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/adminpage', r.headers['Location'])
        all_tas = {t['ta_netid']: t for t in database.get_all_tas()}
        self.assertEqual(all_tas[ta_netid]['ta_name'], 'New Name')
        self.assertEqual(all_tas[ta_netid]['courses'], 'COS 2XX')

    def _setup_matched(self, ta_netid, student_netid, course='COS 126'):
        """Add a TA, enqueue a student, match them. Returns session_id."""
        database.add_ta(
            ta_netid, f'TA {ta_netid}',
            f'{ta_netid}@princeton.edu', course)
        database.queue_entry({
            'student_netid': student_netid,
            'student_name': f'Student {student_netid}',
            'course': course,
            'assignment': 'a1',
            'bug_description': f'help with {course}',
        })
        return database.match(ta_netid)

    def test_route_25_logout_clears_session_and_redirects(self):
        """/logout clears the session and redirects."""
        netid = f'{TEST_PREFIX}stu10'
        self._login_as(netid)
        r = self._get('/logout')
        self.assertEqual(r.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn('username', sess)

    def test_route_26_roleselection_post_ta_for_real_ta(self):
        """A real TA picking 'TA' is redirected to /workhub."""
        netid = f'{TEST_PREFIX}ta10'
        database.add_ta(
            netid, 'Real TA',
            f'{netid}@princeton.edu', 'COS 126')
        self._login_as(netid)
        r = self._post('/roleselection', data={'role': 'TA'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/workhub', r.headers['Location'])

    def test_route_27_roleselection_post_admin_for_real_admin(self):
        """A real admin picking 'Admin' is redirected to /adminpage."""
        netid = f'{TEST_PREFIX}adm2'
        with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(
                    "INSERT INTO admin (admin_netid) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (netid,))
                conn.commit()
        try:
            self._login_as(netid)
            r = self._post('/roleselection', data={'role': 'Admin'})
            self.assertEqual(r.status_code, 302)
            self.assertIn('/adminpage', r.headers['Location'])
        finally:
            with contextlib.closing(psycopg.connect(DATABASE_URL)) as conn:
                with contextlib.closing(conn.cursor()) as cur:
                    cur.execute(
                        "DELETE FROM admin WHERE admin_netid = %s",
                        (netid,))
                    conn.commit()

    def test_route_28_roleselection_post_student_already_in_queue(self):
        """A student already in the queue who picks 'Student' is
        redirected to /queuestatus."""
        netid = f'{TEST_PREFIX}stu11'
        database.queue_entry({
            'student_netid': netid, 'student_name': 'In Queue',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': '.',
        })
        self._login_as(netid)
        r = self._post('/roleselection', data={'role': 'Student'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/queuestatus', r.headers['Location'])

    def test_route_29_roleselection_post_student_in_session(self):
        """A student already in a session who picks 'Student' is
        redirected to /insessionstudent."""
        ta_netid = f'{TEST_PREFIX}ta11'
        student_netid = f'{TEST_PREFIX}stu12'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(student_netid)
        r = self._post('/roleselection', data={'role': 'Student'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/insessionstudent', r.headers['Location'])

    def test_route_30_queueentry_post_when_already_in_queue(self):
        """POST /queueentry while already queued returns
        error=already_in_queue."""
        netid = f'{TEST_PREFIX}stu13'
        database.queue_entry({
            'student_netid': netid, 'student_name': 'In Queue',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': '.',
        })
        self._login_as(netid)
        r = self._post('/queueentry', data={
            'student_name': 'x', 'course': 'COS 126',
            'assignment': 'a1', 'bug_description': 'y',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=already_in_queue', r.headers['Location'])

    def test_route_31_queueentry_post_when_already_in_session(self):
        """POST /queueentry while already in a session returns
        error=already_in_session."""
        ta_netid = f'{TEST_PREFIX}ta12'
        student_netid = f'{TEST_PREFIX}stu14'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(student_netid)
        r = self._post('/queueentry', data={
            'student_name': 'x', 'course': 'COS 126',
            'assignment': 'a1', 'bug_description': 'y',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=already_in_session', r.headers['Location'])

    def test_route_32_queueentry_post_insert_fails_for_invalid_course(self):
        """POST /queueentry with an invalid course returns
        error=not_added_to_queue."""
        self._login_as(f'{TEST_PREFIX}stu15')
        r = self._post('/queueentry', data={
            'student_name': 'Bad', 'course': 'COS 999',
            'assignment': 'a1', 'bug_description': '.',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=not_added_to_queue', r.headers['Location'])

    def test_route_33_queuestatus_renders_for_in_queue_student(self):
        """A queued, unmatched student renders /queuestatus."""
        netid = f'{TEST_PREFIX}stu16'
        database.queue_entry({
            'student_netid': netid, 'student_name': 'Queued',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': 'help me',
        })
        self._login_as(netid)
        r = self._get('/queuestatus')
        self.assertEqual(r.status_code, 200)

    def test_route_34_queuestatus_post_leave_queue(self):
        """POST leave_queue removes the student and redirects to /queueentry."""
        netid = f'{TEST_PREFIX}stu17'
        database.queue_entry({
            'student_netid': netid, 'student_name': 'Quitter',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': '.',
        })
        self._login_as(netid)
        r = self._post('/queuestatus', data={'action': 'leave_queue'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/queueentry', r.headers['Location'])
        queue = [q for q in database.get_queue_students()
                 if q['student_netid'] == netid]
        self.assertEqual(len(queue), 0)

    def test_route_35_queuestatus_redirects_to_insessionstudent_when_matched(self):
        """A matched student is sent from /queuestatus to /insessionstudent."""
        ta_netid = f'{TEST_PREFIX}ta13'
        student_netid = f'{TEST_PREFIX}stu18'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(student_netid)
        r = self._get('/queuestatus')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/insessionstudent', r.headers['Location'])

    def test_route_36_trymatch_returns_in_database_true_for_queued_student(self):
        """/trymatch returns in_database=True for a queued student."""
        netid = f'{TEST_PREFIX}stu19'
        database.queue_entry({
            'student_netid': netid, 'student_name': 'Polling',
            'course': 'COS 126', 'assignment': 'a1',
            'bug_description': '.',
        })
        self._login_as(netid)
        r = self._get('/trymatch')
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body['in_database'], True)
        self.assertEqual(body['matched'], False)
        self.assertGreaterEqual(body['student_place'], 1)

    def test_route_37_insessionstudent_renders_when_matched(self):
        """A matched student renders /insessionstudent."""
        ta_netid = f'{TEST_PREFIX}ta14'
        student_netid = f'{TEST_PREFIX}stu20'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(student_netid)
        r = self._get('/insessionstudent')
        self.assertEqual(r.status_code, 200)

    def test_route_38_endsessionstudent_post_home_redirects(self):
        """POST endsessionstudent action=home redirects to /queueentry."""
        r = self._post('/endsessionstudent', data={'action': 'home'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/queueentry', r.headers['Location'])

    def test_route_39_workhub_redirects_to_homepage_when_no_user(self):
        """GET /workhub with no logged-in user redirects to /."""
        r = self._get('/workhub')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers['Location'].endswith('/'))

    def test_route_40_workhub_post_clock_out_succeeds(self):
        """POST clock_out succeeds when log_shift returns True."""
        ta_netid = f'{TEST_PREFIX}ta15'
        database.add_ta(
            ta_netid, 'Clock Out TA',
            f'{ta_netid}@princeton.edu', 'COS 126')
        database.clock_in(ta_netid)
        original = googlesheet.log_shift
        googlesheet.log_shift = lambda *a, **kw: True
        try:
            self._login_as(ta_netid)
            r = self._post('/workhub', data={'action': 'clock_out'})
        finally:
            googlesheet.log_shift = original
        self.assertEqual(r.status_code, 302)
        self.assertIn('/workhub', r.headers['Location'])
        self.assertNotIn('error', r.headers['Location'])

    def test_route_41_workhub_post_clock_out_fails(self):
        """POST clock_out for a TA who isn't clocked in returns
        error=not_clocked_out."""
        ta_netid = f'{TEST_PREFIX}ta16'
        database.add_ta(
            ta_netid, 'Never Clocked In',
            f'{ta_netid}@princeton.edu', 'COS 126')
        self._login_as(ta_netid)
        r = self._post('/workhub', data={'action': 'clock_out'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=not_clocked_out', r.headers['Location'])

    def test_route_42_workhub_post_start_session_with_match(self):
        """POST start_session matches the TA and redirects to /insessionta."""
        ta_netid = f'{TEST_PREFIX}ta17'
        student_netid = f'{TEST_PREFIX}stu21'
        database.add_ta(
            ta_netid, 'Starter',
            f'{ta_netid}@princeton.edu', 'COS 126')
        database.queue_entry({
            'student_netid': student_netid,
            'student_name': 'Waiting', 'course': 'COS 126',
            'assignment': 'a1', 'bug_description': '.',
        })
        self._login_as(ta_netid)
        r = self._post('/workhub', data={'action': 'start_session'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/insessionta', r.headers['Location'])

    def test_route_43_workhub_post_start_session_no_match(self):
        """POST start_session with an empty queue stays at /workhub."""
        ta_netid = f'{TEST_PREFIX}ta18'
        database.add_ta(
            ta_netid, 'No Match',
            f'{ta_netid}@princeton.edu', 'COS 126')
        self._login_as(ta_netid)
        r = self._post('/workhub', data={'action': 'start_session'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/workhub', r.headers['Location'])
        self.assertNotIn('/insessionta', r.headers['Location'])

    def test_route_44_workhub_redirects_to_insessionta_when_matched(self):
        """A TA in an active session is sent from /workhub to /insessionta."""
        ta_netid = f'{TEST_PREFIX}ta19'
        student_netid = f'{TEST_PREFIX}stu22'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(ta_netid)
        r = self._get('/workhub')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/insessionta', r.headers['Location'])

    def test_route_45_insessionta_renders_when_matched(self):
        """A matched TA renders /insessionta."""
        ta_netid = f'{TEST_PREFIX}ta20'
        student_netid = f'{TEST_PREFIX}stu23'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(ta_netid)
        r = self._get('/insessionta')
        self.assertEqual(r.status_code, 200)

    def test_route_46_insessionta_post_end_session(self):
        """POST end_session removes the session and redirects to /endsessionta."""
        ta_netid = f'{TEST_PREFIX}ta21'
        student_netid = f'{TEST_PREFIX}stu24'
        self._setup_matched(ta_netid, student_netid)
        self._login_as(ta_netid)
        r = self._post('/insessionta', data={'action': 'end_session'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/endsessionta', r.headers['Location'])
        info = database.get_session_info_ta(ta_netid)
        self.assertIsNone(info)

    def test_route_47_endsessionta_post_home_redirects(self):
        """POST endsessionta action=home redirects to /workhub."""
        self._login_as(f'{TEST_PREFIX}ta22')
        r = self._post('/endsessionta', data={'action': 'home'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/workhub', r.headers['Location'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
