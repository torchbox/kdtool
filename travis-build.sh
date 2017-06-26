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
printf '>>> Building Docker image.\n\n'
docker build --pull -t torchbox/gitlab-kube-deploy:$COMMIT .

# If this is a release, push the Docker image to Docker Hub.
if [ "$TRAVIS_PULL_REQUEST" = "false" -a -n "$TRAVIS_TAG" ]; then
	printf '####################################################################\n'
	printf '>>> Creating release.\n\n'

	docker login -u $DOCKER_USER -p $DOCKER_PASSWORD
	docker tag torchbox/gitlab-kube-deploy:$COMMIT torchbox/gitlab-kube-deploy:$TRAVIS_TAG
	docker push torchbox/gitlab-kube-deploy:$TRAVIS_TAG
	docker tag torchbox/gitlab-kube-deploy:$COMMIT torchbox/gitlab-kube-deploy:latest
	docker push torchbox/gitlab-kube-deploy:latest
fi
