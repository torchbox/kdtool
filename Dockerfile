# vim:set sw=8 ts=8 noet:
# Copyright (c) 2016-2017 Torchbox Ltd.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely. This software is provided 'as-is', without any express or implied
# warranty.
FROM alpine:3.6 AS build

RUN	apk update
RUN	apk add ca-certificates curl python3 make
WORKDIR	/usr/src/deploy
COPY	. .
RUN	make dist
RUN	curl -Lo kubectl \
		https://storage.googleapis.com/kubernetes-release/release/v1.8.0/bin/linux/amd64/kubectl

FROM alpine:3.6

COPY	--from=build /usr/src/deploy/kdtool.pyz /usr/local/bin/kdtool
COPY	--from=build /usr/src/deploy/kubectl /usr/local/bin/kubectl
RUN	apk add --no-cache ca-certificates python3
RUN	chmod 755 /usr/local/bin/kdtool /usr/local/bin/kubectl

ENTRYPOINT [ "/usr/local/bin/kdtool" ]
