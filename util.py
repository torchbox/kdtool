#! /usr/bin/env python3
# vim:set sw=2 ts=2 et:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.

import re

def strip_hostname(hostname):
  # Strip https?:// from a hostname so --hostname=<URL> works.
  return re.sub(r"^https?://([^/]*)(/.*)?$", r'\1', hostname)
