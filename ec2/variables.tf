variable "aws_region" {
  description = "The AWS Region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the new VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet (where NAT Gateway/Instance resides)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet (associated with Client VPN)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "client_cidr_block" {
  description = "IP range block for VPN clients. Must be at least a /22 and not overlap with the VPC CIDR."
  type        = string
  default     = "172.16.0.0/22"
}

variable "use_nat_gateway" {
  description = "If true, deploy a Managed NAT Gateway. If false, deploy a cost-effective EC2 NAT Instance."
  type        = bool
  default     = false
}

variable "nat_instance_type" {
  description = "EC2 Instance type for the NAT Instance (if use_nat_gateway is false)"
  type        = string
  default     = "t3.nano"
}
