FROM alpine:3.5

RUN	apk update							&& \
	apk add ca-certificates curl					&& \
	curl -Lo /usr/local/bin/kubectl https://storage.googleapis.com/kubernetes-release/release/v1.5.3/bin/linux/amd64/kubectl && \
	chmod 755 /usr/local/bin/kubectl				&& \
	apk del curl							&& \
	rm -rf /var/cache/apk/*
