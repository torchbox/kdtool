#! /bin/sh
# vim:set sw=8 ts=8 noet:
#
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.

set -e

printf '####################################################################\n'
printf '>>> Building zipapp.\n\n'

if [ -n "$TRAVIS_TAG" ]; then
	VERSION="$(echo "${TRAVIS_TAG}" | sed -e 's/^v//')"
else
	VERSION="git${TRAVIS_COMIT}"
fi

make dist VERSION="${VERSION}"

printf '####################################################################\n'
printf '>>> Building Docker image.\n\n'

docker build --pull -t torchbox/kdtool:$COMMIT .

if [ "$TRAVIS_PULL_REQUEST" = "false" ]; then
	printf '####################################################################\n'
	printf '>>> Pushing test release.\n\n'

	# Push the latest build to the 'testing' tag.
	docker login -u $DOCKER_USER -p $DOCKER_PASSWORD
	docker tag torchbox/kdtool:$COMMIT torchbox/kdtool:testing
	docker push torchbox/kdtool:testing

	# If this is a release, push the Docker image to Docker Hub.
	if [ -n "$TRAVIS_TAG" ]; then
		cp kdtool.pyz kdtool-${TRAVIS_TAG}.pyz

		printf '####################################################################\n'
		printf '>>> Creating release.\n\n'

		docker tag torchbox/kdtool:$COMMIT torchbox/kdtool:$TRAVIS_TAG
		docker push torchbox/kdtool:$TRAVIS_TAG
		docker tag torchbox/kdtool:$COMMIT torchbox/kdtool:latest
		docker push torchbox/kdtool:latest
	fi
fi
