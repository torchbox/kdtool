#! /usr/bin/env python3
# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


from sys import stdout, stderr
import tempfile, argparse, subprocess, random, string, os, json, kubernetes

from kubectl import find_kubectl, get_kubectl_args


# find the application container for a given deployment.  if there is only one
# container, then return that one; otherwise return the container called "app".
# if no "app" container exists, return None.
def find_app_container(dp):
    if len(dp['spec']['template']['spec']['containers']) == 1:
        return dp['spec']['template']['spec']['containers'][0]

    for container in dp['spec']['template']['spec']['containers']:
        if container.name == "app":
            return container

    return None


# make_env: convert an env to a data structure we can pass as a JSON patch.
def make_env(env):
    ret = {
        'name': env.name,
    }

    if env.value:
        ret['value'] = env.value
    elif env.value_from:
        vf = env.value_from
        if vf.secret_key_ref:
            ret['valueFrom'] = {
                'secretKeyRef': {
                    'key': vf.secret_key_ref.key,
                    'name': vf.secret_key_ref.name,
                },
            }
    else:
        return None

    return ret


# make_envfrom: convert an env_from to a data structure we can pass as a JSON
# patch.
def make_envfrom(envfrom):
    if envfrom.secret_ref:
        return {
            'secretRef': {
                'name': envfrom.secret_ref.name,
            },
        }

    if envfrom.config_map_ref:
        return {
            'configMapRef': {
                'name': envfrom.config_map_ref.name,
            },
        }

    return None


# start a shell for the given deployment.
def shell(args, tty=True, command=None):
    config = kubernetes.client.Configuration()
    kubernetes.config.kube_config.load_kube_config(client_configuration=config)
    api_client = kubernetes.client.ApiClient(config=config)

    # We can't use the normal client API here because it returns Python objects
    # that can't be converted back into JSON.  Instead, fetch the JSON by hand.
    resource_path = ('/apis/extensions/v1beta1/namespaces/'
                    + args.namespace
                    + '/deployments/'
                    + args.name)

    header_params = {}
    header_params['Accept'] = api_client.select_header_accept(['application/json'])
    header_params['Content-Type'] = api_client.select_header_content_type(['*/*'])

    (resp, code, header) = api_client.call_api(
            resource_path, 'GET', {}, {}, header_params, None, [], _preload_content=False)
    dp = json.loads(resp.data.decode('utf-8'))

    app = find_app_container(dp)
    if app is None:
        stderr.write('could not find application container.\n')
        exit(1)

    # Create a complete Pod spec that we will pass to kubectl exec as an
    # override.  Metadata is not required, only spec.
    rng = random.SystemRandom()
    chars = string.ascii_lowercase + string.digits
    suffix = str().join(rng.choice(chars) for _ in range(4))
    pod_name = 'kdtool-' + dp['metadata']['name'] + '-' + suffix

    if command is None:
        if args.command is None:
            command = [ '/bin/sh', '-c', 'exec /bin/bash || exec /bin/sh' ]
        else:
            command = args.command.split(" ")

    if args.image:
        pod_image = args.image
    else:
        pod_image = app['image']

    pod = {
        'spec': {
            'containers': [{
                'name': pod_name,
                'image': pod_image,
                'command': command,
                'stdin': True,
                'stdinOnce': True,
                'tty': tty,
            }],
        },
    }

    if 'env' in app:
        pod['spec']['containers'][0]['env'] = app['env']
    if 'envFrom' in app:
        pod['spec']['containers'][0]['envFrom'] = app['envFrom']
    if 'volumeMounts' in app:
        pod['spec']['containers'][0]['volumeMounts'] = app['volumeMounts']
    if 'volumes' in dp['spec']['template']['spec']:
        pod['spec']['volumes'] = dp['spec']['template']['spec']['volumes']

    patch = json.dumps(pod)

    kargs = get_kubectl_args(args)
    kargs.extend([
        'run',
        '--restart=Never',
        '--rm',
        '-ti' if tty else '-i',
        '--image=' + pod_image,
        '--overrides='+patch,
        pod_name,
        '--',
        '/bin/false',  # not used
    ])

    ret = subprocess.call(kargs, start_new_session=True)
    exit(ret)

shell.help = "start an interactive shell for a deployment"
shell.arguments = (
    ( ('-c', '--command'), {
        'type': str,
        'help': 'command to run',
    }),
    ( ('-i', '--image'), {
        'type': str,
        'help': 'image to start',
    }),
    ( ('name',), {
        'type': str,
        'help': 'deployment name',
    }),
)


# exec: like shell, but no terminal.
def execcmd(args):
    return shell(args, tty=False, command=args.command)
execcmd.help = "run a non-interactive command for a deployment"
execcmd.arguments = (
    ( ('-i', '--image'), {
        'type': str,
        'help': 'image to start',
    }),
    ( ('name',), {
        'type': str,
        'help': 'deployment name',
    }),
    ( ('command',), {
        'type': str,
        'help': 'command to run',
        'nargs': argparse.REMAINDER,
    }),
)

commands = {
    'shell':    shell,
    'exec':     execcmd,
}
