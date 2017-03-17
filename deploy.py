#! /usr/bin/env python3
# vim:set sw=2 ts=2 et:

# Create Kubernetes deployment manifests for a typical web application: 
# deployment, service and ingress.

import argparse, json, subprocess, humanfriendly

parser = argparse.ArgumentParser(description='Deploy Kubernetes applications')
parser.add_argument('-N', '--namespace', type=str, default="default", help='Kubernetes namespace to deploy in')
parser.add_argument('-S', '--server', type=str, help="Kubernetes API server URL")
parser.add_argument('-T', '--token', type=str, help="Kubernetes authentication token")
parser.add_argument('-C', '--ca-certificate', type=str, help="Kubernetes API server CA certificate")
parser.add_argument('-H', '--hostname', type=str, action='append', default=[], help='Hostname to expose the application on')
parser.add_argument('-A', '--acme', action='store_true', help='Issue Let\'s Encrypt (ACME) TLS certificate')
parser.add_argument('-r', '--replicas', type=int, default=1, help="Number of replicas to create")
parser.add_argument('-P', '--image-pull-policy', type=str, choices=('IfNotPresent', 'Always'), default='IfNotPresent', help="Image pull policy")
parser.add_argument('-e', '--env', type=str, action='append', default=[], help="Set environment variable (VAR=VALUE)")
parser.add_argument('-p', '--port', type=int, default=80, help="HTTP port the application listens on")
parser.add_argument('-j', '--json', action='store_true', help="Print JSON instead of applying to cluster")
parser.add_argument('-U', '--undeploy', action='store_true', help="Remove existing application")
parser.add_argument('-n', '--dry-run', action='store_true', help="Pass --dry-run to kubectl")
parser.add_argument('--memory-request', type=str, default='64M', help='Required memory allocation')
parser.add_argument('--memory-limit', type=str, default='128M', help='Memory limit')
parser.add_argument('--cpu-request', type=float, default=0.1, help="Number of dedicated CPU cores")
parser.add_argument('--cpu-limit', type=float, default=1, help='CPU core use limit')
parser.add_argument('image', type=str, help='Docker image to deploy')
parser.add_argument('name', type=str, help='Application name')
args = parser.parse_args()

labels = {
  'app': args.name,
}

environment = []
for env in args.env:
  (var, value) = env.split('=', 1)
  environment.append({ 'name': var, 'value': value })

items = []

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
        'containers': [
          {
            'name': 'web',
            'image': args.image,
            'imagePullPolicy': args.image_pull_policy,

            'env': environment,
            'ports': [
              {
                'name': 'http',
                'containerPort': args.port,
                'protocol': 'TCP',
              }
            ],
            'resources': {
              'limits': {
                'cpu': args.cpu_limit,
                'memory': humanfriendly.parse_size(args.memory_limit, binary=True),
              },
              'requests': {
                'cpu': args.cpu_request,
                'memory': humanfriendly.parse_size(args.memory_request, binary=True),
              },
            },
          },
        ],
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
  items.append({
    'apiVersion': 'extensions/v1beta1',
    'kind': 'Ingress',
    'metadata': {
#    annotations:
#      kubernetes.io/tls-acme: "true"
      'name': args.name,
      'namespace': args.namespace,
    },
    'spec': {
      'rules': [
        {
          'host': hostname,
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
  })

spec = json.dumps(
  {
    'apiVersion': 'v1',
    'kind': 'List',
    'items': items,
  })

if args.json:
  print(spec)
else:
  kargs = ['kubectl']

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
