#-----------------------------------------------------------------------
# admin.py
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """
import flask
import os
import database
import auth

#-----------------------------------------------------------------------
#new workflow needs this
admin_routes = flask.Blueprint('admin_routes', __name__, template_folder='.')

#-----------------------------------------------------------------------
# Home Page:
#-----------------------------------------------------------------------

@admin_routes.route('/', methods={'GET'})
@admin_routes.route('/home', methods={'GET'})
def homepage():
    """ Method that displays the homepage page to students. """

    # Send users to the HTML home page
    html_code = flask.render_template('homepage.html')
    response = flask.make_response(html_code)

    return response

