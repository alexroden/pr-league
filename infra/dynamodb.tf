resource "aws_dynamodb_table" "teams" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "team"

  attribute {
    name = "team"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = true
}

data "aws_iam_policy_document" "read" {
  statement {
    actions   = ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:DescribeTable"]
    resources = [aws_dynamodb_table.teams.arn]
  }
}

data "aws_iam_policy_document" "admin" {
  source_policy_documents = [data.aws_iam_policy_document.read.json]

  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:ConditionCheckItem",
    ]
    resources = [aws_dynamodb_table.teams.arn]
  }
}

resource "aws_iam_policy" "read" {
  name        = "${var.table_name}-read"
  description = "Read the PR League teams table (the bot)"
  policy      = data.aws_iam_policy_document.read.json
}

resource "aws_iam_policy" "admin" {
  name        = "${var.table_name}-admin"
  description = "Read and edit the PR League teams table (pr-league-admin)"
  policy      = data.aws_iam_policy_document.admin.json
}
