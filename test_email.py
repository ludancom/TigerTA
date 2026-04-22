# test_email.py
# Temporary script to test email setup. Delete after confirming it works.
from app import app
import notifications

# Replace with YOUR netid so the email goes to your Princeton inbox
MY_NETID = "ak1225"

with app.app_context():
    print("Sending test email...")
    notifications.send_matched(
        student_netid=MY_NETID,
        student_name="Amber",
        ta_name="Test TA",
        course="COS 126"
    )
    print("Done. Check your Princeton inbox (and spam folder).")