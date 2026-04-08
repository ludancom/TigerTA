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
    """ Method that displays the homepage page to administrators. """

    # Send users to the HTML home page
    html_code = flask.render_template('homepage.html')
    response = flask.make_response(html_code)

    return response

@admin_routes.route('/add_ta', methods=['GET', 'POST'])
def add_ta():
    """ Method that adds a TA to the database. """

    # Authenticate CAS
    auth.authenticate()

    # Get the user's net id from CAS
    net_id = auth.get_username()

    if role == 'admin':

        if flask.request.method == 'POST':

        # Get the TA's net id from the form
        ta_net_id = flask.request.form.get('ta_net_id')

        # Add the TA to the database
        database.add_ta(ta_net_id)

        # Send the user to a confirmation page
        response = flask.redirect(flask.url_for('admin_routes.view_tas'))

@admin_routes.route('/remove_ta', methods=['GET', 'POST'])
def remove_ta():
    """ Method that removes a TA from the database. """

    # Authenticate CAS
    auth.authenticate()

    # Get the user's net id from CAS
    net_id = auth.get_username()

    if flask.request.method == 'POST':

        # Get the TA's net id from the form
        ta_net_id = flask.request.form.get('ta_net_id')

        # Remove the TA from the database
        database.remove_ta(ta_net_id)

        # Send the user to a confirmation page
        response = flask.redirect(flask.url_for('admin_routes.view_tas'))

@admin_routes.route('/view_tas', methods=['GET', 'POST'])
def view_tas():
    """ Method that displays the list of TAs to the user. """

    # Send users to the HTML page with the list of TAs
    html_code = flask.render_template('view_tas.html')
    response = flask.make_response(html_code)

    return response