#-----------------------------------------------------------------------
# student.py
# Authors: Amel Osman
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
import os
import database
import auth
import dotenv

#-----------------------------------------------------------------------
# CAS Authentication
dotenv.load_dotenv()
_APP_SECRET_KEY = os.getenv('APP_SECRET_KEY')

#-----------------------------------------------------------------------
app = flask.Flask(
    __name__,
    template_folder='.',
    static_folder='.',
    static_url_path='/static'
)

app.secret_key = _APP_SECRET_KEY
auth.init(app)
#-----------------------------------------------------------------------

#-----------------------------------------------------------------------
# Student Home Page:
#-----------------------------------------------------------------------

@app.route('/', methods={'GET'})
@app.route('/home', methods={'GET'})
def homepage():
    """ Method that displays the homepage page to students. """

    # Send users to the HTML home page
    html_code = flask.render_template('homepage.html')
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# Queue Entry Page:
#-----------------------------------------------------------------------
@app.route('/queueentry', methods=['GET', 'POST'])
def queueentry():
    """ Method that displays the queue entry page for students to
    enter their issue and select their course and assignment. """

    # Authenticate CAS
    auth.authenticate()

    # Get the user's net id from CAS
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

        # Try to match student with TA
        ta_name = database.find_ta_name(course, student_netid)
        # If match is successful
        if ta_name:
            # Display in session page
            response = flask.redirect('/insessionstudent')
            # Set TA name cookie
            response.set_cookie('ta_name', ta_name)
        else: 
            # Otherwise, display queue entry page
            response = flask.redirect('/queuestatus')

        # Set cookies
        response.set_cookie('bug_description', bug_description)
        response.set_cookie('course', course)

        return response

    return flask.render_template('queueentry.html')

#-----------------------------------------------------------------------
# Queue Status Page:
#-----------------------------------------------------------------------
@app.route('/queuestatus', methods={'GET'})
def queuestatus():
    """ Method that displays the queue status page for students to
    view their position in the queue and their bug description. """

    # Get cookies
    bug_description = flask.request.cookies.get('bug_description')


    # Continue displaying queue status page if user does not match with TA
    html_code = flask.render_template('queuestatus.html', bug_description = bug_description)
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# Match Attempt (For Queue Status Page):
#-----------------------------------------------------------------------
@app.route('/trymatch', methods={'GET'})
def trymatch():
    # Get cookies
    student_netid = auth.get_username()
    course = flask.request.cookies.get('course')
    student_place = database.find_student_place(student_netid, course)

    # If TA is found, Queue Status page will redirect to In Session page
    ta_name = database.find_ta_name(course, student_netid)
    if ta_name:
    # Javascript Object Format
        return [{"matched": True}, student_place]
    else:
        return [{"matched": False}, student_place]

#-----------------------------------------------------------------------
# In Session Page:
#-----------------------------------------------------------------------
@app.route('/insessionstudent', methods={'GET'})
def insessionstudent():
    """ Method that displays the TA the student was matched with and
    their bug description. """
    
    # Get cookies
    ta_name = flask.request.cookies.get('ta_name')
    bug_description = flask.request.cookies.get('bug_description')

    # Display queue status page
    html_code = flask.render_template('insessionstudent.html', bug_description = bug_description, ta_name = ta_name)
    response = flask.make_response(html_code)
    
    return response