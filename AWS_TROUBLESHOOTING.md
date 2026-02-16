# AWS Lambda Trading Algorithm - Troubleshooting Guide

**Last Updated:** February 16, 2026

This document contains all critical information needed to troubleshoot and maintain your AWS Lambda trading algorithm deployment.

---

## 📋 AWS Resources Overview

### Lambda Function
- **Function Name:** `trading-algorithm`
- **Runtime:** Python 3.10
- **Region:** `us-east-1`
- **Handler:** `lambda_function.lambda_handler`
- **Timeout:** 120 seconds (2 minutes)
- **Memory:** 512 MB
- **Architecture:** x86_64

### S3 Bucket
- **Bucket Name:** `trading-algorithm-state-jalal`
- **Region:** `us-east-1`
- **Purpose:** Stores `trading_state.json` for algorithm state persistence

### Lambda Layer
- **Layer Name:** `trading-dependencies`
- **Compatible Runtime:** Python 3.10
- **Contents:** yfinance, pandas, numpy, pytz, requests, beautifulsoup4, html5lib
- **S3 Location:** `s3://trading-algorithm-state-jalal/trading-dependencies-layer.zip`

### EventBridge Schedules
1. **Schedule Name:** `trading-algorithm-935am`
   - **Cron:** `35 9 ? * MON-FRI *`
   - **Description:** First trading check at 9:35 AM ET
   - **Timezone:** America/New_York

2. **Schedule Name:** `trading-algorithm-every30min`
   - **Cron:** `0,30 10-16 ? * MON-FRI *`
   - **Description:** Trading checks every 30 min from 10 AM to 4 PM ET
   - **Timezone:** America/New_York

### IAM Roles
- **Lambda Execution Role:** Created by Lambda (has CloudWatch Logs permissions)
- **S3 Policy Name:** `TradingAlgorithmS3Access`
- **EventBridge Scheduler Roles:** Auto-created (Amazon_EventBridge_Scheduler_LAMBDA_*)

---

## 🔐 Environment Variables

The Lambda function requires these environment variables:

```bash
TELEGRAM_BOT_TOKEN=8488869990:AAEAupBhbfP0QkBLY1NGLLdjn0zJ8q6rLQg
TELEGRAM_CHAT_ID=7956935476
STATE_BUCKET_NAME=trading-algorithm-state-jalal
```

**⚠️ Security Note:** These are sensitive credentials. Never commit to public repositories.

---

## 🔍 How to Check if Everything is Working

### 1. Manual Test Lambda Function
```bash
# Via AWS Console
1. Go to: https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions/trading-algorithm
2. Click "Test" tab
3. Click "Test" button
4. Check for "Execution result: succeeded"
5. Verify Telegram notification received

# Via AWS CLI
aws lambda invoke \
  --function-name trading-algorithm \
  --region us-east-1 \
  output.json

cat output.json
```

### 2. Check CloudWatch Logs
```bash
# Via AWS Console
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Flambda$252Ftrading-algorithm

# Via AWS CLI
aws logs tail /aws/lambda/trading-algorithm --follow --region us-east-1
```

### 3. Check S3 State File
```bash
# Via AWS Console
https://s3.console.aws.amazon.com/s3/buckets/trading-algorithm-state-jalal

# Via AWS CLI
aws s3 ls s3://trading-algorithm-state-jalal/
aws s3 cp s3://trading-algorithm-state-jalal/trading_state.json - | jq
```

### 4. Verify EventBridge Schedules
```bash
# Via AWS Console
https://console.aws.amazon.com/scheduler/home?region=us-east-1#schedules

# Via AWS CLI
aws scheduler list-schedules --region us-east-1

# Check specific schedule
aws scheduler get-schedule \
  --name trading-algorithm-935am \
  --region us-east-1
```

---

## 🐛 Common Issues and Solutions

### Issue 1: Lambda Test Fails with "No module named 'yfinance'"

**Symptoms:**
```
Runtime.ImportModuleError: Unable to import module 'lambda_function': No module named 'yfinance'
```

**Solution:**
The Lambda Layer is missing or not attached properly.

1. Check if layer is attached:
   - Go to Lambda function → Scroll to "Layers" section
   - Should see `trading-dependencies` listed

2. If missing, add the layer:
   - Click "Add a layer"
   - Choose "Custom layers"
   - Select `trading-dependencies`
   - Click "Add"

3. If layer doesn't exist, rebuild it:
   ```bash
   # In AWS CloudShell
   rm -rf python trading-dependencies-layer.zip
   mkdir python

   pip install \
     --platform manylinux2014_x86_64 \
     --target python \
     --implementation cp \
     --python-version 3.10 \
     --only-binary=:all: \
     --upgrade \
     yfinance pandas numpy pytz requests

   zip -r trading-dependencies-layer.zip python
   aws s3 cp trading-dependencies-layer.zip s3://trading-algorithm-state-jalal/
   ```

   Then create a new layer version in Lambda console.

---

### Issue 2: Lambda Timeout Error

**Symptoms:**
```
Task timed out after 120.00 seconds
```

**Solution:**
Increase the timeout:
1. Go to Lambda function → Configuration → General configuration
2. Click "Edit"
3. Increase Timeout to 180 seconds (3 minutes)
4. Click "Save"

---

### Issue 3: No Telegram Notification

**Symptoms:**
- Lambda executes successfully but no Telegram message received

**Solution:**
1. Check environment variables are set correctly:
   ```bash
   aws lambda get-function-configuration \
     --function-name trading-algorithm \
     --region us-east-1 \
     --query 'Environment.Variables'
   ```

2. Verify Telegram bot token and chat ID:
   - Test manually: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage?chat_id=<YOUR_CHAT_ID>&text=Test

3. Check CloudWatch Logs for errors related to Telegram API

---

### Issue 4: S3 Permission Denied

**Symptoms:**
```
botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation
```

**Solution:**
The Lambda execution role needs S3 permissions.

1. Go to Lambda function → Configuration → Permissions
2. Click on the role name (opens IAM console)
3. Check if `TradingAlgorithmS3Access` policy is attached
4. If not, create inline policy:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:GetObject",
                   "s3:PutObject"
               ],
               "Resource": "arn:aws:s3:::trading-algorithm-state-jalal/*"
           }
       ]
   }
   ```

---

### Issue 5: EventBridge Schedule Not Triggering

**Symptoms:**
- Schedule shows as "Enabled" but Lambda doesn't run at scheduled time

**Solution:**
1. Verify schedule is enabled:
   ```bash
   aws scheduler get-schedule \
     --name trading-algorithm-935am \
     --region us-east-1 \
     --query 'State'
   ```

2. Check CloudWatch Logs around the scheduled time for any invocations

3. Verify the schedule's IAM role has permission to invoke Lambda:
   - Go to EventBridge Scheduler console
   - Click on the schedule
   - Check "Execution role" has `lambda:InvokeFunction` permission

4. Test by manually invoking:
   ```bash
   aws lambda invoke \
     --function-name trading-algorithm \
     --region us-east-1 \
     test-output.json
   ```

---

### Issue 6: Python Version Mismatch

**Symptoms:**
```
Runtime.ImportModuleError: Unable to import module 'lambda_function'
```

**Solution:**
Ensure Lambda runtime and Layer Python versions match.

1. Check Lambda runtime:
   ```bash
   aws lambda get-function-configuration \
     --function-name trading-algorithm \
     --region us-east-1 \
     --query 'Runtime'
   ```

2. If it's Python 3.11 but layer is Python 3.10, either:
   - Update Lambda to Python 3.10, OR
   - Rebuild layer for Python 3.11 (change `--python-version 3.11` in layer build command)

---

## 📊 Monitoring and Maintenance

### CloudWatch Logs Insights Queries

**Find errors in last 24 hours:**
```
fields @timestamp, @message
| filter @message like /ERROR/ or @message like /Exception/
| sort @timestamp desc
| limit 20
```

**Check execution times:**
```
fields @timestamp, @duration
| stats avg(@duration), max(@duration), min(@duration)
```

**Count invocations by day:**
```
fields @timestamp
| stats count() by bin(5m)
```

---

## 🔄 How to Update Lambda Code

### Method 1: Via Console
1. Go to Lambda function → Code tab
2. Click "Upload from" → ".zip file"
3. Upload new `lambda_deployment.zip`
4. Click "Save"

### Method 2: Via AWS CLI
```bash
# From your local project directory
cd lambda_package
zip -r ../lambda_deployment.zip *.py
cd ..

aws lambda update-function-code \
  --function-name trading-algorithm \
  --zip-file fileb://lambda_deployment.zip \
  --region us-east-1
```

---

## 🧹 How to Clean Up / Delete Everything

If you need to remove all AWS resources:

```bash
# 1. Delete EventBridge Schedules
aws scheduler delete-schedule --name trading-algorithm-935am --region us-east-1
aws scheduler delete-schedule --name trading-algorithm-every30min --region us-east-1

# 2. Delete Lambda Function
aws lambda delete-function --function-name trading-algorithm --region us-east-1

# 3. Delete Lambda Layer (all versions)
aws lambda list-layer-versions --layer-name trading-dependencies --region us-east-1
# Then delete each version:
aws lambda delete-layer-version --layer-name trading-dependencies --version-number 1 --region us-east-1

# 4. Empty and Delete S3 Bucket
aws s3 rm s3://trading-algorithm-state-jalal --recursive
aws s3 rb s3://trading-algorithm-state-jalal

# 5. Delete IAM Roles (via console)
# Go to IAM → Roles → Search for "trading-algorithm" and delete
```

---

## 💰 Cost Monitoring

### Expected Monthly Costs (Free Tier)
- Lambda: ~280 invocations/month = **$0.00** (within 1M free tier)
- S3: ~5KB storage = **$0.00** (within 5GB free tier)
- EventBridge: 2 schedules = **$0.00** (within 1M events free tier)

**Total: $0.00/month** (within free tier limits)

### After Free Tier Expires (12 months)
- Lambda: ~$0.15/month
- S3: ~$0.01/month
- EventBridge: ~$0.01/month

**Total: ~$0.17/month**

### Check Current Costs
```bash
# Via AWS Console
https://console.aws.amazon.com/billing/home

# Via AWS CLI (requires Cost Explorer enabled)
aws ce get-cost-and-usage \
  --time-period Start=2026-02-01,End=2026-02-28 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --region us-east-1
```

---

## 📞 Quick Reference Commands

### Test Lambda
```bash
aws lambda invoke --function-name trading-algorithm --region us-east-1 output.json && cat output.json
```

### View Latest Logs
```bash
aws logs tail /aws/lambda/trading-algorithm --follow --region us-east-1
```

### Check S3 State
```bash
aws s3 cp s3://trading-algorithm-state-jalal/trading_state.json - | python -m json.tool
```

### List All Schedules
```bash
aws scheduler list-schedules --region us-east-1 | grep trading
```

### Update Environment Variable
```bash
aws lambda update-function-configuration \
  --function-name trading-algorithm \
  --environment "Variables={TELEGRAM_BOT_TOKEN=NEW_TOKEN,TELEGRAM_CHAT_ID=7956935476,STATE_BUCKET_NAME=trading-algorithm-state-jalal}" \
  --region us-east-1
```

---

## 🔗 Important Links

- **Lambda Function:** https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions/trading-algorithm
- **S3 Bucket:** https://s3.console.aws.amazon.com/s3/buckets/trading-algorithm-state-jalal
- **CloudWatch Logs:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Flambda$252Ftrading-algorithm
- **EventBridge Schedules:** https://console.aws.amazon.com/scheduler/home?region=us-east-1#schedules
- **IAM Roles:** https://console.aws.amazon.com/iam/home?region=us-east-1#/roles

---

## 📝 Notes

- Timezone: America/New_York (automatically handles EST/EDT)
- Trading days: Monday-Friday only
- First run: 9:35 AM ET
- Subsequent runs: Every 30 minutes from 10:00 AM to 4:00 PM ET
- State persists in S3 between runs
- Notifications sent via Telegram for each execution

---

## 🆘 Emergency Contact

If nothing in this document helps, check:
1. AWS Service Health Dashboard: https://status.aws.amazon.com/
2. AWS Support Center: https://console.aws.amazon.com/support/
3. Local project files: `/Users/jalalchowdhury/PycharmProjects/trading_algorithm/`

---

**Document Version:** 1.0
**Created:** February 16, 2026
**Last Test Successful:** February 16, 2026
