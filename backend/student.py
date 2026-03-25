#-----------------------------------------------------------------------
# student.py
# Authors: Amel Osman
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
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
@app.route('/queueentry', methods={'GET'})
def queueentry():
    """ Method that displays the queue entry page for students to
    enter their issue and select their course and assignment. """

    # Authenticate CAS
    auth.authenticate()

    # Get net id from CAS
    net_id = auth.get_username()

    # Get the user's course
    course = flask.request.args.get('course')

    # Get the user's assignment
    assignment = flask.request.args.get('assignment')

    # Get the user's bug description
    bug_description = flask.request.args.get('bug_description')

    # Create the list of session information
    session = {
        'student': net_id,
        'course': course,
        'assignment': assignment,
        'bug_description': bug_description
    }

    # Sending session info to Neon database
    session = database.send_session_info(query)

    # Display queue entry page
    html_code = flask.render_template('queueentry.html')
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# Queue Status Page:
#-----------------------------------------------------------------------
@app.route('/queuestatus', methods={'GET'})
def queueentry():
    """ Method that displays the queue status page for students to
    view their position in the queue and their bug description. """

    # Get the user's bug description
    bug_description = flask.request.args.get('bug_description')

    # Display queue status page
    html_code = flask.render_template('queuestatus.html', bug_description)
    response = flask.make_response(html_code)

    return response

#-----------------------------------------------------------------------
# In Session Page:
#-----------------------------------------------------------------------
@app.route('/insessionstudent', methods={'GET'})
def insessionstudent():
    """ Method that displays the TA the student was matched with and
    their bug description. """

    # Get the TA the student was matched with
    #### GET TA FROM DATABASE... WE MUST MATCH TA TO STUDENT SOMEWHERE ###

    # Get the user's bug description
    bug_description = flask.request.args.get('bug_description')

    # Display queue status page
    html_code = flask.render_template('queuestatus.html', bug_description, ta)
    response = flask.make_response(html_code)
    
    return response