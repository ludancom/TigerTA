
TigerTA is a web-based queue management system designed for COS LabTA, 
the Princeton University computer science intro course TA system. 
The platform streamlines the interaction between students, TAs, 
and administrators by providing real-time queue management, automatic 
TA-student matching, session tracking, notifications, administrative 
tools, and additional features and safeguards for TA management and analytics.

Our system is divided into three different workflows: student, TA, and administrators. 
At the most basic level, students join course-specific queues and are helped by TAs, 
TAs start sessions and automatically get matched with the next student waiting in queue, 
and administrators have the ability to delete, add, and control the information of TA.

These workflows, particularly the Student and TA workflows, include much overlap. 
Each section still emphasizes testing as it relates to the respective workflow; however, 
for functionality purposes, will require the grader to play multiple roles at one time.

TigerTA uses Princeton NetID authentication and role-based authorization to ensure that only 
approved users can access TA and administrator functionality. While admin are able to adjust the 
information of TAs, as well as add and remove TAs, you must be manually added into our database 
in order to have access to the admin workflow.

-- To Run Locally --------------------------------------------------------------
1. Make sure the included .env file is in the project root. The repo on GitHub
   does not contain .env for security reasons, but we have specified where you
   can find it in the Product Evaluation document.
2. Install dependencies:

      pip install -r requirements.txt
   
3. To run the app, replacing 5555 with any free port:

      python app.py 5555
   
4. Visit http://localhost:5555 in a browser.
The deployed version of TigerTA is available at https://tigerta.onrender.com .

-- To Run Tests ----------------------------------------------------------------

The test scripts must be run locally. With dependencies installed, run:
    
    python -m unittest test_automation.py -v
    
    python -m unittest test_boundary.py -v
    
For combined coverage measurement:
    
    coverage erase && coverage run --source=database,student,ta,admin,notifications -m unittest test_automation.py test_boundary.py && coverage report -m && coverage html && open htmlcov/index.html
    
A successful run prints "Ran 100 tests in X.Xs" followed by "OK" and a
coverage report showing 85% total coverage. See the Product Evaluation
document for more detail.
