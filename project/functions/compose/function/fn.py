"""Composes a team Network into a VPC, a subnet, and a security group."""

import grpc
from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1
from models.io.upbound.m.aws.ec2.securitygroup import v1beta1 as sgv1beta1
from models.io.upbound.m.aws.ec2.subnet import v1beta1 as subnetv1beta1
from models.io.upbound.m.aws.ec2.vpc import v1beta1 as vpcv1beta1
from models.org.example.kubecon.network import v1alpha1


class FunctionRunner(grpcv1.FunctionRunnerService):
    """A FunctionRunner handles gRPC RunFunctionRequests."""

    def __init__(self):
        """Create a new FunctionRunner."""
        self.log = logging.get_logger()

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Run the function."""
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running function")

        rsp = response.to(req)

        try:
            compose(req, rsp)
        except Exception as e:  # noqa: BLE001
            response.fatal(rsp, f"cannot compose network: {e}")

        return rsp


def compose(req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse) -> None:
    """Add the network's composed resources to the desired state."""
    xr = v1alpha1.Network.model_validate(
        resource.struct_to_dict(req.observed.composite.resource)
    )
    name = xr.metadata.name
    team = xr.metadata.namespace
    tags = {"environment": xr.spec.environment, "team": team}

    vpc_id = ""
    if "vpc" in req.observed.resources:
        observed_vpc = resource.struct_to_dict(req.observed.resources["vpc"].resource)
        vpc_id = observed_vpc.get("status", {}).get("atProvider", {}).get("id", "")

    resource.update(rsp.desired.resources["vpc"],
        vpcv1beta1.VPC(
            apiVersion="ec2.aws.m.upbound.io/v1beta1",
            kind="VPC",
            spec=vpcv1beta1.Spec(
                forProvider=vpcv1beta1.ForProvider(
                    region=xr.spec.region,
                    cidrBlock=xr.spec.vpcCidr,
                    tags=tags,
                ),
            ),
        ),
    )

    if not vpc_id:
        return

    resource.update(rsp.desired.resources["subnet"],
        subnetv1beta1.Subnet(
            apiVersion="ec2.aws.m.upbound.io/v1beta1",
            kind="Subnet",
            spec=subnetv1beta1.Spec(
                forProvider=subnetv1beta1.ForProvider(
                    region=xr.spec.region,
                    vpcId=vpc_id,
                    cidrBlock=xr.spec.subnetCidr,
                    availabilityZone=xr.spec.availabilityZone,
                    tags=tags,
                ),
            ),
        ),
    )

    resource.update(rsp.desired.resources["sg"],
        sgv1beta1.SecurityGroup(
            apiVersion="ec2.aws.m.upbound.io/v1beta1",
            kind="SecurityGroup",
            spec=sgv1beta1.Spec(
                forProvider=sgv1beta1.ForProvider(
                    region=xr.spec.region,
                    vpcId=vpc_id,
                    name=f"{team}-{name}",
                    description="Managed by Crossplane",
                    tags=tags,
                ),
            ),
        ),
    )
