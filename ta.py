#-----------------------------------------------------------------------
# ta.py
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
import os
import database

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
        
        # Get the user's clock in status
        action = flask.request.form.get('action')

        # Update the TA's attendance when they clock in
        ### Implement this function later ###
        if action == clock_in:
            database.clockin(ta_netid)

        # If the TA wants to start a session...
        if action == start_session:
            student_name = database.start_session()
            # This can all be done in one function in database.py

            # Change the TA's availability to true

            # Check if there are students in the queue
                # pull everyone from sessions table where ta_netid = Null

            # If there are students in the queue:
                # get and return the student's name that they were matched with from the sessions table

            # If there are no students in the queue:
                # Refresh and check again every 5 seconds or so (this is done in JS on frontend)

        # Set student name cookie
        response.set_cookie('student_name', student_name)

    return flask.render_template('workhub.html')

#-----------------------------------------------------------------------
# In Session TA Page:
#-----------------------------------------------------------------------
@ta_routes.route('/insessionta', methods=['GET', 'POST'])
def insessionta():
    """ Method that displays the TA the student was matched with and
    their bug description. """

    # Get student name cookie
    student_name = flask.request.cookies.get('student_name')

    # Get course
    # Get assignment
    # Get bug description
    # Display these things

    # Display in session page
    html_code = flask.render_template('insessionta.html', bug_description = bug_description, student_name = ta_name)
    response = flask.make_response(html_code)

    # End session button takes them to next page
    
    return response
