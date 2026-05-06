#-----------------------------------------------------------------------
# ta.py
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """

import flask
import os
import database
import auth
import time
import threading
from flask import current_app
import notifications

def send_async(func, *args):
    from flask import current_app
    import threading, time, sys

    app = current_app._get_current_object()

    def wrapper():
        with app.app_context():
            try:
                print("ASYNC START", flush=True)
                sys.stdout.flush()

                func(*args)

                print("ASYNC DONE", flush=True)
                sys.stdout.flush()

                time.sleep(0.5)  
            except Exception:
                import traceback
                traceback.print_exc()
                sys.stdout.flush()

    threading.Thread(target=wrapper, daemon=False).start()  

#-----------------------------------------------------------------------
ta_routes = flask.Blueprint('ta_routes', __name__, template_folder='.')

#-----------------------------------------------------------------------
# Secure Https Use:
#-----------------------------------------------------------------------
@ta_routes.before_request
def before_request():
    is_running_locally = '//localhost:' in flask.request.url_root
    is_using_https = flask.request.is_secure
    if (not is_running_locally) and (not is_using_https):
        url = flask.request.url.replace('http://', 'https://', 1)
        return flask.redirect(url, code=301)
    return None

#-----------------------------------------------------------------------
# Work Hub Page:
#-----------------------------------------------------------------------
@ta_routes.route('/workhub', methods=['GET', 'POST'])
def workhub():
    """ Method that displays the work hub page for TAs and allows
    them to clock in and start a session. """

    # Get TA's netID
    ta_netid = auth.get_username()

    if not ta_netid:
        return flask.redirect('/')
    
    if flask.request.method == 'POST':
        # Get TA's button request
        action = flask.request.form.get('action')

        # If TA wants to update their clocked in status...
        if action == 'clock_in':
            # Update TA's attendance when they clock in
            clockInSuccessful = database.clock_in(ta_netid)
            if clockInSuccessful:
                # Redirect so TA can't submit twice
                return flask.redirect('/workhub')
            else:
                return flask.redirect('/workhub?error=not_clocked_in')

        if action == 'clock_out':
            # Update TA's attendance and add to google sheet when 
            # they clock out
            clockOutSuccessful = database.clock_out(ta_netid)
            if clockOutSuccessful:
                return flask.redirect('/workhub')
            else: 
                return flask.redirect('/workhub?error=not_clocked_out')

        # If TA wants to start a session...
        if action == 'start_session':
            # TA clicks button to match with next queued student
            database.set_available(ta_netid)
            session_id = database.match(ta_netid)
            if session_id is not None:
                database.update_num_students_helped(ta_netid)

                session_info = database.get_session_info_ta(ta_netid)

                if session_info:
                    student_netid = session_info['student_netid']
                    student_name = session_info['student_name']
                    course = session_info['course']
                    ta_name = database.get_session_ta_name(student_netid)

                    # matched email
                    send_async(
                        notifications.send_matched,
                        student_netid,
                        student_name,
                        ta_name,
                        course
                    )

                    # next in line email
                    next_info = database.notify_next_in_line(course)
                    if next_info:
                        send_async(notifications.send_next_in_line, *next_info)

            return flask.redirect('/workhub')

    # Check if TA was matched by seeing if session_info is able
    # to be extracted
    session_info = database.get_session_info_ta(ta_netid)
     # If TA is matched, send them to the in session page
    if session_info:
        return flask.redirect('/insessionta')

    # Button says "Clock In" if not clocked in and "Clock Out" otherwise
    clocked_in = database.check_if_clocked_in(ta_netid)

    queue_students = database.get_queue_students()
    active_sessions = database.get_active_sessions()

    return flask.render_template('workhub.html', clocked_in=clocked_in,
                                   queue_students=queue_students,
                                    active_sessions=active_sessions)

#-----------------------------------------------------------------------
# JSON Helper for Workhub:
#-----------------------------------------------------------------------
@ta_routes.route('/workhub_status', methods=['GET'])
def workhub_status():
    """ Method with JSON checker for determining 
    whether TA has been matched."""

    queue_students = database.get_queue_students()
    active_sessions = database.get_active_sessions()

    # Determine whether TA was matched
    ta_netid = auth.get_username()
    session_info = database.get_session_info_ta(ta_netid)
    matched = session_info is not None

    return flask.jsonify({
        "matched": matched,
        "queue_students": queue_students,
        "active_sessions": active_sessions
    })

#-----------------------------------------------------------------------
# In Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/insessionta', methods=['GET', 'POST'])
def insessionta():
    """ Method that displays the student that the TA was matched with 
    and their session details. """

    # Get TA's netID
    ta_netid = auth.get_username()

    # Get session info
    session_info = database.get_session_info_ta(ta_netid)
    if not session_info:
        return flask.redirect('/workhub')

    # Get student's name
    student_name = session_info['student_name']

    # Get student's netID
    student_netid = session_info['student_netid']

    # Get session ID
    session_id = session_info['session_id']

    # Get course
    course = session_info['course']

    # Get assignment
    assignment = session_info['assignment']

    # Get bug description
    bug_description = session_info['bug_description']

    # Get session start time 
    time_session_began = database.get_time_session_began(session_id)

    # End session button takes TA to next page
    if flask.request.method == 'POST':
        # Get TA's button request
        action = flask.request.form.get('action')

        if action == 'end_session':
            # Remove session from queue after session ends
            database.remove_session(student_netid)

            # Redirect TA to end session page
            response = flask.redirect('/endsessionta')

            response.set_cookie('student_name', student_name)
            
            return response

    return flask.render_template('insessionta.html', student_name=student_name,
                                 course=course, assignment=assignment,
                                 bug_description=bug_description, 
                                 time_session_began = time_session_began)

#-----------------------------------------------------------------------
# End Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/endsessionta', methods=['GET', 'POST'])
def endsessionta():
    """ Method that displays the end page, the student's name, and
    a button to return back to home. """
    
    # Get TA's netID
    ta_netid = auth.get_username()

    # Get student's name because when session ends, 
    # we need to show student's name to TA
    student_name = flask.request.cookies.get('student_name')

    if flask.request.method == 'POST':
        action = flask.request.form.get('action')
        if action == 'home':
            # Redirect to work hub page
            return flask.redirect('/workhub')

    return flask.render_template('endsessionta.html', student_name=student_name)