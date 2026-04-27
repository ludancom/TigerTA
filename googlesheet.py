#-----------------------------------------------------------------------
# googlesheet.py
#-----------------------------------------------------------------------
""" Handles the sheet that stores TA shift information and student session 
feedback for Head Lab TA access. """

import gspread

client = gspread.service_account(filename='tigerta-d62e8c569ae9.json')
# Tab in sheet for shifts
sheet = client.open_by_key(key='1yT4kDQ-0aeV7Rac9R7TxEHTyS-BIPbrgayMMFtSCAt4')
shiftWorksheet = sheet.get_worksheet_by_id(id=0)

# Tab in sheet for feedback
feedbackWorksheet = sheet.get_worksheet_by_id(id=1084720156)

def log_shift(netid, name, date, clock_in, clock_out, students):
    shiftWorksheet.append_row([
        netid,
        name, 
        date,
        clock_in,
        clock_out,
        students
    ])

def log_feedback(timestamp, ta_name, rating, feedback_text):
    feedbackWorksheet.append_row([
        timestamp,
        ta_name,
        rating,
        feedback_text
    ])