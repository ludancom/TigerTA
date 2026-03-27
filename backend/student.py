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
app = flask.Flask(__name__, template_folder='.')

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

    # Get net id from CAS
    student_netid = auth.get_username()
    
    if flask.request.method == 'POST':
        
        # Get the user's name
        #student_name = flask.request.form.get('student_name')
        student_name = flask.request.form.get('student_name')

        # Get the user's course
        course = flask.request.form.get('course')

        # Get the user's assignment
        assignment = flask.request.form.get('assignment')

        # Get the user's bug description
        bug_description = flask.request.form.get('bug_description')
        if bug_description is None:
            bug_description = ''

        # Display queue entry page
        response = flask.redirect('/queuestatus')

        # Set cookies
        response.set_cookie('bug_description', bug_description)

        # Create the list of session information
        session = {
            'student_netid': student_netid,
            'student_name': student_name,
            'course': course,
            'assignment': assignment,
            'bug_description': bug_description
        }

        # Sending session info to Neon database
        ta_name = database.queue_entry(session)
        if ta_name is None:
            ta_name = ''

        # Set ta name cookie
        response.set_cookie('ta_name', ta_name)

        #place = ta_place[0]
        #place = ta_place[1]

        return response

    return flask.render_template('queueentry.html')

#-----------------------------------------------------------------------
# Queue Status Page:
#-----------------------------------------------------------------------
@app.route('/queuestatus', methods={'GET'})
def queuestatus():
    """ Method that displays the queue status page for students to
    view their position in the queue and their bug description. """

    # Getting bug description from cookies
    bug_description = flask.request.cookies.get('bug_description')

    # Display queue status page
    html_code = flask.render_template('queuestatus.html', bug_description = bug_description, ta_name = ta_name)
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# In Session Page:
#-----------------------------------------------------------------------
@app.route('/insessionstudent', methods={'GET'})
def insessionstudent():
    """ Method that displays the TA the student was matched with and
    their bug description. """
    
    # Getting TA name from cookies
    ta_name = flask.request.cookies.get('ta_name')

    # Getting bug description from cookies
    bug_description = flask.request.cookies.get('bug_description')

    # Display queue status page
    html_code = flask.render_template('queuestatus.html', bug_description, ta_name)
    response = flask.make_response(html_code)
    
    return response