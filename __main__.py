#! /usr/bin/env python3
# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


import argparse, json, subprocess, tempfile, re, humanfriendly
from base64 import b64encode
from os import environ
from sys import stdout, stderr, exit, argv

from kubectl import find_kubectl

import deploy, shell, status, kubeutil

class PrintVersion(argparse.Action):
  def __call__(self, parser, namespace, values, option_string):
    try:
        import version
        print('kdtool version {}, {}.'.format(
                        version.__version__, version.__info__))
    except ImportError:
        print('kdtool, development build or manual installation.')
    exit(0)

# Create our argument parser.
parser = argparse.ArgumentParser(description='Kubernetes deployment tool')
subparsers = parser.add_subparsers(
                title='commands',
                description='valid commands',
                help='additional help')

# Global options for all modes; mostly to do with Kubernetes connection.
parser.add_argument('-V', '--version', nargs=0, action=PrintVersion,
    help="Type program version and exit")
parser.add_argument('-K', '--kubectl', type=str, metavar='PATH',
    help='Location of kubectl binary')
parser.add_argument('-n', '--namespace', type=str, default="default",
    help='Kubernetes namespace to deploy in')
parser.add_argument('-S', '--server', type=str, metavar='URL',
    help="Kubernetes API server URL")
parser.add_argument('-T', '--token', type=str,
    help="Kubernetes authentication token")
parser.add_argument('-C', '--ca-certificate', type=str,
    help="Kubernetes API server CA certificate")
parser.add_argument('-G', '--gitlab', action='store_true',
    help="Configure Kubernetes from Gitlab CI")

# Add commands and their options from modules.
def add_commands(cmds):
  for cmd in sorted(cmds):
    func = cmds[cmd]
    if hasattr(func, 'arguments'):
      p = subparsers.add_parser(cmd, help=func.help)
      p.set_defaults(func=func)
      for arg in func.arguments:
        p.add_argument(*arg[0], **arg[1])

add_commands(deploy.commands)
add_commands(shell.commands)
add_commands(status.commands)
args = parser.parse_args(argv[1:])

# Try to find kubectl.
if args.kubectl is None:
    args.kubectl = find_kubectl()
if args.kubectl is None:
    stderr.write('could not find kubectl executable anywhere in $PATH.\n')
    stderr.write('install kubectl in $PATH or pass -K/path/to/kubectl.\n')
    exit(1)

# Check for GitLab mode.
if args.gitlab:
    if 'KUBECONFIG' in environ:
        stderr.write("""\
warning: argument -G/--gitlab specified but $KUBECONFIG is set in environment.
         since GitLab 9.4, the --gitlab option is no longer required and should
         be removed.
warning: $KUBECONFIG will be ignored and Kubernetes configuration will be taken
         from legacy GitLab environment configuration.
""")
        del environ['KUBECONFIG']

    try:
        if 'KUBE_CA_PEM_FILE' in environ:
            args.ca_certificate = environ['KUBE_CA_PEM_FILE']
        elif 'KUBE_CA_PEM' in environ:
            tmpf = tempfile.NamedTemporaryFile(delete=False)
            tmpf.write(environ['KUBE_CA_PEM'].encode('utf-8'))
            tmpf.close()
            args.ca_certificate = tmpf.name
        else:
            stderr.write("--gitlab: cannot determine Kubernetes CA certificate\n")
            exit(1)
        args.namespace = environ['KUBE_NAMESPACE']
        args.server = environ['KUBE_URL']
        args.token = environ['KUBE_TOKEN']
    except KeyError as e:
        stderr.write("--gitlab: missing ${0} in environment\n".format(e.args[0]))
        exit(1)

kubeutil.configure(args)

# Run the subcommand requested by the user.
if not hasattr(args, 'func'):
  stderr.write("no command given\n")
  exit(0)
exit(args.func(args))
