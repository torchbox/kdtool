# vim:set tw=8 ts=8 et:
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.

REPOSITORY?=	torchbox/gitlab-kube-deploy
TAG?=		latest

build:
	docker build -t ${REPOSITORY}:${TAG} .

push:
	docker push ${REPOSITORY}:${TAG}
