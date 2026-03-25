#-----------------------------------------------------------------------
# student.py
# Authors: Amel Osman
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
import database
import auth

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
    """ Method that displays the queueentry page for students to
    enter their issue and select their course and assignment. """

    # Authenticate CAS
    auth.authenticate()

    # Get net id from CAS
    net_id = auth.get_username()

    # Get the user's course
    course = flask.request.args.get('course')
    if course is None:
        course = ''

    # Get the user's assignment
    assignment = flask.request.args.get('assignment')
    if assignment is None:
        assignment = ''

    # Get the user's bug description
    bug_description = flask.request.args.get('bug_description')
    if bug_description is None:
        bug_description = ''

    # Create the list of session information
    session = {
        'student': net_id,
        'course': course,
        'assignment': assignment,
        'bug_description': bug_description
    }

    # Sending session info to Neon database
    session = database.send_session_info(query)

    html_code = flask.render_template('queueentry.html',
            dept=prev_dept, coursenum=prev_coursenum,
            area=prev_area, title=prev_title,
            overviews = overviews_output[1])
        response = flask.make_response(html_code)

    # If it was not successful, send to the error page
    else:
        html_code = flask.render_template('error.html',
            error_message = overviews_output[1])
        response = flask.make_response(html_code)

    # Set cookies
    response.set_cookie('prev_dept', prev_dept)
    response.set_cookie('prev_coursenum', prev_coursenum)
    response.set_cookie('prev_area', prev_area)
    response.set_cookie('prev_title', prev_title)

    return response