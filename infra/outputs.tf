output "table_name" {
  value = aws_dynamodb_table.teams.name
}

output "table_arn" {
  value = aws_dynamodb_table.teams.arn
}

output "read_policy_arn" {
  value = aws_iam_policy.read.arn
}

output "admin_policy_arn" {
  value = aws_iam_policy.admin.arn
}
