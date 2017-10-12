# vim:set sw=2 ts=2 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.


from os import environ
from base64 import b64encode
from sys import stdout, stderr, exit
import re, yaml


# Load a YAML manifest from disk and perform environment substitution on it,
# based on the environment and our arguments.  Returns an array of items loaded
# from the YAML; this needs to be converted to a List before sending it to
# kubectl.
def load_manifest(args, filename):
  # Avoid modifying the system environment.
  menv = environ.copy()

  with open(filename, 'r') as f:
    spec = f.read()

  menv['IMAGE'] = args.image
  menv['NAME'] = args.name
  menv['NAMESPACE'] = args.namespace

  for env in args.env:
    (var, value) = env.split('=', 1)
    menv[var] = value

  def envrep(m):
    funcs = {
      'b64encode': lambda v: b64encode(v.encode('utf-8')).decode('utf-8'),
    }

    bits = m.group(2).split(':')

    try:
      var = menv[bits[0]]
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

  items = []
  for item in yaml.load_all(spec):
    items.append(item)
  return items
