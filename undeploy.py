# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.

import json
from sys import stdout, stderr, exit
from kubernetes.client.apis import core_v1_api, extensions_v1beta1_api

import deployment, kubectl, kubeutil

def undeploy(args):
    try:
        dp = deployment.get_deployment(args.namespace, args.name)
    except Exception as e:
        stderr.write('cannot load deployment {0}: {1}\n'.format(
            args.name, kubeutil.get_error(e)))
        exit(1)

    resources = None
    try:
        resources = json.loads(dp['metadata']['annotations']['kdtool.torchbox.com/attached-resources'])
    except KeyError:
        pass
    except ValueError as e:
        stderr.write("error: could not decode kdtool.torchbox.com/attached-resources annotation: {0}\n".format(str(e)))
        exit(1)

    stdout.write("\nthis deployment will be removed:\n")
    stdout.write("- {0}/{1}\n".format(
        dp['metadata']['namespace'],
        dp['metadata']['name'],
    ))

    if len(resources):
        if args.all:
            stdout.write("\nthe following attached resources will also be deleted:\n")
            for res in resources:
                extra = ''
                if res['kind'] == 'database':
                    extra = ' (database will be dropped)'
                elif res['kind'] == 'volume':
                    extra = ' (contents will be deleted)'

                stdout.write("- {0}: {1}{2}\n".format(
                    res['kind'],
                    res['name'],
                    extra
                ))
        else:
            stdout.write("\nthe following attached resources will NOT be deleted (use --all):\n")
            for res in resources:
                stdout.write("- {0}: {1}\n".format(
                    res['kind'],
                    res['name'],
                ))

    stdout.write('\n')

    if not args.force:
        pr = input('continue [y/N]? ')
        if pr.lower() not in ['yes', 'y']:
            stdout.write("okay, aborting\n")
            exit(0)

    client = kubeutil.get_client()
    extv1beta1 = extensions_v1beta1_api.ExtensionsV1beta1Api(client)
    v1 = core_v1_api.CoreV1Api(client)

    stdout.write('deleting deployment <{}/{}>: '.format(args.namespace, args.name))
    extv1beta1.delete_namespaced_deployment(args.name, args.namespace, body={})
    stdout.write('ok\n')

    if not args.all:
        exit(0)

    for res in resources:
        stdout.write('deleting {} <{}>: '.format(res['kind'], res['name']))
        if res['kind'] == 'volume':
            v1.delete_namespaced_persistent_volume_claim(
                res['name'], args.namespace, body={})
        elif res['kind'] == 'secret':
            v1.delete_namespaced_secret(res['name'], args.namespace, body={})
        elif res['kind'] == 'database':
            resource_path = ('/apis/torchbox.com/v1/namespaces/'
                            + dp['metadata']['namespace']
                            + '/databases/'
                            + res['name'])

            header_params = {}
            header_params['Accept'] = client.select_header_accept(['application/json'])
            header_params['Content-Type'] = client.select_header_content_type(['*/*'])
            header_params.update(kubeutil.config.api_key)

            (resp, code, header) = client.call_api(
                    resource_path, 'DELETE', {}, {}, header_params, None, [], _preload_content=False)
        elif res['kind'] == 'service':
            v1.delete_namespaced_service(res['name'], args.namespace)
        elif res['kind'] == 'ingress':
            extv1beta1.delete_namespaced_ingress(res['name'], args.namespace, body={})

        stdout.write('ok\n')
            
undeploy.help = "undeploy an application"
undeploy.arguments = (
    ( ('-M', '--manifest'), {
        'type': str,
        'metavar': 'FILE',
        'help': 'deploy from Kubernetes manifest with environment substitution',
    }),
    ( ('-f', '--force'), {
        'action': 'store_true',
        'help': 'do not prompt for confirmation',
    }),
    ( ('-A', '--all'), {
        'action': 'store_true',
        'help': 'undeploy attached resources',
    }),
    ( ('name',), {
        'type': str,
        'help': 'application name',
    })
)

commands = {
    'undeploy':   undeploy,
}

