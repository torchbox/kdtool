# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


import json, kubernetes
from kubernetes.client.apis import core_v1_api, extensions_v1beta1_api
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

    resources = None
    try:
        resources = json.loads(dp['metadata']['annotations']['kdtool.torchbox.com/attached-resources'])
    except KeyError:
        exit(0)
    except ValueError as e:
        stderr.write("warning: could not decode kdtool.torchbox.com/attached-resources annotation: {0}\n".format(str(e)))
        exit(0)

    if len(resources) == 0:
        exit(0)

    stdout.write("\nattached resources:\n")

    client = kubeutil.get_client()
    v1 = core_v1_api.CoreV1Api(client)
    extv1beta1 = extensions_v1beta1_api.ExtensionsV1beta1Api(client)

    services = [resource['name'] for resource in resources if resource['kind'] == 'service']
    for svc_name in services:
        service = v1.read_namespaced_service(svc_name, args.namespace)
        stdout.write("  service {0}: selector is ({1})\n".format(
            service.metadata.name,
            ", ".join([ k+"="+v for k,v in service.spec.selector.items() ]),
        ))
        for port in service.spec.ports:
            stdout.write("    port {0}: {1}/{2} -> {3}\n".format(
                port.name,
                port.port,
                port.protocol,
                port.target_port))

    ingresses = [resource['name'] for resource in resources if resource['kind'] == 'ingress']

    for ing_name in ingresses:
        ingress = extv1beta1.read_namespaced_ingress(ing_name, args.namespace)
        stdout.write("  ingress {0}:\n".format(ingress.metadata.name))
        for rule in ingress.spec.rules:
            stdout.write("    http[s]://{0} -> {1}/{2}:{3}\n".format(
                rule.host,
                ingress.metadata.namespace,
                rule.http.paths[0].backend.service_name,
                rule.http.paths[0].backend.service_port,
            ))

    volumes = [resource['name'] for resource in resources if resource['kind'] == 'volume']

    for vol_name in volumes:
        volume = v1.read_namespaced_persistent_volume_claim(vol_name, args.namespace)
        if volume.status:
            stdout.write("  volume {0}: mode is {1}, size {2}, phase {3}\n".format(
                volume.metadata.name,
                ",".join(volume.status.access_modes),
                volume.status.capacity['storage'],
                volume.status.phase,
            ))
        else:
            stdout.write("  volume {0} is unknown (not provisioned)\n".format(
                volume.metadata.name,
            ))

    databases = [resource['name'] for resource in resources if resource['kind'] == 'database']

    for db_name in databases:
        resource_path = ('/apis/torchbox.com/v1/namespaces/'
                        + dp['metadata']['namespace']
                        + '/databases/'
                        + db_name)

        header_params = {}
        header_params['Accept'] = client.select_header_accept(['application/json'])
        header_params['Content-Type'] = client.select_header_content_type(['*/*'])
        header_params.update(kubeutil.config.api_key)

        (resp, code, header) = client.call_api(
                resource_path, 'GET', {}, {}, header_params, None, [], _preload_content=False)

        database = json.loads(resp.data.decode('utf-8'))
        if 'status' in database:
            stdout.write("  database {0}: type {1}, phase {2} (on server {3})\n".format(
                database['metadata']['name'],
                database['spec']['type'],
                database['status']['phase'],
                database['status']['server'],
            ))
        else:
            stdout.write("  database {0}: type {1}, unknown (not provisioned)\n".format(
                database['metadata']['name'],
                database['spec']['type'],
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
