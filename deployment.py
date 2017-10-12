# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


import json, kubernetes

import kubeutil

# get_deployment: return the named deployment.
def get_deployment(namespace, name):
    api_client = kubeutil.get_client()

    # We can't use the normal client API here because it returns Python objects
    # that can't be converted back into JSON.  Instead, fetch the JSON by hand.
    resource_path = ('/apis/extensions/v1beta1/namespaces/'
                    + namespace
                    + '/deployments/'
                    + name)

    header_params = {}
    header_params['Accept'] = api_client.select_header_accept(['application/json'])
    header_params['Content-Type'] = api_client.select_header_content_type(['*/*'])
    header_params.update(kubeutil.config.api_key)

    (resp, code, header) = api_client.call_api(
            resource_path, 'GET', {}, {}, header_params, None, [], _preload_content=False)
    dp = json.loads(resp.data.decode('utf-8'))

    return dp

# get_replicasets: return all the active replicasets for a deployment.
# old replicasets (with zero replicas) are not included.
def get_replicasets(dp):
    ret = []

    api_client = kubeutil.get_client()

    # We can't use the normal client API here because it returns Python objects
    # that can't be converted back into JSON.  Instead, fetch the JSON by hand.
    resource_path = ('/apis/extensions/v1beta1/namespaces/'
                    + dp['metadata']['namespace']
                    + '/replicasets')

    header_params = {}
    header_params['Accept'] = api_client.select_header_accept(['application/json'])
    header_params['Content-Type'] = api_client.select_header_content_type(['*/*'])
    header_params.update(kubeutil.config.api_key)

    (resp, code, header) = api_client.call_api(
            resource_path, 'GET', {}, {}, header_params, None, [], _preload_content=False)

    rslist = json.loads(resp.data.decode('utf-8'))

    for rs in rslist['items']:
        md = rs['metadata']

        # Check if this RS is owned by the correct deployment.
        if 'ownerReferences' not in md:
            continue
        has_owner = False
        for owner in md['ownerReferences']:
            if owner['kind'] == 'Deployment' and owner['name'] == dp['metadata']['name']:
                has_owner = True
                break
        if not has_owner:
            continue

        if rs['spec']['replicas'] == 0:
            continue

        ret.append(rs)

    return ret


# get_rs_pods: get all the pods for a replicaset.
def get_rs_pods(rs):
    ret = []

    api_client = kubeutil.get_client()

    # We can't use the normal client API here because it returns Python objects
    # that can't be converted back into JSON.  Instead, fetch the JSON by hand.
    resource_path = ('/api/v1/namespaces/'
                    + rs['metadata']['namespace']
                    + '/pods')

    header_params = {}
    header_params['Accept'] = api_client.select_header_accept(['application/json'])
    header_params['Content-Type'] = api_client.select_header_content_type(['*/*'])
    header_params.update(kubeutil.config.api_key)

    (resp, code, header) = api_client.call_api(
            resource_path, 'GET', {}, {}, header_params, None, [], _preload_content=False)

    podlist = json.loads(resp.data.decode('utf-8'))
    for pod in podlist['items']:
        md = pod['metadata']
        if 'ownerReferences' not in md:
            continue

        has_owner = False

        for owner in md['ownerReferences']:
            if owner['kind'] != 'ReplicaSet':
                continue
            if owner['name'] != rs['metadata']['name']:
                continue
            has_owner = True
            break

        if not has_owner:
            continue

        ret.append(pod)

    return ret
