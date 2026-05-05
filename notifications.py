#-----------------------------------------------------------------------
# notifications.py
#-----------------------------------------------------------------------
""" Handles email notifications for students waiting in the queue. """

import socket
import sys
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
    """ Run mail.send under a short socket timeout and emit a single
    log line on success or failure so production logs say what happened. """
    print(f'{label}: sending to {msg.recipients}', file=sys.stderr, flush=True)
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(_SMTP_TIMEOUT_SECONDS)
        mail.send(msg)
        print(f'{label}: sent OK', file=sys.stderr, flush=True)
    except Exception as ex:
        print(f'{label}: SEND FAILED: {ex!r}', file=sys.stderr, flush=True)
    finally:
        socket.setdefaulttimeout(old_timeout)


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
