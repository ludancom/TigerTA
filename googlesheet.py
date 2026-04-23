import gspread

client = gspread.service_account(filename='tigerta-d62e8c569ae9.json')
# Worksheet for shifts
shiftSheet = client.open_by_key(key='1yT4kDQ-0aeV7Rac9R7TxEHTyS-BIPbrgayMMFtSCAt4')
shiftworksheet = sheet.get_worksheet_by_id(id=0)

# Worksheet for feedback
shiftSheet = client.open_by_key(key='1yT4kDQ-0aeV7Rac9R7TxEHTyS-BIPbrgayMMFtSCAt4')
shiftworksheet = sheet.get_worksheet_by_id(id=1)

def log_shift(netid, name, date, clock_in, clock_out, students):
    worksheet.append_row([
        netid,
        name, 
        date,
        clock_in,
        clock_out,
        students
    ])

def log_feedback(netid, feedback):
    worksheet.append_row([
        netid,
        feedback
    ])
