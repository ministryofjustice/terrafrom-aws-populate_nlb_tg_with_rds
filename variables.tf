variable "rds_dns_name" {
  default     = ""
  description = "the DNS name of the RDS database."
}

variable "nlb_tg_arn" {
  type        = string
  default     = ""
  description = "Network Log Balancer Target Group arn."
}

variable "max_lookup_per_invocation" {
  type 		  = string
  default 	  = "10"
  description = "Maximum number of invocations of DNS lookup"
}

variable "schedule_expression" {
  default     = "cron(5 * * * ? *)"
  description = "the aws cloudwatch event rule scheule expression that specifies when the scheduler runs. Default is 5 minuts past the hour. for debugging use 'rate(5 minutes)'. See https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html"
}
