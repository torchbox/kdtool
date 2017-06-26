# Gitlab Kubernetes deploy tool

This is a helper container for deploying to Kubernetes from Gitlab.  It provides
a container with `kubectl` installed, and a tool called `deploy` that simplifies
calling `kubectl` from Gitlab pipelines.

To be useful, this requires that you've set up Kubernetes integration for your
project in Gitlab, which is documented
[here](https://docs.gitlab.com/ce/user/project/integrations/kubernetes.html).

`deploy` can deploy simple applications without needing a manifest, and it can
simplify manifests for more complicated applications.

## Simple applications

You can use `deploy` to deploy a simple application without creating a manifest.
To deploy the built image on "www.mysite.com" from `.gitlab-ci.yml`:

```
deploy -G --hostname=www.mysite.com $CI_REGISTRY_IMAGE:$CI_BUILD_REF $CI_ENVIRONMENT_SLUG
```

This will create a Deployment, Service and Ingress in the Kubernete namespace
configured in Gitlab.

The following options are accepted:

* `-G`, `--gitlab`: Take Kubernetes cluster details from Gitlab environment
 variables.
* `-A`, `--acme`: Add annotations to the Ingress to tell 
  [kube-lego](https://github.com/jetstack/kube-lego) to issue a TLS certificate.
* `-r N`, `--replicas=N`: Create N replicas of the application.
* `-P policy`, `--image-pull-policy=policy`: Set the Kubernete images pull 
  policy to `IfNotPresent` or `Always`.
* `-e VAR=VALUE`, `--env=VAR=VALUE`: Set the given environment variable in the
  Deployment.
* `-s VAR=VALUE`, `--secret=VAR=VALUE`: Set the given environment variable as a
  Kubernetes Secret referenced from the Deployment.
* `-p port`, `--port=port`: Set the port the application container listens on
  (default 80).
* `-v NAME:PATH`, `--volume=NAME:PATH`: Create a Persistent Volume Claim called
  `NAME` and mount it at `PATH`.  For this to work, your cluster must have a
  functional PVC provisioner.
* `--memory-request`: Set Kubernetes memory request.  Default 64MB.
* `--memory-limit`: Set Kubernetes memory limit.  Default 128MB.
* `--cpu-request`: Set Kubernetes CPU request.  Default 100m (0.1 cores).
* `--cpu-limit`: Set Kubernetes CPU limit.  Default 1.
* `--database=TYPE`: Attach a database of the given type, which should be
  `mysql` or `postgresql`.  This is Torchbox-specific and won't work elsewhere,
  although we hope to open source the controller that makes this work soon.
* `-U`, `--undeploy`: Delete all the resources that would have been created if
  the command was invoked without this option.

Authentication flags:

* `--htauth-user=USERNAME:PASSWORD`: Require HTTP basic authentication using
  this username and password.  This may be specified multiple times.
* `--htauth-address=1.2.3.0/24`: Reject requests from outside this IP range.
  May be specified multiple times.
* `--htauth-satisfy=<any|all>`: Control behaviour when both `--htauth-user` and
  `--htauth-address` are specified.  If `all` (default) a valid password _and_
  a whitelisted IP address are required or the connection will be rejected.  If
  `any`, either is sufficient for access.

Authentication varies greatly among Kubernetes Ingress controllers.  As far as
I know, the GKE Ingress controller doesn't support it at all.  The nginx
controller supports all the options except `--htauth-satisfy`.  The only
controller that supports all the options is
[Traffic Server](https://github.com/torchbox/k8s-ts-ingress).

This authentication is not intended to be secure: it accepts passwords in
plaintext and hashes them using FreeBSD MD5.  It's intended to prevent search
engines and curious users from finding your staging sites, not to replace proper
application-level authentication.

### Example .gitlab-ci.yml

Use Gitlab dynamic environments to deploy any branch at
`https://<branchname>.myapp-staging.com`, except for `master` which is
deployed at `https://www.myapp.com/`:

```
---
image: docker:latest
variables:
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_BUILD_REF

stages:
- build
- deploy

build:
  stage: build
  before_script:
  - docker login -u gitlab-ci-token -p $CI_BUILD_TOKEN $CI_REGISTRY
  script:
  - docker build -t $IMAGE_TAG .
  - docker push $IMAGE_TAG

deploy_production:
  stage: deploy
  only:
  - master
  environment:
    name: $CI_BUILD_REF_NAME
    url: https://www.myapp.com
  image: torchbox/gitlab-kube-deploy:latest
  script: 
  - deploy -G -r2 -A -H www.myapp.com $IMAGE_TAG $CI_ENVIRONMENT_SLUG

deploy_staging:
  stage: deploy
  only:
  - branches
  except:
  - master
  environment:
    name: $CI_BUILD_REF_NAME
    url: https://$CI_ENVIRONMENT_SLUG.myapp.com
    on_stop: undeploy_staging
  image: torchbox/gitlab-kube-deploy:latest
  script: 
  - deploy -G -A -H $CI_ENVIRONMENT_SLUG.myapp.com $IMAGE_TAG $CI_ENVIRONMENT_SLUG

undeploy_staging:
  stage: deploy
  when: manual

  environment:
    name: $CI_BUILD_REF_NAME
    action: stop

  image: torchbox/gitlab-kube-deploy:latest

  script: 
  - deploy -G --undeploy -A -H $CI_ENVIRONMENT_SLUG.myapp.com $IMAGE_TAG $CI_ENVIRONMENT_SLUG
```

## Custom manifests

`deploy`'s automatic manifest generation isn't intended to cover every possible
use case.  If you like, you can provide your own manifest; `deploy` will do
variable substitution inside the manifest.

Specifically, any string `$varname` or `${varname}` in the manifest will be
replaced with the corresponding environment variable.  This includes variables
defined in `.gitlab-ci.yml`, like `$IMAGE`, and any variables defined as Gitlab
Pipeline secrets.

A variable of the form `${varname:b64encode}` will be Base64-encoded, which is
useful for populating Kubernetes Secrets.

Here is an example manifest that assumes `DATABASE_URL` and `SECRET_KEY` have
been set as Gitlab secrets:

```
apiVersion: v1
kind: Secret
metadata:
  namespace: $KUBE_NAMESPACE
  name: $CI_ENVIRONMENT_SLUG
type: Opaque
data:
  DATABASE_URL: ${DATABASE_URL:b64encode}
  SECRET_KEY: ${SECRET_KEY:b64encode}

---

apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: $CI_ENVIRONMENT_SLUG
  namespace: $KUBE_NAMESPACE
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: $CI_ENVIRONMENT_SLUG
  template:
    metadata:
      labels:
        app: $CI_ENVIRONMENT_SLUG
    spec:
      containers:
      - name: app
        image: $IMAGE
        envFrom:
        - secretRef:
            name: $CI_ENVIRONMENT_SLUG
        ports:
        - name: http
          containerPort: 80
          protocol: TCP

---

apiVersion: v1
kind: Service
metadata:
  name: $CI_ENVIRONMENT_SLUG
  namespace: $KUBE_NAMESPACE
spec:
  type: ClusterIP
  ports:
  - name: http
    port: 80
    protocol: TCP
    targetPort: http
  selector:
    app: $CI_ENVIRONMENT_SLUG

---

apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  annotations:
    kubernetes.io/tls-acme: "true"
  name: $CI_ENVIRONMENT_SLUG
  namespace: $KUBE_NAMESPACE
spec:
  rules:
  - host: www.myapp.com
    http:
      paths:
      - backend:
          serviceName: $CI_ENVIRONMENT_SLUG
          servicePort: http
  tls:
  - hosts:
    - www.myapp.com
    secretName: ${CI_ENVIRONMENT_SLUG}-tls
```

You could use this manifest in `.gitlab-ci.yml` like this:

```
deploy_production:
  stage: deploy
  only:
  - master
  environment:
    name: $CI_BUILD_REF_NAME
    url: https://www.myapp.com
  image: torchbox/gitlab-kube-deploy:latest
  script: 
  - deploy -G --manifest=deployment.yaml $IMAGE_TAG $CI_ENVIRONMENT_SLUG
```
