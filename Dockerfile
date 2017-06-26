# vim:set sw=8 ts=8 noet:
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.
FROM alpine:3.5

RUN	apk update							&& \
	apk add ca-certificates curl python3				&& \
	pip3 install humanfriendly passlib				&& \
	curl -Lo /usr/local/bin/kubectl \
		https://storage.googleapis.com/kubernetes-release/release/v1.6.6/bin/linux/amd64/kubectl && \
	chmod 755 /usr/local/bin/kubectl				&& \
	apk del curl							&& \
	rm -rf /var/cache/apk/*

COPY	deploy.py /usr/local/bin/deploy
RUN	chmod 755 /usr/local/bin/deploy
