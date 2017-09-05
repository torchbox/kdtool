#! /usr/bin/env python3
# vim:set sw=2 ts=2 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


# Create Kubernetes deployment manifests for a typical web application:
# deployment, service and ingress.


import argparse, json, subprocess, tempfile, re, humanfriendly
from base64 import b64encode
from os import environ
from sys import stdout, stderr, exit
from passlib.hash import md5_crypt

# GitLab 9.4 puts $KUBECONFIG in the environment, which causes kubectl to fail
# with an error when we specify --certificate-authority=.  Since we don't need
# a kubeconfig, just remove it.
if 'KUBECONFIG' in environ:
  del environ['KUBECONFIG']

parser = argparse.ArgumentParser(description='Deploy Kubernetes applications')
parser.add_argument('-N', '--namespace', type=str, default="default", help='Kubernetes namespace to deploy in')
parser.add_argument('-S', '--server', type=str, metavar='URL', help="Kubernetes API server URL")
parser.add_argument('-T', '--token', type=str, help="Kubernetes authentication token")
parser.add_argument('-C', '--ca-certificate', type=str, help="Kubernetes API server CA certificate")
parser.add_argument('-G', '--gitlab', action='store_true', help="Configure Kubernetes from Gitlab CI")
parser.add_argument('-H', '--hostname', type=str, action='append', default=[], help='Hostname to expose the application on')
parser.add_argument('-A', '--acme', action='store_true', help='Issue Let\'s Encrypt (ACME) TLS certificate')
parser.add_argument('-M', '--manifest', type=str, metavar='FILE', help='Deploy from Kubernetes manifest with environment substitution')
parser.add_argument('-r', '--replicas', type=int, default=1, help="Number of replicas to create")
parser.add_argument('-P', '--image-pull-policy', type=str, choices=('IfNotPresent', 'Always'), default='IfNotPresent', help="Image pull policy")
parser.add_argument('-e', '--env', type=str, action='append', default=[], metavar='VARNAME=VALUE', help="Set environment variable")
parser.add_argument('-s', '--secret', type=str, action='append', default=[], metavar='VARNAME=VALUE', help="Set secret environment variable")
parser.add_argument('-v', '--volume', type=str, action='append', default=[], metavar='PATH', help="Attach persistent filesystem storage at PATH")
parser.add_argument('-p', '--port', type=int, default=80, help="HTTP port the application listens on")
parser.add_argument('-j', '--json', action='store_true', help="Print JSON instead of applying to cluster")
parser.add_argument('-U', '--undeploy', action='store_true', help="Remove existing application")
parser.add_argument('-n', '--dry-run', action='store_true', help="Pass --dry-run to kubectl")
parser.add_argument('-D', '--database', type=str, choices=('mysql', 'postgresql'), help='Provision database')
parser.add_argument('--htauth-user', type=str, action='append', default=[], metavar='USERNAME:PASSWORD', help='Add HTTP authentication username/password')
parser.add_argument('--htauth-address', type=str, action='append', default=[], metavar='ipaddress[/prefix]', help='Add HTTP authentication address')
parser.add_argument('--htauth-satisfy', type=str, default='any', choices=('any', 'all'), help='HTTP authentication satisfy policy')
parser.add_argument('--htauth-realm', type=str, default='Authentication required', help='HTTP authentication realm')
parser.add_argument('--postgres', type=str, metavar='9.6', help="Attach PostgreSQL database at $DATABASE_URL")
parser.add_argument('--redis-cache', type=str, metavar='64m', help="Attach Redis database at $CACHE_URL")
parser.add_argument('--memory-request', type=str, default='none', help='Required memory allocation')
parser.add_argument('--memory-limit', type=str, default='none', help='Memory limit')
parser.add_argument('--cpu-request', type=float, default=0, help="Number of dedicated CPU cores")
parser.add_argument('--cpu-limit', type=float, default=0, help='CPU core use limit')
parser.add_argument('image', type=str, help='Docker image to deploy')
parser.add_argument('name', type=str, help='Application name')
args = parser.parse_args()

labels = {
  'app': args.name,
}

def strip_hostname(hostname):
  # Strip https?:// from a hostname so --hostname=<URL> works.
  return re.sub(r"^https?://([^/]*)(/.*)?$", r'\1', hostname)

if args.gitlab:
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

if args.manifest:
  with open(args.manifest, 'r') as f:
    spec = f.read()

  environ['IMAGE'] = args.image
  environ['NAME'] = args.name
  environ['NAMESPACE'] = args.namespace

  for env in args.env:
    (var, value) = env.split('=', 1)
    environ[var]= value

  def envrep(m):
    funcs = {
      'b64encode': lambda v: b64encode(v.encode('utf-8')).decode('utf-8'),
    }

    bits = m.group(2).split(':')

    try:
      var = environ[bits[0]]
    except KeyError:
      stderr.write(args.manifest+ ": $" + bits[0] + " not in environment.\n")
      exit(1)

    if len(bits) > 1:
      if bits[1] not in funcs:
        stderr.write(args.manifest + ": function " + bits[1] + " unknown.\n")
      return funcs[bits[1]](var, *bits[2:])
    else:
      return var

  spec = re.sub(r"\$({)?([A-Za-z_][A-Za-z0-9_:]+)(?(1)})", envrep, spec)
else:
  environment = []
  items = []
  containers = []
  volumes = []
  volume_mounts = []

  secrets = {
    'apiVersion': 'v1',
    'kind': 'Secret',
    'metadata': {
      'name': args.name,
      'namespace': args.namespace,
    },
    'type': 'Opaque',
    'data': {}
  }

  for env in args.env:
    envbits = env.split('=', 1)
    if len(envbits) == 1:
      envbits.append(environ.get(envbits[0], ''))
    environment.append({ 'name': envbits[0], 'value': envbits[1] })

  for secret in args.secret:
    (var, value) = secret.split('=', 1)
    environment.append({
      'name': var,
      'valueFrom': {
        'secretKeyRef': {
          'name': args.name,
          'key': var,
        },
      },
    })
    secrets['data'][var] = b64encode(value.encode('utf-8')).decode('ascii')

  items.append(secrets)

  if len(args.htauth_user):
    htpasswd = ""
    for auth in args.htauth_user:
      (u,p) = auth.split(":", 1)
      htpasswd += u + ":" + md5_crypt.hash(p) + "\n"

    items.append({
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

# Add Postgres if requested
  if args.postgres is not None:
    containers.append({
      'name': 'postgres',
      'image': "postgres:" + args.postgres + "-alpine",
      'imagePullPolicy': 'Always',
      'volumeMounts': [
        {
          'name': 'postgres',
          'mountPath': '/var/lib/postgresql/data',
        },
      ],
    })
    environment.append({
      'name': 'DATABASE_URL',
      'value': 'postgres://postgres:postgres@localhost/postgres',
    })

    # Mount storage for Postgres
    items.append({
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
    })
    volumes.append({
      'name': 'postgres',
      'persistentVolumeClaim': {
        'claimName': args.name + '-postgres',
      }
    })

# Redis
  if args.redis_cache is not None:
    containers.append({
      'name': 'redis',
      'image': "redis:alpine",
      'imagePullPolicy': 'Always',
      'args': [
        '--maxmemory', args.redis_cache,
        '--maxmemory-policy', 'allkeys-lru',
      ],
    })
    environment.append({
      'name': 'CACHE_URL',
      'value': 'redis://localhost:6379/0',
    })

# Database
  if args.database is not None:
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

    environment.append({
      'name': 'DATABASE_URL',
      'valueFrom': {
        'secretKeyRef': {
          'name': args.name+'-database',
          'key': 'database-url',
        },
      },
    })

# Add PVCs for any volumes requested.
  for volume in args.volume:
    (volslug, path) = volume.split(':', 1)
    name = args.name + '-' + volslug

    items.append({
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
    })

    # Mount this PVC in the container
    volumes.append({
      'name': volslug,
      'persistentVolumeClaim': {
        'claimName': name,
      }
    })
    volume_mounts.append({
      'name': volslug,
      'mountPath': path,
    })


# Application container
  app_container = {
    'name': 'web',
    'image': args.image,
    'imagePullPolicy': args.image_pull_policy,
    'env': environment,
    'volumeMounts': volume_mounts,
    'ports': [
      {
        'name': 'http',
        'containerPort': args.port,
        'protocol': 'TCP',
      }
    ],
    'resources': {
      'limits': {
      },
      'requests': {
      },
    },
  }

  if args.cpu_limit:
    app_container['resources']['limits']['cpu'] = args.cpu_limit
  if args.cpu_request:
    app_container['resources']['requests']['cpu'] = args.cpu_request
  if args.memory_limit != 'none':
    app_container['resources']['limits']['memory'] = humanfriendly.parse_size(args.memory_limit, binary=True)
  if args.memory_request != 'none':
    app_container['resources']['requests']['memory'] = humanfriendly.parse_size(args.memory_request, binary=True)
  containers.append(app_container)

  items.append({
    'apiVersion': 'extensions/v1beta1',
    'kind': 'Deployment',
    'metadata': {
      'labels': labels,
      'name': args.name,
      'namespace': args.namespace,
    },
    'spec': {
      'replicas': args.replicas,
      'selector': {
        'matchLabels': labels,
      },
      'strategy': {
        'type': 'RollingUpdate',
        'rollingUpdate': {
          'maxSurge': 1,
          'maxUnavailable': 0,
        },
      },
      'template': {
        'metadata': {
          'labels': labels,
          },
        'spec': {
          'containers': containers,
          'volumes': volumes,
        },
      },
    },
  })

  items.append({
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
      'selector': labels,
      'type': 'ClusterIP',
    },
  })

  if len(args.hostname) > 0:
    ingress = {
      'apiVersion': 'extensions/v1beta1',
      'kind': 'Ingress',
      'metadata': {
        'name': args.name,
        'namespace': args.namespace,
        'annotations': {},
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

    if len(args.htauth_address):
      ingress['metadata']['annotations']['ingress.kubernetes.io/whitelist-source-range'] = ",".join(args.htauth_address)

    if len(args.htauth_user):
      ingress['metadata']['annotations'].update({
        'ingress.kubernetes.io/auth-type': 'basic',
        'ingress.kubernetes.io/auth-realm': args.htauth_realm,
        'ingress.kubernetes.io/auth-satisfy': args.htauth_satisfy,
        'ingress.kubernetes.io/auth-secret': args.name+'-htaccess',
      })

    if args.acme:
      ingress['metadata']['annotations']['kubernetes.io/tls-acme'] = 'true'
      ingress['spec']['tls'] = [{
        'hosts': [ strip_hostname(hostname) ],
        'secretName': strip_hostname(hostname) + '-tls',
      } for hostname in args.hostname]

    items.append(ingress)

  spec = json.dumps(
    {
      'apiVersion': 'v1',
      'kind': 'List',
      'items': items,
    })

if args.json:
  print(spec)
else:
  kargs = ['/usr/local/bin/kubectl']

  if args.undeploy:
    kargs.append('delete')
  else:
    kargs.append('apply')

  if args.server:
    kargs.append('--server='+args.server)
  if args.token:
    kargs.append('--token='+args.token)
  if args.ca_certificate:
    kargs.append('--certificate-authority='+args.ca_certificate)
  if args.namespace:
    kargs.append('--namespace='+args.namespace)

  if args.dry_run:
    kargs.append('--dry-run')

  kargs.extend(['-f', '-'])

  kubectl = subprocess.Popen(kargs, stdin=subprocess.PIPE)
  kubectl.communicate(spec.encode('utf-8'))
  exit(kubectl.returncode)
