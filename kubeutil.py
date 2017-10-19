# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


from sys import stdout, stderr, exit
import kubernetes, json, urllib3

config = kubernetes.client.Configuration()

# configure: set configuration based on args.
def configure(args):
    try:
        kubernetes.config.kube_config.load_kube_config(
            client_configuration=config,
            context=args.context)
    except:
        stderr.write("warning: could not load kubeconfig\n")
        args.server = 'http://localhost:8080'

    if args.server:
        config.host = args.server
    if args.token:
        config.api_key['authorization'] = "bearer " + args.token
    if args.ca_certificate:
        config.ssl_ca_cert = args.ca_certificate

# get_client: return a Kubernetes API client.
def get_client():
    client = kubernetes.client.ApiClient(config=config)
    return client

# get_error: try to extract a printable error message from an exception.
def get_error(exc):
    if isinstance(exc, kubernetes.client.rest.ApiException):
        try:
            body = exc.body.decode('utf-8')
            d = json.loads(body)
            return d['message']
        except:
            return exc.reason

    if isinstance(exc, urllib3.exceptions.HTTPError):
        return exc.args[0]

    return str(exc)
