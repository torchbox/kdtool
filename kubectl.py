# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


import os, json, subprocess
from sys import stdout, stderr, exit


# get_kubectl_args: return a kubectl command line to connect to the cluster
# based on our arguments.
def get_kubectl_args(args):
    kargs = [ args.kubectl ]

    if args.server:
        kargs.append('--server='+args.server)
    if args.token:
        kargs.append('--token='+args.token)
    if args.ca_certificate:
        kargs.append('--certificate-authority='+args.ca_certificate)
    if args.namespace:
        kargs.append('--namespace='+args.namespace)

    return kargs

# find_kubectl: try to locate kubectl.  searches $PATH, then tries some likely
# locations.
def find_kubectl():
    try_ = os.environ.get('PATH', '').split(os.pathsep)
    try_.extend([
        # Often installed here
        '/usr/local/bin',
        # The Torchbox package puts it here
        '/opt/tbx/bin',
    ])

    for path in try_:
        filename = path + "/kubectl"
        if os.path.isfile(filename):
            return filename
        if os.path.isfile(filename + ".exe"):
            return filename + ".exe"

    return None


# apply_manifest: feed a manifest to kubectl.  the input should be an API object
# which will be converted to JSON.  to apply multiple objects, use a v1.List
# object.
def apply_manifest(manifest, args):
    kargs = get_kubectl_args(args)

    if args.undeploy:
        kargs.append('delete')
    else:
        kargs.append('apply')

    if args.dry_run:
        kargs.append('--dry-run')

    kargs.extend(['-f', '-'])

    spec = json.dumps(manifest)

    kubectl = subprocess.Popen(kargs, stdin=subprocess.PIPE)
    kubectl.communicate(spec.encode('utf-8'))
    return kubectl.returncode
