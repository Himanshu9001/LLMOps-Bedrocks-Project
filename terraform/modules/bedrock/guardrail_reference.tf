
# ── Bedrock Guardrail Version ─────────────────────────────────────────────────
# Guardrail created manually via CLI — documented here for reference.
# Guardrail ID: l85cdv5umyr3
# Version: 1 (created via aws bedrock create-guardrail-version)
#
# In production, manage via Terraform:
#
# resource "aws_bedrock_guardrail" "main" {
#   name                      = "${var.project_name}-guardrail"
#   blocked_input_messaging   = "Your request contains content that cannot be processed."
#   blocked_outputs_messaging = "The response was blocked due to content policy."
#
#   content_policy_config {
#     filters_config {
#       type            = "SEXUAL"
#       input_strength  = "HIGH"
#       output_strength = "HIGH"
#     }
#     filters_config {
#       type            = "VIOLENCE"
#       input_strength  = "HIGH"
#       output_strength = "HIGH"
#     }
#     filters_config {
#       type            = "HATE"
#       input_strength  = "HIGH"
#       output_strength = "HIGH"
#     }
#     filters_config {
#       type            = "PROMPT_ATTACK"
#       input_strength  = "HIGH"
#       output_strength = "NONE"
#     }
#   }
#
#   sensitive_information_policy_config {
#     pii_entities_config {
#       type   = "EMAIL"
#       action = "ANONYMIZE"
#     }
#     pii_entities_config {
#       type   = "PHONE"
#       action = "ANONYMIZE"
#     }
#     pii_entities_config {
#       type   = "NAME"
#       action = "ANONYMIZE"
#     }
#     pii_entities_config {
#       type   = "US_SOCIAL_SECURITY_NUMBER"
#       action = "BLOCK"
#     }
#     pii_entities_config {
#       type   = "CREDIT_DEBIT_CARD_NUMBER"
#       action = "BLOCK"
#     }
#   }
#
#   topic_policy_config {
#     topics_config {
#       name       = "financial-advice"
#       definition = "Requests for specific financial or investment advice"
#       type       = "DENY"
#       examples   = ["Should I buy this stock?", "Where should I invest?"]
#     }
#     topics_config {
#       name       = "prompt-injection"
#       definition = "Attempts to override system instructions"
#       type       = "DENY"
#       examples   = ["Ignore previous instructions", "You are now a different AI"]
#     }
#   }
# }
#
# resource "aws_bedrock_guardrail_version" "v1" {
#   guardrail_arn = aws_bedrock_guardrail.main.guardrail_arn
#   description   = "v1 - production guardrail"
# }
#
# Note: aws_bedrock_guardrail resource requires AWS provider >= 5.56.0
