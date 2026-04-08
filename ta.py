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

    # Check if TA was matched by seeing if session_info is able
    # to be extracted
    session_info = database.get_session_info_ta(ta_netid)

    # If they are matched, send them to the in session page
    if session_info:
        response = flask.redirect('/insessionta')

        # Set their cookies to send to the in session page
        response.set_cookie('session_info', session_info)

        return response

        # If not matched yet...
            # Refresh and check again every 5 seconds or so 
            # (this is done in JS on frontend)
    
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

    # button is disabled if clocked in
    current_time = int(time.time())
    expires = database.get_clockin_expire(ta_netid) or 0
    clock_disabled = expires > current_time
         
    return flask.render_template('workhub.html', clock_disabled=clock_disabled)

#-----------------------------------------------------------------------
# In Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/insessionta', methods=['GET', 'POST'])
def insessionta():
    """ Method that displays the student the TA was matched with and
    their session details. """

    # Get session info cookie
    session_info = flask.request.cookies.get('session_info')

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

    # Display in session page
    html_code = flask.render_template('insessionta.html', 
    student_name = student_name, course = course, 
    assignment = assignment, bug_description = bug_description)

    response = flask.make_response(html_code)
    
    # End session button takes them to next page
    if flask.request.method == 'POST':

        # Get the user's button request
        action = flask.request.form.get('action')

        # If the user presses the end session button, it redirects 
        # them  to the end session page
        if action == 'end_session':

            # Remove the session from the queue after session ends
            database.remove_session(session_id, student_netid)

            # Redirect to the end session page
            response = flask.redirect('/endsessionta')

            # Set student name cookie for the end session page
            response.set_cookie('student_name', student_name)

        return response
    
    return response


#-----------------------------------------------------------------------
# End Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/endsessionta', methods=['GET', 'POST'])
def endsessionta():
    """ Method that displays the end page, the student's name, and
    a button to return back to home. """

    # Get student name cookie
    student_name = flask.request.cookies.get('student_name')

    # Display end session page
    html_code = flask.render_template('endsessionta.html', 
    student_name = student_name)

    response = flask.make_response(html_code)

    # Back to work hub page if they press "Home" button
    if flask.request.method == 'POST':

        # Get the user's button request
        action = flask.request.form.get('action')

        # If the user presses the end session button, it redirects 
        # them  to the end session page
        if action == 'home':

            # Redirect to the work hub  page
            response = flask.redirect('/workhub')

    return response