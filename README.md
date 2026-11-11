# KubeCon demo: `crossplane * simulate`

## Setup (pre talk)

1. Start the project:

    ```shell
    cd project && crossplane project run --extra-resources extra-resources/
    ```

2. Apply AWS credentials:

    ```shell
    kubectl -n crossplane-system create secret generic aws-credentials \
        --from-file=credentials=$HOME/tmp/aws-creds.txt --dry-run=client -o yaml | \
        kubectl apply -f -
    ```

3. Apply the teams' resources:

    ```shell
    kubectl apply -f examples/teams.yaml
    ```

## Lay of the land

Each application team needs a "network". In our AWS setup this means three
resources: a VPC, a subnet, and a security group. The platform team has used
Crossplane to build an abstraction for this.

Each team creates a composite resource called `Network`:

```shell
$ kubectl get networks.kubecon.example.org -A
NAMESPACE   NAME   SYNCED   READY   COMPOSITION                    AGE
team-a      web    True     True    networks.kubecon.example.org   108s
team-b      web    True     True    networks.kubecon.example.org   108s
team-c      web    True     True    networks.kubecon.example.org   108s
```

Crossplane has composed VPCs, subnets, and security groups for these networks:

```shell
$ kubectl get managed -A
NAMESPACE   NAME                                         SYNCED   READY   EXTERNAL-NAME          AGE
team-a      securitygroup.ec2.aws.m.upbound.io/web-web   True     True    sg-093fc45c3475bc1ab   2m33s
team-b      securitygroup.ec2.aws.m.upbound.io/web-web   True     True    sg-05e8240d805533884   3m32s
team-c      securitygroup.ec2.aws.m.upbound.io/web-web   True     True    sg-01b2291c100430373   2m46s

NAMESPACE   NAME                                     SYNCED   READY   EXTERNAL-NAME              AGE
team-a      subnet.ec2.aws.m.upbound.io/web-subnet   True     True    subnet-0c4dc650c19946a60   2m33s
team-b      subnet.ec2.aws.m.upbound.io/web-subnet   True     True    subnet-0e67bb036fee2685a   3m32s
team-c      subnet.ec2.aws.m.upbound.io/web-subnet   True     True    subnet-03f657c3e525e6195   2m46s

NAMESPACE   NAME                                       SYNCED   READY   EXTERNAL-NAME           AGE
platform    vpc.ec2.aws.m.upbound.io/shared-services   True     True    vpc-087df62393492c793   10m
team-a      vpc.ec2.aws.m.upbound.io/web-vpc           True     True    vpc-01654e1576586fbe9   3m36s
team-b      vpc.ec2.aws.m.upbound.io/web-vpc           True     True    vpc-04831c22c3141d2b5   3m36s
team-c      vpc.ec2.aws.m.upbound.io/web-vpc           True     True    vpc-0e6366f66c03695e0   2m50s
```

This is defined by the composition:

```shell
cat apis/networks/composition.yaml
```

Which calls a function defined in our project:

```shell
cat functions/compose/function/fn.py
```

## Let's simulate!

The idea of simulations is that we can see what will happen before we apply a
change. Let's start with the simplest case.

### `crossplane resource simulate`

The platform team has a VPC of their own that they use for shared services and
apply directly (not with a composition):

```shell
cat extra-resources/standalone-vpc.yaml
```

The team wants to add a tag to their VPC and create a subnet in it. We can
simulate what will happen before actually making the change. Because these are
plain managed resources, not composites, we use the `resource simulate` command:

```shell
$ crossplane resource simulate -f ../changes/resource/1-tag.yaml
✓ Pulling provider package xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
✓ Starting diff server for xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
[~] VPC.ec2.aws.m.upbound.io platform/shared-services (update)
    spec:
      forProvider:
        ~ enableDnsHostnames: "false" -> "true"
        tags:
          + cost-center: "platform"
        tagsAll:
          + cost-center: "platform"

[+] Subnet.ec2.aws.m.upbound.io platform/shared-services-subnet (create)
    spec:
      forProvider:
        + assignIpv6AddressOnCreation: "false"
        + availabilityZone: "us-west-2a"
        + availabilityZoneId: (known after apply)
        + cidrBlock: "10.100.1.0/24"
        + enableDns64: "false"
        + enableResourceNameDnsARecordOnLaunch: "false"
        + enableResourceNameDnsAaaaRecordOnLaunch: "false"
        + ipv6Native: "false"
        + mapPublicIpOnLaunch: "false"
        + region: "us-west-2"

Plan: 1 to add, 1 to change, 0 to destroy.
```

This change looks like it will work as expected, so we're all good.

Now, let's say the team wants to make their VPC's CIDR block bigger. We can
simulate that change, too:

```shell
$ crossplane resource simulate -f ../changes/resource/2-cidr.yaml
✓ Pulling provider package xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
✓ Starting diff server for xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
[-/+] VPC.ec2.aws.m.upbound.io platform/shared-services (replace)
    spec:
      forProvider:
        ~ cidrBlock: "10.100.0.0/16" -> "10.100.0.0/15"  # forces replacement

Plan: 0 to add, 0 to change, 0 to destroy, 1 requires replacement.

Warning: 1 resource has fields that force replacement: cidrBlock.
Crossplane providers never destroy and recreate to apply a change.
Applying this leaves the resource unsynced until it is replaced manually.
```

This change won't work as expected; to change the CIDR block AWS requires that
we delete and re-create the VPC. Terraform would do this replacement, but
Crossplane won't; it will get stuck. We can only know this by asking the
provider - Crossplane doesn't know AWS details itself.

### `crossplane xr simulate`

Now let's move to the team point of view. A team wants to change a tag on their
`Network`; let's see what will happen:

```shell
$ crossplane xr simulate -f ../changes/xr/1-promote.yaml
✓ Pulling provider package xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
✓ Starting diff server for xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
XR: Network.kubecon.example.org team-b/web
  [~] Network.kubecon.example.org team-b/web (update)
      spec:
        ~ environment: "dev" -> "prod"

  [~] SecurityGroup.ec2.aws.m.upbound.io team-b/web-web (update)
      spec:
        forProvider:
          tags:
            ~ environment: "dev" -> "prod"
          tagsAll:
            ~ environment: "dev" -> "prod"

  [~] Subnet.ec2.aws.m.upbound.io team-b/web-subnet (update)
      spec:
        forProvider:
          tags:
            ~ environment: "dev" -> "prod"
          tagsAll:
            ~ environment: "dev" -> "prod"

  [~] VPC.ec2.aws.m.upbound.io team-b/web-vpc (update)
      spec:
        forProvider:
          tags:
            ~ environment: "dev" -> "prod"
          tagsAll:
            ~ environment: "dev" -> "prod"

Plan: 0 to add, 4 to change, 0 to destroy.
```

This did two things: first it rendered the XR, then it simulated each of the
composed resources that popped out.

Now the team wants to move their netowrk to a different AZ; let's simulate that
change:

```shell
$ crossplane xr simulate ../changes/xr/2-move-az.yaml
✓ Pulling provider package xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
✓ Starting diff server for xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
XR: Network.kubecon.example.org team-b/web
  [~] Network.kubecon.example.org team-b/web (update)
      spec:
        ~ availabilityZone: "us-west-2b" -> "us-west-2a"

  [-/+] Subnet.ec2.aws.m.upbound.io team-b/web-subnet (replace)
      spec:
        forProvider:
          ~ availabilityZone: "us-west-2b" -> "us-west-2a"  # forces replacement

Plan: 0 to add, 1 to change, 0 to destroy, 1 requires replacement.

Warning: 1 resource has fields that force replacement: availabilityZone.
Crossplane providers never destroy and recreate to apply a change.
Applying this leaves the resource unsynced until it is replaced manually.
```

Similar to the CIDR block change on the VPC, this change would require deleting
and re-creating the subnet. Becuase simulate both renders and asks the provider
what it would do, we can see the full chain of events that the second-order
change would get stuck.

### `crossplane project simulate`

Back to the platform team. We've decided all VPCs should have DNS hostnames
enabled, so we're going to make a change in the function that composes VPCs.

We're using Crossplane CLI projects here, so the function lives in the project
and gets built by our tooling. We can use `crossplane project simulate` to do a
new build of the project and simulate applying it to the existing resources in
the cluster.

```shell
$ crossplane project simulate
✓ Resolving function dependencies
✓ Collecting resources
✓ Updating dependency xpkg.crossplane.io/crossplane-contrib/function-auto-ready:v0.7.3
✓ Updating dependency xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
✓ Updating dependency xpkg.crossplane.io/crossplane-contrib/function-go-templating:v0.13.2
✓ Generating schemas
✓ Building function compose
✓ Building configuration package
✓ Pulling provider package xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
✓ Starting diff server for xpkg.crossplane.io/crossplane-contrib/provider-aws-ec2:v2.9.0
[=] Composition.apiextensions.crossplane.io networks-inline.kubecon.example.org (no-op)
    Applying this creates no new CompositionRevision. Impact analysis skipped.

[=] Composition.apiextensions.crossplane.io networks.kubecon.example.org (no-op)
    Applying this creates no new CompositionRevision.

XR: Network.kubecon.example.org team-a/web
  [~] VPC.ec2.aws.m.upbound.io team-a/web-vpc (update)
      spec:
        forProvider:
          ~ enableDnsHostnames: "false" -> "true"

XR: Network.kubecon.example.org team-c/web
    rendered against pinned revision networks.kubecon.example.org-d196666 with the changed functions
  [~] VPC.ec2.aws.m.upbound.io team-c/web-vpc (update)
      spec:
        forProvider:
          ~ enableDnsHostnames: "false" -> "true"

Plan: 0 to add, 2 to change, 0 to destroy.
```
