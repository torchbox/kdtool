REPOSITORY?=	registry.git.torchbox.com/sysadmin/kubectl
TAG?=		latest

build:
	docker build -t ${REPOSITORY}:${TAG} .

push:
	docker push ${REPOSITORY}:${TAG}
