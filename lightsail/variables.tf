variable "aws_region" {
  description = "The AWS Region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "instance_name" {
  description = "The name of the Lightsail instance"
  type        = string
  default     = "lightsail-vpn"
}
