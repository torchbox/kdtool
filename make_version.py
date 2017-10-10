#! /usr/bin/env python3

import sys, getpass, platform, socket, time

if platform.system() == 'Windows':
    userhost='{}\\{}'.format(socket.gethostname(), getpass.getuser())
else:
    userhost='{}@{}'.format(getpass.getuser(), socket.gethostname())

with open('version.py', 'w') as f:
    f.write("""
__version__ = "{}"
__info__ = "built by {} on {}"
""".format(sys.argv[1], userhost, time.strftime('%Y-%m-%d %H:%M:%S %Z')))
