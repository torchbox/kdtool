#! /usr/bin/env python3
# vim:set sw=4 ts=4 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.

import subprocess, json, humanfriendly
from base64 import b64encode
from sys import stdin, stdout, stderr
from os import environ
from passlib.hash import md5_crypt

import kubectl
from util import strip_hostname


# make_service: create a Service resource for the given arguments.
def make_service(args):
    service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': args.name,
            'namespace': args.namespace,
        },
        'spec': {
            'ports': [
                {
                    'name': 'http',
                    'port': 80,
                    'protocol': 'TCP',
                    'targetPort': 'http',
                },
            ],
            'selector': {
                'app': args.name
            },
            'type': 'ClusterIP',
        },
    }

    return service

# make_ingress: create an Ingress resource for the given arguments.
# returns: API object data structure
def make_ingress(args):
    # The basic Ingress
    ingress = {
      'apiVersion': 'extensions/v1beta1',
      'kind': 'Ingress',
      'metadata': {
        'name': args.name,
        'namespace': args.namespace,
        'annotations': {}
      },
      'spec': {
        'rules': [
          {
            'host': strip_hostname(hostname),
            'http': {
              'paths': [
                {
                  'backend': {
                    'serviceName': args.name,
                    'servicePort': 80,
                  },
                },
              ],
            },
          } for hostname in args.hostname
        ],
      },
    }

    # Add htauth

    secrets = []

    if len(args.htauth_address):
        ingress['metadata']['annotations']\
            ['ingress.kubernetes.io/whitelist-source-range'] = \
                ",".join(args.htauth_address)

    if len(args.htauth_user):
        ingress['metadata']['annotations'].update({
            'ingress.kubernetes.io/auth-type': 'basic',
            'ingress.kubernetes.io/auth-realm': args.htauth_realm,
            'ingress.kubernetes.io/auth-satisfy': args.htauth_satisfy,
            'ingress.kubernetes.io/auth-secret': args.name+'-htaccess',
        })

        htpasswd = ""
        for auth in args.htauth_user:
            (u,p) = auth.split(":", 1)
            htpasswd += u + ":" + md5_crypt.hash(p) + "\n"

        secrets.append({
            'apiVersion': 'v1',
            'kind': 'Secret',
            'metadata': {
                'name': args.name+'-htaccess',
                'namespace': args.namespace,
            },
            'type': 'Opaque',
            'data': {
                'auth': b64encode(htpasswd.encode('utf-8')).decode('ascii'),
            },
        })

    # Add ACME TLS
    if args.acme:
      ingress['metadata']['annotations']['kubernetes.io/tls-acme'] = 'true'
      ingress['spec']['tls'] = [{
        'hosts': [ strip_hostname(hostname) ],
        'secretName': strip_hostname(hostname) + '-tls',
      } for hostname in args.hostname]

    return (ingress, secrets)


# make_pod: create a basic Pod for the given arguments
def make_pod(args):
    pod = {
        'metadata': {
            'labels': {
                'app': args.name,
            }
        },
        'spec': {
            'containers': [],
            'volumes': [],
        },
    }

    return pod


# make_deployment: convert the given Pod into a Deployment for the given args.
def make_deployment(pod, args):
    deployment = {
        'apiVersion': 'extensions/v1beta1',
        'kind': 'Deployment',
        'metadata': {
            'name': args.name,
            'namespace': args.namespace,
        },
        'spec': {
            'replicas': args.replicas,
            'selector': {
                'matchLabels': {
                    'app': args.name,
                },
            },
            'template': pod,
        },
    }

    if args.strategy == 'rollingupdate':
        deployment['spec']['strategy'] = {
            'type': 'RollingUpdate',
            'rollingUpdate': {
                'maxSurge': 1,
                'maxUnavailable': 0,
            },
        }
    else:
        deployment['spec']['strategy'] = {
            'type': 'Recreate',
        }

    return deployment


# make_pvc: create a PVC from the given argument
def make_pvc(arg, args):
    (volslug, path) = arg.split(':', 1)
    name = args.name + '-' + volslug

    pvc = {
      'apiVersion': 'v1',
      'kind': 'PersistentVolumeClaim',
      'metadata': {
        'namespace': args.namespace,
        'name': name,
      },
      'spec': {
        'accessModes': [ 'ReadWriteMany' ],
        'resources': {
          'requests': {
            'storage': '1Gi',
          },
        },
      },
    }

    pvcvolume = {
        'name': volslug,
        'persistentVolumeClaim': {
            'claimName': name,
        }
    }

    pvcmount = {
        'name': volslug,
        'mountPath': path,
    }

    return (pvc, pvcvolume, pvcmount)


# make_app_container: create the application container.
def make_app_container(args):
    # We add some empty values here so it's easier to modify this template later
    app_container = {
        'name': 'app',
        'image': args.image,
        'imagePullPolicy': args.image_pull_policy,
        'resources': {
            'limits': {},
            'requests': {},
        },
        'volumeMounts': [],
        'env': [],
        'envFrom': [],
    }

    # Resource limits
    if args.cpu_limit:
        app_container['resources']['limits']['cpu'] = args.cpu_limit
    if args.cpu_request:
        app_container['resources']['requests']['cpu'] = args.cpu_request
    if args.memory_limit != 'none':
        app_container['resources']['limits']['memory'] = \
            humanfriendly.parse_size(args.memory_limit, binary=True)
    if args.memory_request != 'none':
        app_container['resources']['requests']['memory'] = \
            humanfriendly.parse_size(args.memory_request, binary=True)

    return app_container


# make_redis_container: create a Redis container based on args.
def make_redis_container(args):
    container = {
        'name': 'redis',
        'image': "redis:alpine",
        'imagePullPolicy': 'Always',
        'args': [
            '--maxmemory', args.redis_cache,
            '--maxmemory-policy', 'allkeys-lru',
        ],
    }

    env = {
        'name': 'CACHE_URL',
        'value': 'redis://localhost:6379/0',
    }

    return (container, env)


# make_postgres: create a Postgres container for the given args.
def make_postgres(args):
    postgres = {
      'name': 'postgres',
      'image': "postgres:" + args.postgres + "-alpine",
      'imagePullPolicy': 'Always',
      'volumeMounts': [
        {
          'name': 'postgres',
          'mountPath': '/var/lib/postgresql/data',
        },
      ],
    }

    env = {
      'name': 'DATABASE_URL',
      'value': 'postgres://postgres:postgres@localhost/postgres',
    }

    pvc = {
      'apiVersion': 'v1',
      'kind': 'PersistentVolumeClaim',
      'metadata': {
        'namespace': args.namespace,
        'name': args.name + '-postgres',
      },
      'spec': {
        'accessModes': [ 'ReadWriteMany' ],
        'resources': {
          'requests': {
            'storage': '1Gi',
          },
        },
      },
    }

    volume = {
      'name': 'postgres',
      'persistentVolumeClaim': {
        'claimName': args.name + '-postgres',
      }
    }

    return (postgres, env, volume, pvc)


# make_secret: create a Secret object based on args.
def make_secret(args):
    secret = {
        'apiVersion': 'v1',
        'kind': 'Secret',
        'metadata': {
            'name': args.name,
            'namespace': args.namespace,
        },
        'type': 'Opaque',
        'data': {}
    }

    for s in args.secret:
        (var, value) = s.split('=', 1)
        secret['data'][var] = b64encode(value.encode('utf-8')).decode('ascii')

    return secret


# make_database: create a torchbox.com/v1.Database based on args.
def make_database(args):
    # Due to Kubernetes bug #53379 (https://github.com/kubernetes/kubernetes/issues/53379)
    # we cannot unconditionally include the database in the manifest; it will
    # fail to apply correctly when the database provisioner is using CRD
    # instead of TPR.  As a workaround, attempt to check whether the database
    # already exists.  This is not a very good check because any failure of
    # kubectl will be treated as the database not existing, but it will do to
    # make deployments work until the Kubernetes bug is fixed.
    #
    # This should be removed once #53379 is fixed, and we will mark the
    # affected Kubernetes releases as unsupported for -D.
    provision_db = True
    items = []

    if args.undeploy == False:
        stdout.write('checking if database already exists (bug #53379 workaround)...\n')
        kargs = kubectl.get_kubectl_args(args)
        kargs.extend([ 'get', 'database', args.name ])
        kubectl_p = subprocess.Popen(kargs,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        kubectl_p.communicate()

        if kubectl_p.returncode == 0:
            stdout.write('database exists; will not replace\n')
            provision_db = False
        else:
            stdout.write('database does not exist; will create\n')

    if provision_db:
        items.append({
            'apiVersion': 'torchbox.com/v1',
            'kind': 'Database',
            'metadata': {
            'namespace': args.namespace,
            'name': args.name,
        },
        'spec': {
            'class': 'default',
            'secretName': args.name+'-database',
            'type': args.database,
        },
    })

    env = {
        'name': 'DATABASE_URL',
        'valueFrom': {
            'secretKeyRef': {
                'name': args.name+'-database',
                'key': 'database-url',
            },
        },
    }

    return (items, env)


# make_manifest: create a manifest based on our arguments.
def make_manifest(args):
    items = []

    pod = make_pod(args)
    app = make_app_container(args)
    pod['spec']['containers'].append(app)

    # Configure any requested PVCs
    for vol in args.volume:
        (pvc, pvcvolume, pvcmount) = make_pvc(vol, args)
        items.append(pvc)

        app['volumeMounts'].append(pvcmount)
        pod['spec']['volumes'].append(pvcvolume)

    # Add Secret environment variables
    if len(args.secret) > 0:
        secret = make_secret(args)
        items.append(secret)
        app['envFrom'].append({
            'secretRef': {
                'name': args.name,
            }
        })

    # Add (non-secret) environment variables
    for env in args.env:
        envbits = env.split('=', 1)
        if len(envbits) == 1:
            envbits.append(environ.get(envbits[0], ''))
        app['env'].append({
            'name': envbits[0],
            'value': envbits[1]
        })

    if args.database is not None:
        (db_items, db_env) = make_database(args)
        items.extend(db_items)
        app['env'].append(db_env)

    # Add Redis container
    if args.redis_cache is not None:
        (redis, redis_env) = make_redis_container(args)
        pod['spec']['containers'].append(redis)
        app['env'].append(redis_env)

    # Add Postgres container
    if args.postgres is not None:
        (postgres, pg_env, pg_volume, pg_pvc) = make_postgres(args)
        pod['spec']['containers'].append(postgres)
        pod['spec']['volumes'].append(pg_volume)
        app['env'].append(pg_env)
        items.append(pg_pvc)

    # Create our deployment last, so it can reference other resources.
    deployment = make_deployment(pod, args)
    items.append(deployment)

    # If any hostnames are configured, create a Service and some Ingresses.
    if len(args.hostname):
        app['ports'] = [
            {
                'name': 'http',
                'containerPort': args.port,
                'protocol': 'TCP',
            }
        ]
        items.append(make_service(args))
        (ingress, secrets) = make_ingress(args)
        items.append(ingress)
        items.extend(secrets)

    # Convert our items array into a List.
    spec = {
        'apiVersion': 'v1',
        'kind': 'List',
        'items': items,
    }

    return spec


# Deploy an application.
def deploy(args):
    if args.manifest:
        spec = load_manifest(args, args.manifest)
    else:
        spec = make_manifest(args)

    if args.json:
        print(json.dumps(spec))
        exit(0)
    else:
        exit(kubectl.apply_manifest(spec, args))

deploy.help = "deploy an application"
deploy.arguments = (
    ( ('-H', '--hostname'), {
        'type': str,
        'action': 'append',
        'default': [],
        'help': 'Hostname to expose the application on'
    }),
    ( ('-A', '--acme'), {
        'action': 'store_true',
        'help': 'Issue Let\'s Encrypt (ACME) TLS certificate',
    }),
    ( ('-M', '--manifest'), {
        'type': str,
        'metavar': 'FILE',
        'help': 'Deploy from Kubernetes manifest with environment substitution',
    }),
    ( ('-r', '--replicas'), {
        'type': int,
        'default': 1,
        'help': 'Number of replicas to create',
    }),
    ( ('-P', '--image-pull-policy'), {
        'type': str,
        'choices': ('IfNotPresent', 'Always'),
        'default': 'IfNotPresent',
        'help': 'Image pull policy',
    }),
    ( ('-e', '--env'), {
        'type': str,
        'action': 'append',
        'default': [],
        'metavar': 'VARNAME=VALUE',
        'help': 'Set environment variable',
    }),
    ( ('-s', '--secret'), {
        'type': str,
        'action': 'append',
        'default': [],
        'metavar': 'VARNAME=VALUE',
        'help': 'Set secret environment variable',
    }),
    ( ('-v', '--volume'), {
        'type': str,
        'action': 'append',
        'default': [],
        'metavar': 'PATH',
        'help': 'Attach persistent filesystem storage at PATH',
    }),
    ( ('-p', '--port'), {
        'type': int,
        'default': 80,
        'help': 'HTTP port the application listens on',
    }),
    ( ('-j', '--json'), {
        'action': 'store_true',
        'help': 'Print JSON instead of applying to cluster',
    }),
    ( ('-U', '--undeploy'), {
        'action': 'store_true',
        'help': 'Remove existing application',
    }),
    ( ('-n', '--dry-run'), {
        'action': 'store_true',
        'help': 'Pass --dry-run to kubectl',
    }),
    ( ('-D', '--database'), {
        'type': str,
        'choices': ('mysql', 'postgresql'),
        'help': 'Provision database',
    }),
    ( ('--htauth-user',), {
        'type': str,
        'action': 'append',
        'default': [],
        'metavar': 'USERNAME:PASSWORD',
        'help': 'Add HTTP authentication username/password',
    }),
    ( ('--htauth-address',), {
        'type': str,
        'action': 'append',
        'default': [],
        'metavar': 'ipaddress[/prefix]',
        'help': 'Add HTTP authentication address',
    }),
    ( ('--htauth-satisfy',), {
        'type': str,
        'default': 'any',
        'choices': ('any', 'all'),
        'help': 'HTTP authentication satisfy policy',
    }),
    ( ('--htauth-realm',), {
        'type': str,
        'default': 'Authentication required',
        'help': 'HTTP authentication realm',
    }),
    ( ('--postgres',), {
        'type': str,
        'metavar': '9.6',
        'help': 'Attach PostgreSQL database at $DATABASE_URL',
    }),
    ( ('--redis-cache',), {
        'type': str,
        'metavar': '64m',
        'help': 'Attach Redis database at $CACHE_URL',
    }),
    ( ('--memory-request',), {
        'type': str,
        'default': 'none',
        'help': 'Required memory allocation',
    }),
    ( ('--memory-limit',), {
        'type': str,
        'default': 'none',
        'help': 'Memory limit',
    }),
    ( ('--cpu-request',), {
        'type': float,
        'default': 0,
        'help': 'Number of dedicated CPU cores',
    }),
    ( ('--cpu-limit',), {
        'type': float,
        'default': 0,
        'help': 'CPU core use limit',
    }),
    ( ('--strategy',), {
        'type': str,
        'choices': ('rollingupdate', 'recreate'),
        'default': 'rollingupdate',
        'help': 'Deployment update strategy',
    }),
    ( ('image',), {
        'type': str,
        'help': 'Docker image to deploy',
    }),
    ( ('name',), {
        'type': str,
        'help': 'Application name',
    })
)

commands = {
    'deploy':   deploy,
}
