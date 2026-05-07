#-----------------------------------------------------------------------
# notifications.py
#-----------------------------------------------------------------------
""" Handles email notifications for students waiting in the queue. """

import socket
import sys
import threading

import flask
from flask_mail import Mail, Message

mail = Mail()

# Cap the SMTP socket at 10s so a network-blocked port (e.g. Render's
# free/starter plans dropping outbound 587) cannot hang a gunicorn
# worker until SIGKILL. flask_mail constructs smtplib.SMTP() without a
# timeout argument, so we install a default at the socket layer.
_SMTP_TIMEOUT_SECONDS = 10


def _princeton_email(netid):
    return f"{netid}@princeton.edu"


def _send(msg, label):
    """ Send `msg` in a background thread so the request that triggered
    the notification (queue_entry, match, etc.) returns immediately
    instead of blocking on a 1-3 second SMTP round-trip to Gmail. We
    capture the current Flask app object up front so the worker thread
    can push its own app context for mail.send(). Errors are logged,
    not raised -- a transient SMTP failure must never crash the flow
    that triggered the notification. """
    # Capture the real app object now, while we are still inside the
    # request's app context. `current_app` is a proxy and would be
    # invalid by the time the worker thread runs.
    app = flask.current_app._get_current_object()

    def _do_send():
        print(f'{label}: sending to {msg.recipients}',
              file=sys.stderr, flush=True)
        old_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_SMTP_TIMEOUT_SECONDS)
            with app.app_context():
                mail.send(msg)
            print(f'{label}: sent OK', file=sys.stderr, flush=True)
        except Exception as ex:
            print(f'{label}: SEND FAILED: {ex!r}',
                  file=sys.stderr, flush=True)
        finally:
            socket.setdefaulttimeout(old_timeout)

    # daemon=True so worker threads don't keep the process alive at
    # shutdown; in-flight emails may be dropped on SIGTERM, which is
    # fine for transactional notifications.
    threading.Thread(target=_do_send, daemon=True).start()


def send_next_in_line(student_netid, student_name, course):
    """ Email a student to let them know they're next in the queue. """

    msg = Message(
        subject=f"[TigerTA] You're next in line for {course} help!",
        recipients=[_princeton_email(student_netid)],
    )
    msg.body = (
        f"Hi {student_name},\n\n"
        f"You're next in line for {course} help through TigerTA. "
        f"A TA should be with you shortly — please stay at your "
        f"workstation and keep the app open.\n\n"
        f"— TigerTA"
    )
    _send(msg, 'send_next_in_line')


def send_matched(student_netid, student_name, ta_name, course):
    """ Email a student to let them know they've been matched with a TA. """

    msg = Message(
        subject="[TigerTA] You've been matched with a TA!",
        recipients=[_princeton_email(student_netid)],
    )
    msg.body = (
        f"Hi {student_name},\n\n"
        f"You've been matched with {ta_name} for {course} help. "
        f"They're on their way to you now.\n\n"
        f"— TigerTA"
    )
    _send(msg, 'send_matched')
