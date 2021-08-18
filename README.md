# terrafrom-aws-populate_nlb_tg_with_rds

Populate network load balancer target group with RDS IP address. This can be in fact any DNS resolvable to an instance like redshift DNS.

# Overview

RDS database have a DNS such as my-db.ctjuxtulczykq.eu-west-1.rds.amazonaws.com that associates an IP Address so applications can connect to the database. However the IP Address is subject to change in case of failover or upgrade so putting a load balancer in front (i.e. to use privatelink ) is problematic as the IP address must be specified in the target group. This lambda runs regularly to check the IP Address of the DNS entry for the RDS database and will unregister the old IP address and register the new IP address in the target group if it is changed. 

Initially it doesn't have any code to re-attempt the registration is if the connection goes into an Unhealthy state.

## Requirements

This module requires Terraform version `0.14.x` or newer.

## Dependencies

This module depends on a correctly configured [AWS Provider](https://www.terraform.io/docs/providers/aws/index.html) in your Terraform codebase.

## Usage

```
module "populate_nlb_tg_with_rds" {
  source        = "github.com/ministryofjustice/terrafrom-aws-populate_nlb_tg_with_rds"
  rds_dns_name  = "my-db.ctjuxtulczykq.eu-west-1.rds.amazonaws.com"
  nlb_tg_arn    = "arn:aws:elasticloadbalancing:eu-west-1:01234567890:targetgroup/mytargetgroup/aabbccddee0044332211"
  max_lookup_per_invocation = "10" 
}
```
## variables

### rds_dns_name

the DNS name of the RDS database. This can be in fact any DNS resolvable to an instance like redshift DNS.

### nlb_tg_arn

Network Log Balancer Target Group arn.
 
### max_lookup_per_invocation

Maximum number of invocations of DNS lookup. 

**Note:** This is a string value even though it is a number as it sets an environment variable

### schedule_expression

The aws cloudwatch event rule schedule expression that specifies when the lambda runs.

Default = "rate(5 minutes)"  i.e. every "rate(5 minutes)" See [ScheduledEvents](https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html)

### resource_name_prefix

The prefix to apply to resource names. E.g. setting this to cluster1- will create the Lambda as cluster1-populate-nlb-tg-with-rds-lambda rather than populate-nlb-tg-with-rds-lambda. default = "".

## References 

[https://aws.amazon.com/blogs/networking-and-content-delivery/using-static-ip-addresses-for-application-load-balancers/](https://aws.amazon.com/blogs/networking-and-content-delivery/using-static-ip-addresses-for-application-load-balancers/)

[https://aws.amazon.com/blogs/networking-and-content-delivery/hostname-as-target-for-network-load-balancers/](https://aws.amazon.com/blogs/networking-and-content-delivery/hostname-as-target-for-network-load-balancers/)

[https://www.bluematador.com/blog/static-ips-for-aws-application-load-balancer](https://www.bluematador.com/blog/static-ips-for-aws-application-load-balancer)
