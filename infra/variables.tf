variable "table_name" {
  description = "DynamoDB table holding the league's teams; the bot reads it from PR_LEAGUE_TABLE"
  type        = string
  default     = "pr-league-teams"
}
