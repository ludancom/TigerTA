#-----------------------------------------------------------------------
# notifications.py
#-----------------------------------------------------------------------
""" Handles email notifications for students waiting in the queue. """

import sys
import socket
import threading
from flask import current_app
from flask_mail import Mail, Message

mail = Mail()

# Cap how long the SMTP socket will block on connect/read. flask_mail
# constructs smtplib.SMTP() without a timeout argument, so without this
# a flaky mail server can hang a gunicorn worker until SIGKILL.
_SMTP_TIMEOUT_SECONDS = 10

def _princeton_email(netid):
    return f"{netid}@princeton.edu"

def _send_async(app, msg, label):
    """ Actually send the message on a worker thread so a slow or
    unreachable SMTP server cannot block the HTTP request. """
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(_SMTP_TIMEOUT_SECONDS)
        with app.app_context():
            mail.send(msg)
    except Exception as ex:
        print(f'{label}: {ex}', file=sys.stderr)
    finally:
        socket.setdefaulttimeout(old_timeout)

def _dispatch(msg, label):
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_send_async,
        args=(app, msg, label),
        daemon=True,
    )
    thread.start()

def send_next_in_line(student_netid, student_name, course):
    """ Email a student to let them know they're next in the queue. """

    try:
        msg = Message(
            subject=f"[TigerTA] You're next in line for {course} help!",
            recipients=[_princeton_email(student_netid)]
        )
        msg.body = (
            f"Hi {student_name},\n\n"
            f"You're next in line for {course} help through TigerTA. "
            f"A TA should be with you shortly — please stay at your "
            f"workstation and keep the app open.\n\n"
            f"— TigerTA"
        )
        _dispatch(msg, 'send_next_in_line')

    except Exception as ex:
        print(f'send_next_in_line: {ex}', file=sys.stderr)

def send_matched(student_netid, student_name, ta_name, course):
    """ Email a student to let them know they've been matched with a TA. """

    try:
        msg = Message(
            subject="[TigerTA] You've been matched with a TA!",
            recipients=[_princeton_email(student_netid)]
        )
        msg.body = (
            f"Hi {student_name},\n\n"
            f"You've been matched with {ta_name} for {course} help. "
            f"They're on their way to you now.\n\n"
            f"— TigerTA"
        )
        _dispatch(msg, 'send_matched')

    except Exception as ex:
        print(f'send_matched: {ex}', file=sys.stderr)
