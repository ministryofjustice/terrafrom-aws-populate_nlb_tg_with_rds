import boto3
from botocore.exceptions import ClientError

import sys, os, json, logging, time
import dns.resolver
from collections import defaultdict
from datetime    import datetime

# Timeout on one NS
DNS_RESOLVER_TIMEOUT = 1
# Timeout through out all of the NS
DNS_RESOLVER_LIFETIME = 10

logger = logging.getLogger()
logger.setLevel(logging.INFO)

aws_region = None

rds_dns_name = os.getenv('RDS_DNS_NAME', '')
logger.info("RDS_DNS_NAME is %s." % rds_dns_name)

nlb_tg_arn = os.getenv('NLB_TG_ARN', '')
logger.info("NLB_TG_ARN is %s." % nlb_tg_arn)

max_lookup_per_invocation = int(os.getenv('MAX_LOOKUP_PER_INVOCATION', '10'))
logger.info("MAX_LOOKUP_PER_INVOCATION is %s." % max_lookup_per_invocation)
debugmode = False

def init():
    # Setup AWS connection
    aws_region     = os.getenv('AWS_REGION', 'us-east-1')

    global elbv2
    logger.info("-----> Connecting to region \"%s\"", aws_region)
    elbv2 = boto3.client("elbv2", region_name=aws_region)
    logger.info("-----> Connected to region \"%s\"", aws_region)

def debugout(module, data):
    if debugmode:
        logger.info("DEBUG %s : %s" % (module, data))

def precondition(pre_condition, error_message):
    """
    Raise ValueError when pre-condition is False
    :param pre_condition: pre-condition statement
    :param error_message: error message passed to the exception
    """
    if not pre_condition:
        logger.error(f"Pre-condition: {pre_condition}. Error message: {error_message}")
        raise ValueError(error_message)


def dns_lookup(domain_name, record_type, dns_servers=[]):
    """
    Get dns lookup results
    :param dns_servers: list of DNS server IP addresses
    :param record_type: DNS record type
    :param domain_name: DNS name
    :return: list of dns lookup results
    """
    lookup_result_list = []
    my_resolver = dns.resolver.Resolver()
    my_resolver.rotate = True

    # When no specific DNS name server is given
    if not dns_servers:
        logger.info("No given DNS server")
        lookup_answers = my_resolver.query(domain_name, record_type)
        lookup_result_list = [str(answer) for answer in lookup_answers]
        return lookup_result_list

    # When a list of DNS name server (IP addresses) is given. Iterate over them until get the DNS lookup result
    for nameserver in dns_servers.copy():
        try:
            logger.info(f"Given DNS server: {dns_servers}")
            my_resolver.nameservers = [nameserver]
            lookup_answers = my_resolver.query(domain_name, record_type)
            lookup_result_list = [str(answer) for answer in lookup_answers]
            return lookup_result_list
        except Exception as e:
            dns_servers.remove(nameserver)
            logger.exception(
                f"Lookup error with name server - {nameserver}. "
                f"Remaining name server for retry - {dns_servers}. Error: {e}"
            )
            continue


def dns_lookup_with_retry(domain_name, record_type, total_retry_count, dns_servers=[]):
    """
    Get dns lookup results with retry
    :param domain_name:
    :param record_type:
    :param total_retry_count:
    :param dns_servers:
    :return:
    """
    dns_lookup_result_set = set()
    attempt = 1
    while attempt <= total_retry_count:
        lookup_result_per_attempt = dns_lookup(domain_name, record_type, dns_servers)
        dns_lookup_result_set = set(lookup_result_per_attempt) | dns_lookup_result_set
        logger.info(
            f"Attempt-{attempt}: DNS lookup IP count: {len(dns_lookup_result_set)}. "
            f"DNS lookup result: {dns_lookup_result_set}"
        )
        if len(lookup_result_per_attempt) < 8:
            logger.info(
                "There are less than 8 IPs in the DNS response. Stop further DNS lookup..."
            )
            break
        attempt += 1
    return dns_lookup_result_set

def get_node_ip_from_dns(dns_name, record_type, total_retry_count):
    """
    Get node IP through DNS lookup
    :param dns_name: DNS name of RDS
    :param record_type: DNS record type. e.g. A or AAAA
    :param total_retry_count: Total DNS lookup count
    :return: a set of node IP addresses
    """

    # Get IP through DNS lookup
    node_ip_set = dns_lookup_with_retry(
        dns_name, record_type, total_retry_count
    )
    return node_ip_set

def get_ip_from_dns():
    """
    Get node IP address through DNS lookup. Exit if no IP found in the DNS
    :return: a set of node IP addresses
    """
    ip_from_dns_set = get_node_ip_from_dns(
        rds_dns_name, "A", max_lookup_per_invocation
    )
    logger.info(
        f"Node IPs from DNS lookup: {ip_from_dns_set}. Total IP count: {len(ip_from_dns_set)}"
    )

    # Check if there is no IP in the DNS. If so, exit from the current Lambda invocation
    try:
        error_message = (
            f"No IP found from DNS for - {rds_dns_name}. "
            f"The Lambda function will not proceed with making changes to the target group - {nlb_tg_arn}"
        )
        precondition(ip_from_dns_set, error_message)
        return ip_from_dns_set
    except ValueError:
        sys.exit(1)


def register_target(tg_arn, new_target_list):
    """
    Register given targets to the given target group
    :param tg_arn: ARN of target group
    :param new_target_list: list of targets
    """
    logger.info("Register new_target_list:{}".format(new_target_list))
    try:
        elbv2.register_targets(TargetGroupArn=tg_arn, Targets=new_target_list)
    except ClientError as e:
        logger.exception(
            f"Failed to register target to target group. "
            f"Targets: {new_target_list}. Target group: {tg_arn}"
        )

def deregister_target(tg_arn, new_target_list):
    """
    Deregister given targets to the given target group
    :param tg_arn: ARN of target group
    :param new_target_list: list of targets
    """
    logger.info("Deregistering targets: {}".format(new_target_list))
    try:
        elbv2.deregister_targets(
            TargetGroupArn=tg_arn, Targets=new_target_list
        )
    except ClientError as e:
        logger.exception(
            f"Failed to deregister target to target group. "
             f"Targets: {new_target_list}. Target group: {tg_arn}"
         )

def get_ip_target_list_by_target_group_arn(tg_arn):
    """
    Get a list of IP targets that are registered with the given target group
    :param tg_arn: ARN of target group
    :return: list of target IP
    """
    registered_ip_list = []
    try:
        response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        for target in response["TargetHealthDescriptions"]:
            registered_ip_list.append(target["Target"]["Id"])
    except ClientError:
        logger.exception(f"Failed to get target list from target group - {tg_arn}")

    logger.info(
        f"RDS IPs that are currently registered with the target group: {registered_ip_list}. "
        f"Total IP count: {len(registered_ip_list)}"
    )
    return registered_ip_list


# Main function. Entrypoint for Lambda
def handler(event, context):

    init()
    
    # ---- Step 1 -----
    # Get IP from DNS
    logger.info(">>>>Step-1: Get IPs from DNS<<<<")
    ip_from_dns_set = get_ip_from_dns()

    # ---- Step 2 -----
    # Get IP that are currently registered with the NLB target group and update CloudWatch metric
    logger.info(">>>>Step-2: Get IPs from target group<<<<")
    ip_from_target_group_set = set(
        get_ip_target_list_by_target_group_arn(nlb_tg_arn)
    )
    logger.info(
        f"RDS IPs from target group ({nlb_tg_arn}): {ip_from_target_group_set}. "
        f"Total IP count: {len(ip_from_target_group_set)}"
    )
    
    now = datetime.now()
    active_ip_from_dns_meta_data = {
        "RDSName": rds_dns_name,
        "TimeStamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "IPList": list(ip_from_dns_set),
        "IPCount": len(ip_from_dns_set),
    }
    logger.debug(
        f"Meta data of active IPs in DNS from the current invocation: {active_ip_from_dns_meta_data}"
    )

    logger.info(">>>>Step-3: compare DNS IP address with IP Address in target group<<<<")
    logger.info(f"ip_from_target_group_set : {ip_from_target_group_set}")
    logger.info( f"ip_from_dns_set : {ip_from_dns_set}")
    targetIds = list(ip_from_dns_set)
    if len(ip_from_dns_set) == 0:
        logger.info(f"No DNS Entry found for : {rds_dns_name}")
    elif targetIds[0] not in ip_from_target_group_set:
        targets_list = [dict(Id=target_id) for target_id in targetIds]
        register_target(nlb_tg_arn, targets_list)
        if len(ip_from_target_group_set) > 0:
            oldtargetIds = list(ip_from_target_group_set)
            old_targets_list = [dict(Id=target_id) for target_id in oldtargetIds]
            deregister_target(nlb_tg_arn, old_targets_list)
    else:
        logger.info(f"target group already has IP : {targetIds[0]}")

# Manual invocation of the script (only used for testing)
if __name__ == "__main__":
    # Test data
    test = {}
    handler(test, None)
