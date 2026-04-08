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

#-----------------------------------------------------------------------
ta_routes = flask.Blueprint('ta_routes', __name__, template_folder='.')

#-----------------------------------------------------------------------
# Work Hub Page:
#-----------------------------------------------------------------------
@ta_routes.route('/workhub', methods=['GET', 'POST'])
def workhub():
    """ Method that displays the work hub page for TAs and allows
    them to clock in and start a session. """

    # Get netid cookie
    ta_netid = auth.get_username() or flask.request.cookies.get('net_id')

    if not ta_netid:
        return flask.redirect('/')
    
    if flask.request.method == 'POST':
        # Get the user's button request
        action = flask.request.form.get('action')

        # Update the TA's attendance when they clock in
        ### Implement this function later ###
        if action == 'clock_in':
            # creating the 2 hour shift for the TA when clocked in
            current_time = int(time.time())
            expires = database.get_clockin_expire(ta_netid) or 0
            if expires <= current_time:
                # add the shift to the clock in table, and expire in 2 hours
                database.clock_in(ta_netid)
                database.set_clockin_expire(ta_netid, current_time + 60*60*2)
            # redirect so they cant submit twice
            return flask.redirect('/workhub')

        # If the TA wants to start a session...
        if action == 'start_session':
            #ta clicks the button to take the next queued student
            database.set_available(ta_netid)
            session_id = database.start_session(ta_netid)
            if session_id is not None:
                return flask.redirect('/insessionta')
            return flask.redirect('/workhub')

    # Check if TA was matched by seeing if session_info is able
    # to be extracted
    session_info = database.get_session_info_ta(ta_netid)
     # If they are matched, send them to the in session page
    if session_info:
        return flask.redirect('/insessionta')

    # button is disabled if clocked in
    current_time = int(time.time())
    expires = database.get_clockin_expire(ta_netid) or 0
    clock_disabled = expires > current_time

    queue_students = database.get_queue_students()
    active_sessions = database.get_active_sessions()

    return flask.render_template('workhub.html', clock_disabled=clock_disabled,
                                   queue_students=queue_students,
                                    active_sessions=active_sessions)

#-----------------------------------------------------------------------
# JSON Helper for Workhub:
#-----------------------------------------------------------------------
@ta_routes.route('/workhub_status', methods=['GET'])
def workhub_status():
    """JSON checker for determining whether TA has been matched."""
    ta_netid = auth.get_username() or flask.request.cookies.get('net_id')
    session_info = database.get_session_info_ta(ta_netid)
    #it is matched if there is session info inside
    return {'matched': session_info is not None}

#-----------------------------------------------------------------------
# In Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/insessionta', methods=['GET', 'POST'])
def insessionta():
    """ Method that displays the student the TA was matched with and
    their session details. """

    #get the current ta net id
    ta_netid = auth.get_username() or flask.request.cookies.get('net_id')

    if not ta_netid:
        return flask.redirect('/')

    # Get session info
    session_info = database.get_session_info_ta(ta_netid)
    if not session_info:
        return flask.redirect('/workhub')

    # Get student name
    student_name = session_info['student_name']

    # Get student net id
    student_netid = session_info['student_netid']

    # Get session id
    session_id = session_info['session_id']

    # Get course
    course = session_info['course']

    # Get assignment
    assignment = session_info['assignment']

    # Get bug description
    bug_description = session_info['bug_description']

    # End session button takes them to next page
    if flask.request.method == 'POST':
        # Get the user's button request
        action = flask.request.form.get('action')

        if action == 'end_session':
            # Remove the session from the queue after session ends
            database.remove_session(session_id, student_netid)

            # Redirect to the end session page
            response = flask.redirect('/endsessionta')

            # Set student name cookie for the end session page
            response.set_cookie('student_name', student_name)
            return response

    return flask.render_template('insessionta.html', student_name=student_name,
                                 course=course, assignment=assignment,
                                 bug_description=bug_description)


#-----------------------------------------------------------------------
# End Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/endsessionta', methods=['GET', 'POST'])
def endsessionta():
    """ Method that displays the end page, the student's name, and
    a button to return back to home. """

    # Get student name cookie
    student_name = flask.request.cookies.get('student_name')

    if flask.request.method == 'POST':
        action = flask.request.form.get('action')
        if action == 'home':
            # Redirect to the work hub  page
            response = flask.redirect('/workhub')

    return flask.render_template('endsessionta.html', student_name=student_name)