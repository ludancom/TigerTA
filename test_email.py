#-----------------------------------------------------------------------
# test_email.py
#-----------------------------------------------------------------------
""" Smoke test for the Flask-Mail SMTP setup.

Sends a "next in line" email and then a "matched" email to MY_NETID's
Princeton inbox in sequence, so you can confirm SMTP is wired up
correctly without driving a real student through the queue. Useful
right after editing .env or rotating the Gmail app password.

Reads the same MAIL_* env vars as app.py:
    MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME,
    MAIL_PASSWORD, MAIL_DEFAULT_SENDER

Usage:
    python test_email.py
"""

import time

# Importing `app` triggers app.config[...] = MAIL_* and
# notifications.mail.init_app(app), which is what mail.send() needs
# to know how to talk to SMTP. We then enter app_context() so
# Flask-Mail can find the bound app inside notifications._send().
from app import app
import notifications


# Send the test emails to this netID's Princeton inbox. Change before
# running if you're not Amber.
MY_NETID = "ak1225"

# Pause between the two sends. Long enough that Gmail won't collapse
# them into a single thread, short enough that we don't lose interest.
DELAY_BETWEEN_EMAILS = 20


def main():
    with app.app_context():
        print(f"Sending 'next in line' email to {MY_NETID}@princeton.edu ...")
        notifications.send_next_in_line(
            student_netid=MY_NETID,
            student_name="Amber",
            course="COS 126",
        )

        print(f"Waiting {DELAY_BETWEEN_EMAILS}s before sending the next "
              f"email so you can confirm they arrive in order ...")
        time.sleep(DELAY_BETWEEN_EMAILS)

        print(f"Sending 'matched' email to {MY_NETID}@princeton.edu ...")
        notifications.send_matched(
            student_netid=MY_NETID,
            student_name="Amber",
            ta_name="Test TA",
            course="COS 126",
        )

        print("Done. Check your Princeton inbox (and spam folder).")


if __name__ == '__main__':
    main()
