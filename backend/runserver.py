#-----------------------------------------------------------------------
# runserver.py
# Author: Amel Osman
#-----------------------------------------------------------------------
""" Server program that takes in command line arguments and begins
our flask program. """

import sys
import argparse
import reg3

def main():
    parser = argparse.ArgumentParser(description=
    "COS Lab TA Queue Application")
    parser.add_argument("port",type=int,
    help= "the port at which the server should listen")

    args = parser.parse_args()

    try:
        reg3.app.run(host='0.0.0.0', port=args.port, debug=True)
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
