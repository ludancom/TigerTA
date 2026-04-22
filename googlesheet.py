import gspread

client = gspread.service_account(filename='tigerta-d62e8c569ae9.json')
sheet = client.open_by_key(key='1yT4kDQ-0aeV7Rac9R7TxEHTyS-BIPbrgayMMFtSCAt4')
worksheet = sheet.get_worksheet_by_id(id=0)

def log_shift(netid, date, clock_in, clock_out, students):
    worksheet.append_row([
        netid,
        date,
        clock_in,
        clock_out,
        students
    ])