#-----------------------------------------------------------------------
# notifications.py
#-----------------------------------------------------------------------
""" Handles email notifications for students waiting in the queue. """
import sys
from flask_mail import Mail, Message

mail = Mail()

def _princeton_email(netid):
    return f"{netid}@princeton.edu"

def send_next_in_line(student_netid, student_name, course):
    """Email a student to let them know they're next in the queue."""
    try:
        msg = Message(
            subject=f"You're next in line for {course} help!",
            recipients=[_princeton_email(student_netid)]
        )
        msg.body = (
            f"Hi {student_name},\n\n"
            f"You're next in line for {course} help through TigerTA. "
            f"A TA should be with you shortly — please stay at your "
            f"workstation and keep the app open.\n\n"
            f"— TigerTA"
        )
        mail.send(msg)
    except Exception as ex:
        print(f'send_next_in_line: {ex}', file=sys.stderr)

def send_matched(student_netid, student_name, ta_name, course):
    """Email a student to let them know they've been matched with a TA."""
    try:
        msg = Message(
            subject=f"You've been matched with a TA!",
            recipients=[_princeton_email(student_netid)]
        )
        msg.body = (
            f"Hi {student_name},\n\n"
            f"You've been matched with {ta_name} for {course} help. "
            f"They're on their way to you now.\n\n"
            f"— TigerTA"
        )
        mail.send(msg)
    except Exception as ex:
        print(f'send_matched: {ex}', file=sys.stderr)