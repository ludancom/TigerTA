#-----------------------------------------------------------------------
# ta.py
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
import os
import database
import auth

#-----------------------------------------------------------------------
ta_routes = flask.Blueprint('ta_routes', __name__)

#-----------------------------------------------------------------------
# TA Home Page:
#-----------------------------------------------------------------------

@ta_routes.route('/', methods={'GET'})
@ta_routes.route('/home', methods={'GET'})
def homepage():
    """ Method that displays the homepage page to TAs. """

    # Send users to the HTML home page
    html_code = flask.render_template('homepage.html')
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# Role Selection Page:
#-----------------------------------------------------------------------

@ta_routes.route('/roleselection', methods={'GET', 'POST'})
def roleselection():
    """ Method that displays the option for TAs to either be a TA or
    a student for their session. """

    # Authenticate CAS
    auth.authenticate()

    # Get the user's net id from CAS
    net_id = auth.get_username()

    if flask.request.method == 'POST':

        # Get the user's role
        role = flask.request.form.get('role')

        # If the TA role is selected, validate that the user is actually a TA
        if role == 'TA':
            ### Implement this function later ###
            is_ta = database.validate_ta(net_id)

            # If the user is a TA, send them to the TA work hub
            if is_ta:
                response = flask.redirect('/workhub')

            # If the user is not a TA, send them to an error page
            else:
                response = flask.redirect('/error')

        # If the student role is selected, send them to the student workflow
        else:
            response = flask.redirect('/queueentry')

        # Set net_id cookie
        response.set_cookie('net_id', net_id)

        return response

    return flask.render_template('roleselection.html')

#-----------------------------------------------------------------------
# Work Hub Page:
#-----------------------------------------------------------------------
@ta_routes.route('/workhub', methods=['GET', 'POST'])
def workhub():
    """ Method that displays the work hub page for TAs and allows
    them to clock in and start a session. """

    # Get netid cookies
    ta_netid = flask.request.cookies.get('net_id')
    
    if flask.request.method == 'POST':
        
        # Get the user's button request
        action = flask.request.form.get('action')

        # Update the TA's attendance when they clock in
        ### Implement this function later ###
        if action == clock_in:
            database.clock_in(ta_netid)

        # If the TA wants to start a session...
        if action == start_session:
            session_info = database.start_session(ta_netid)
            # This can all be done in one function in database.py

            # Change the TA's availability to true

            # Check if the TA has gotten matched
                # pull everyone from sessions table where ta_netid = self tas netid
                # get and return the student's information (name, course, assignment, bug description) that they were matched with from the sessions table
                # IF matched.... redirect to the in session page

            # If not matched yet...
                # Refresh and check again every 5 seconds or so (this is done in JS on frontend)

        # Set session info cookie
        response.set_cookie('session_info', session_info)

    return flask.render_template('workhub.html')

#-----------------------------------------------------------------------
# In Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/insessionta', methods=['GET', 'POST'])
def insessionta():
    """ Method that displays the student the TA was matched with and
    their session details. """

    # Get session info cookie
    session_info = flask.request.cookies.get('session_info')

    # Get student info
    student_name = session_info['student_name']

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
        if action == end_session:

            # Remove the session from the queue after session ends
            database.remove_session(session_id)

            # Redirect to the end session page
            response = flask.redirect('/endsessionta')

            # Set student name cookie for the end session page
            response.set_cookie('student_name', student_name)

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
        if action == home:

            # Redirect to the work hub  page
            response = flask.redirect('/workhub')

    return response
