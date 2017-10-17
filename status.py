# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


import json, kubernetes
from sys import stdout, stderr

import deployment, kubeutil

# status: print the overall status of a deployment and any errors.
def status(args):
    try:
        dp = deployment.get_deployment(args.namespace, args.name)
        replicasets = deployment.get_replicasets(dp)
    except Exception as e:
        stderr.write('cannot load deployment {0}: {1}\n'.format(
            args.name, kubeutil.get_error(e)))
        exit(1)

    try:
        generation = dp['metadata']['annotations']['deployment.kubernetes.io/revision']
    except KeyError:
        generation = '?'

    stdout.write("deployment {0}/{1}:\n".format(
            dp['metadata']['namespace'],
            dp['metadata']['name'],
    ))
    stdout.write("  current generation is {0}, {2} replicas configured, {1} active replica sets\n".format(
        generation,
        len(replicasets),
        dp['spec']['replicas'],
    ))
    stdout.write("\n  active replicasets (status codes: * current, ! error):\n")

    for rs in replicasets:
        pods = deployment.get_rs_pods(rs)
        error = ' '

        try:
            revision = rs['metadata']['annotations']['deployment.kubernetes.io/revision']
        except KeyError:
            revision = '?'

        if str(revision) == str(generation):
            active = '*'
        else:
            active = ' '

        try:
            nready = rs['status']['readyReplicas']
        except KeyError:
            error = '!'
            nready = 0

        errors = []
        try:
            for condition in rs['status']['conditions']:
                if condition['type'] == 'ReplicaFailure' and condition['status'] == 'True':
                    errors.append(condition['message'])
                    error = '!'
        except KeyError:
            pass

        stdout.write("    {4}{5}generation {1} is replicaset {0}, {2} replicas configured, {3} ready\n".format(
            rs['metadata']['name'],
            revision,
            rs['spec']['replicas'],
            nready,
            active,
            error
        ))

        for container in rs['spec']['template']['spec']['containers']:
            stdout.write("        container {0}: image {1}\n".format(
                container['name'],
                container['image'],
            ))

        for error in errors:
            stdout.write("        {0}\n".format(error))

        for pod in pods:
            try:
                phase = pod['status']['phase']
            except KeyError:
                phase = '?'

            stdout.write("        pod {0}: {1}\n".format(
                pod['metadata']['name'],
                phase,
            ))

            if 'status' in pod and 'containerStatuses' in pod['status']:
                for cs in pod['status']['containerStatuses']:
                    if 'waiting' in cs['state']:
                        try:
                            message = cs['state']['waiting']['message']
                        except KeyError:
                            message = '(no reason)'

                        stdout.write("          {0}: {1}\n".format(
                            cs['state']['waiting']['reason'],
                            message,
                        ))

status.help = "show deployment status"
status.arguments = (
    ( ('name',), {
        'type': str,
        'help': 'deployment name',
    }),
)

commands = {
    'status': status
}
