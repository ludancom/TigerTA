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
# Logout Helper for All Pages:
#-----------------------------------------------------------------------
@student_routes.route('/logout', methods={'GET'})
def logout():
    """ Method that logs out students. """
    
    # Get the user's net id from CAS   
    netid = auth.get_username()

    # Remove session from database if student is in the queue
    status = database.student_already_in_queue(netid)
    if(status == "InQueue" or status == "InSession"):
        database.remove_session(netid)

    # Remove session from database if TA is helping student 
    ta_session_info = database.get_session_info_ta(netid)
    if ta_session_info is not None:
        student_netid = ta_session_info['student_netid']
        database.remove_session(student_netid)
    
    # Log out
    auth.logoutapp()
    # Go to Home Page
    return flask.redirect('/home')

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

    # Get student net id
    student_netid = auth.get_username()

    if flask.request.method == 'POST':
        # check before inserting student into queue
        status = database.student_already_in_queue(student_netid)
        if status == "InQueue":
            return flask.redirect('/queuestatus?error=already_in_queue')
        elif status == "InSession":
            return flask.redirect('/insessionstudent?error=already_in_session')

        # get student name
        student_name = flask.request.form.get('student_name')

        # get course
        course = flask.request.form.get('course')

        # get assignment
        assignment = flask.request.form.get('assignment')

        # get bug description
        bug_description = flask.request.form.get('bug_description') or ''

        # get session info
        session = {
            'student_netid': student_netid,
            'student_name': student_name,
            'course': course,
            'assignment': assignment,
            'bug_description': bug_description
        }

        # insert the session into the database
        database.queue_entry(session)
        return flask.redirect('/queuestatus')

    return flask.render_template('queueentry.html')

#-----------------------------------------------------------------------
# Queue Status Page:
#-----------------------------------------------------------------------
@student_routes.route('/queuestatus', methods=['GET', 'POST'])
def queuestatus():
    """ Method that displays the queue status page for students to
    view their position in the queue and their bug description. """
    #Get student ent id
    student_netid = auth.get_username()

    # Get relevant session info
    session_info = database.get_session_info_student(student_netid)
    if not session_info:
        return flask.redirect('/queueentry')

    # if TA has already been assigned, go to the in session page
    ta_name = database.get_session_ta_name(student_netid)
    if ta_name is not None:
        return flask.redirect('/insessionstudent')

    # Get bug description
    bug_description = session_info['bug_description']

    #Get course
    course = session_info['course']

    # get student place
    student_place = database.find_student_place(course, student_netid)

    #get number of available tas
    num_on_shift_tas = database.get_num_on_shift_tas(course)

    if flask.request.method == 'POST':
        action = flask.request.form.get('action')
        if action == 'leave_queue':
            database.remove_session(student_netid)
            return flask.redirect('/queueentry')

    return flask.render_template(
        'queuestatus.html',
        bug_description=bug_description,
        student_place=student_place,
        num_on_shift_tas=num_on_shift_tas
    )
#-----------------------------------------------------------------------
# Match Attempt & Updating Number of TAs on Shift (For Queue Status Page):
#-----------------------------------------------------------------------
@student_routes.route('/trymatch', methods={'GET'})
def trymatch():
    # Get student net id
    student_netid = auth.get_username()

    # if the session no longer exists
    session_info = database.get_session_info_student(student_netid)
    if not session_info:
        return {
            "matched": False,
            "student_place": None
        }

    #Get course
    course = session_info['course']

    #Get student place
    student_place = database.find_student_place(course, student_netid)

    # check whether a TA has already been assigned
    ta_name = database.get_session_ta_name(student_netid)

    # Retrieve number of TAs on shift for specific course
    num_on_shift_tas = database.get_num_on_shift_tas(course)

    return {
        "matched": ta_name is not None,
        "student_place": student_place,
        "num_on_shift_tas": num_on_shift_tas
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

    # Get session info
    session_info = database.get_session_info_student(student_netid)
    if not session_info:
        return flask.redirect('/queueentry')

    # Get ta name
    ta_name = database.get_session_ta_name(student_netid)
    if ta_name is None:
        return flask.redirect('/queuestatus')

    # Get bug description
    bug_description = session_info['bug_description']

    return flask.render_template(
        'insessionstudent.html',
        bug_description=bug_description,
        ta_name=ta_name
    )


#-----------------------------------------------------------------------
# End Session Student Page:
#-----------------------------------------------------------------------
@student_routes.route('/endsessionstudent', methods=['GET', 'POST'])
def endsessionstudent():
    """ Method that displays the end page, the TA's name, and
    a button to return back to home. """

    # Get the ta name from the cookie
    ta_name = flask.request.cookies.get('ta_name')

    # If the student clicks the home button
    if flask.request.method == 'POST':
        if flask.request.form.get('action') == 'home':
            # take them back to the queue entry page
            return flask.redirect('/queueentry')

    return flask.render_template('endsessionstudent.html', ta_name=ta_name)


#-----------------------------------------------------------------------
# Submit Feedback Modal:
#-----------------------------------------------------------------------
@student_routes.route('/submitfeedback', methods=['GET', 'POST'])
def submit_feedback():
    """ Method that displays the feedback modal, the TA's name, and
    a button to submit feedback. """
    import datetime
    import googlesheet

    rating = flask.request.form.get('rating', '').strip()
    feedback_text = flask.request.form.get('feedback_text', '').strip()
    ta_name = flask.request.form.get('ta_name', '').strip()


    timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")

    googlesheet.log_feedback(
        timestamp,
        ta_name,
        rating,
        feedback_text
    )

    return flask.redirect(flask.url_for('student_routes.queueentry'))

    


