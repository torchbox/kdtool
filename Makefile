# vim:set sw=8 ts=8 noet:
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.

VERSION?=	1.8.0-dev
PYTHON?=	python3
PIP?=		pip3
REPOSITORY?=	torchbox/kdtool
TAG?=		latest

# Debian has broken 'pip install --target'.  The fix makes the command
# incompatible with non-Debian systems, so it's impossible to support both.
# On Debian and derived operating systems, run 'make BROKEN_DEBIAN=yes'.
BROKEN_DEBIAN=	no

default: dist

version.py: Makefile make_version.py
	${PYTHON} make_version.py $(VERSION)

dist: version.py
	rm -rf _dist kdtool.pyz
	mkdir _dist
	if test "${BROKEN_DEBIAN}" = "yes"; then \
		${PIP} install --system --no-compile --target _dist -r requirements.txt; \
	else \
		${PIP} install --no-compile --target _dist -r requirements.txt; \
	fi
	cp -r *.py _dist/
	rm -rf _dist/*.egg-info _dist/*.dist-info
	${PYTHON} -m zipapp -p "/usr/bin/env python3" -o kdtool.pyz _dist
	chmod 755 kdtool.pyz
	@ls -l kdtool.pyz

docker-build:
	docker build -t ${REPOSITORY}:${TAG} .

docker-push:
	docker push ${REPOSITORY}:${TAG}

.PHONY: default dist build push version.py
