#-----------------------------------------------------------------------
# student.py
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
import os
import database
import auth

#-----------------------------------------------------------------------
# New workflow needs this
student_routes = flask.Blueprint('student_routes', __name__, template_folder='.')

#-----------------------------------------------------------------------
# Secure Https Use:
#-----------------------------------------------------------------------

@student_routes.before_request
def before_request():
    is_running_locally = '//localhost:' in flask.request.url_root
    is_using_https = flask.request.is_secure
    if (not is_running_locally) and (not is_using_https):
        url = flask.request.url.replace('http://', 'https://', 1)
        return flask.redirect(url, code=301)
    return None

#-----------------------------------------------------------------------
# Home Page:
#-----------------------------------------------------------------------

@student_routes.route('/', methods={'GET'})
@student_routes.route('/home', methods={'GET'})
def homepage():
    """ Method that displays the homepage page to students. """

    # Send users to the HTML home page
    html_code = flask.render_template('homepage.html')
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# Role Selection Page:
#-----------------------------------------------------------------------

@student_routes.route('/roleselection', methods={'GET', 'POST'})
def roleselection():
    """ Method that displays the option to either be a TA or
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

            # Returns true if they are truly a TA
            is_ta = database.validate_ta(net_id)

            # If the user is a TA, send them to the TA work hub
            if is_ta:
                response = flask.redirect(flask.url_for('ta_routes.workhub'))

            # If the user is not a TA, send them an error alert 
            else:
                response = flask.redirect('/roleselection?error=not_ta')

        # If the Admin role is selected, validate that the user is actually an admin
        elif role == 'Admin':
            
             # Returns true if they are truly an admin
            is_admin = database.validate_admin(net_id)

            # If the user is an admin, send them to the admin page
            if is_admin:
                response = flask.redirect(flask.url_for('admin_routes.adminpage'))
            
            else:
                response = flask.redirect('/roleselection?error=not_admin')

        # If the student role is selected, send them to the student
        # queue entry
        else:
            status = database.student_already_in_queue(net_id)
            print("STATUS:", status)
            # Check if student is already in queue or being helped. If so, redirect them to the correct page. 
            if(status == "InQueue"):
                response = flask.redirect('/queuestatus')
            elif(status == "InSession"):
                response = flask.redirect('/insessionstudent')  
            else:
                response = flask.redirect('/queueentry')

        return response

    return flask.render_template('roleselection.html')

#-----------------------------------------------------------------------
# Queue Entry Page:
#-----------------------------------------------------------------------
@student_routes.route('/queueentry', methods=['GET', 'POST'])
def queueentry():
    """ Method that displays the queue entry page for students to
    enter their issue and select their course and assignment. """

    # Get the user's net id 
    student_netid = auth.get_username()
    
    if flask.request.method == 'POST':
        
        # Get the user's name
        student_name = flask.request.form.get('student_name')

        # Get the user's course
        course = flask.request.form.get('course')

        # Get the user's assignment
        assignment = flask.request.form.get('assignment')

        # Get the user's bug description
        bug_description = flask.request.form.get('bug_description')
        if bug_description is None:
            bug_description = ''

        # Create the list of session information
        session = {
            'student_netid': student_netid,
            'student_name': student_name,
            'course': course,
            'assignment': assignment,
            'bug_description': bug_description
        }

        # Send session info to Neon database
        database.queue_entry(session)

        #So basically what I had to do was figure out a way to use match
        # and use it on both sides
        #so i had to modify the match function to take in both student and TA net IDs
        #and then i ended up calling match in start session for a TA
        # so here we only want students to join the queue, then
        # TA clicks start session and the match function is called
        # and does the work instead
        response = flask.redirect('/queuestatus')

        # Try to match student with TA
        #ta_name = database.find_ta_name(course, student_netid)
        # If match is successful
        #if ta_name:
            # Display in session page
            #response = flask.redirect('/insessionstudent')
        #else: 
            # Otherwise, display queue entry page
            #response = flask.redirect('/queuestatus')

        return response

    return flask.render_template('queueentry.html')

#-----------------------------------------------------------------------
# Queue Status Page:
#-----------------------------------------------------------------------
@student_routes.route('/queuestatus', methods={'GET', 'POST'})
def queuestatus():
    """ Method that displays the queue status page for students to
    view their position in the queue and their bug description. """
    student_netid = auth.get_username()

    # Get relevant session data:
    session_info = database.get_session_info_student(student_netid)

    # Get bug description
    bug_description = session_info['bug_description']

    # Get course
    course = session_info['course']

    # Continue displaying queue status page if user does not match with TA
    student_place = database.find_student_place(course, student_netid)
    num_helping_tas = database.get_num_helping_tas(course)
    html_code = flask.render_template('queuestatus.html', bug_description = bug_description, student_place = student_place, num_helping_tas = num_helping_tas)
    response = flask.make_response(html_code)

    # Leave queue button takes them to queue entry page 
    if flask.request.method == 'POST':
        # Get the user's button request
        action = flask.request.form.get('action')

        if action == 'leave_queue':
            # Remove the session from the queue 
            database.remove_session(student_netid)

            # Redirect to the queue entry page
            response = flask.redirect('/queueentry')

    return response

#-----------------------------------------------------------------------
# Match Attempt (For Queue Status Page):
#-----------------------------------------------------------------------
@student_routes.route('/trymatch', methods={'GET'})
def trymatch():
    # Get student net id
    student_netid = auth.get_username()

    # Get relevant session data:
    session_info = database.get_session_info_student(student_netid)

    course = session_info['course']
    
    # If TA is found, Queue Status page will redirect to In Session page
    student_place = database.find_student_place(course, student_netid)
    ta_name = None

    # Only try to match a student if they are first in the queue
    if(student_place == 1):
        ta_name = database.find_ta_name(course, student_netid)
    # Javascript Object Format
    return {
        "matched": ta_name is not None,
        "student_place": student_place  
    }

#-----------------------------------------------------------------------
# In Session Page:
#-----------------------------------------------------------------------
@student_routes.route('/insessionstudent', methods={'GET'})
def insessionstudent():
    """ Method that displays the TA the student was matched with and
    their bug description. """

    # Get student net id
    student_netid = auth.get_username()
    
    # Get relevant session data:
    session_info = database.get_session_info_student(student_netid)

    # Get TA name
    ta_name = database.get_session_ta_name(student_netid)

    # Get bug description
    bug_description = session_info['bug_description']

    # Display in session page
    html_code = flask.render_template('insessionstudent.html', 
    bug_description = bug_description, ta_name = ta_name)
    response = flask.make_response(html_code)
    
    return response


#-----------------------------------------------------------------------
# End Session Student Page:
#-----------------------------------------------------------------------
@student_routes.route('/endsessionstudent', methods=['GET', 'POST'])
def endsessionstudent():
    """ Method that displays the end page, the TA's name, and
    a button to return back to home. """

    # Get student net id
    student_netid = auth.get_username()
    
    # Get relevant session data:
    session_info = database.get_session_info_student(student_netid)

    # Get TA name
    ta_name = database.get_session_ta_name(student_netid)

    # Display end session page
    html_code = flask.render_template('endsessionstudent.html', 
    ta_name = ta_name)

    response = flask.make_response(html_code)

    # Back to work hub page if they press "Home" button
    if flask.request.method == 'POST':

        # Get the user's button request
        action = flask.request.form.get('action')

        # If the user presses the end session button, it redirects 
        # them to the end session page
        if action == 'home':

            # Redirect to the queue entry page
            response = flask.redirect('/queueentry')

    return response
