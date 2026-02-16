# AWS Lambda + EventBridge Setup Guide

Complete guide to deploy your trading algorithm to AWS Lambda for 100% reliable scheduling.

---

## 📋 Prerequisites

- AWS Account (free tier eligible)
- AWS CLI installed (optional but recommended)
- Your Telegram bot token and chat ID

---

## 🚀 Step-by-Step Setup

### Step 1: Create S3 Bucket for State Storage

1. **Go to S3 Console:** https://s3.console.aws.amazon.com/
2. **Click "Create bucket"**
3. **Bucket settings:**
   - **Bucket name:** `trading-algorithm-state-YOUR_NAME` (must be globally unique)
   - **Region:** `us-east-1` (or your preferred region)
   - **Block all public access:** ✅ CHECKED (keep it private)
   - Leave other settings as default
4. **Click "Create bucket"**
5. **Note down your bucket name** - you'll need it later

---

### Step 2: Package Your Code for Lambda

**Option A: Using Docker (Recommended for complex dependencies)**

```bash
cd /Users/jalalchowdhury/PycharmProjects/trading_algorithm

# Create deployment package
mkdir -p lambda_package
pip install -r requirements.txt -t lambda_package/
cp *.py lambda_package/
cd lambda_package
zip -r ../lambda_deployment.zip .
cd ..
```

**Option B: Using AWS SAM (if you have it installed)**

```bash
sam build
sam deploy --guided
```

**Option C: Manual (Simpler but larger)**

```bash
cd /Users/jalalchowdhury/PycharmProjects/trading_algorithm
zip -r lambda_deployment.zip *.py
```

*Note: Option C creates a smaller package but you'll need to add Lambda Layers for dependencies (see Step 3B).*

---

### Step 3A: Create Lambda Function (Console Method)

1. **Go to Lambda Console:** https://console.aws.amazon.com/lambda/
2. **Click "Create function"**
3. **Function settings:**
   - **Function name:** `trading-algorithm`
   - **Runtime:** Python 3.9 or 3.11
   - **Architecture:** x86_64
   - **Permissions:** Create a new role with basic Lambda permissions
4. **Click "Create function"**

---

### Step 3B: Upload Your Code

**If you used Option A or B (full package with dependencies):**

1. In the Lambda function page, go to "Code" tab
2. Click "Upload from" → ".zip file"
3. Upload `lambda_deployment.zip`
4. Click "Save"

**If you used Option C (code only, no dependencies):**

1. Upload the zip file as above
2. Then scroll down to "Layers" section
3. Click "Add a layer"
4. Choose "AWS Layers"
5. Add these layers (search for them):
   - `AWSSDKPandas-Python39` (includes pandas, numpy)
   - You may need to manually install yfinance, requests, pytz via a custom layer

*Note: For simplicity, I recommend Option A.*

---

### Step 4: Configure Lambda Function

1. **Set Handler:**
   - In "Runtime settings", click "Edit"
   - Set Handler to: `lambda_function.lambda_handler`
   - Click "Save"

2. **Set Timeout:**
   - Go to "Configuration" → "General configuration"
   - Click "Edit"
   - Set Timeout to: **2 minutes** (120 seconds)
   - Set Memory to: **512 MB** (more memory = faster execution)
   - Click "Save"

3. **Set Environment Variables:**
   - Go to "Configuration" → "Environment variables"
   - Click "Edit" → "Add environment variable"
   - Add these three variables:

   | Key | Value |
   |-----|-------|
   | `TELEGRAM_BOT_TOKEN` | `8488869990:AAEAupBhbfP0QkBLY1NGLLdjn0zJ8q6rLQg` |
   | `TELEGRAM_CHAT_ID` | `7956935476` |
   | `STATE_BUCKET_NAME` | `your-bucket-name-from-step-1` |

   - Click "Save"

---

### Step 5: Grant S3 Permissions

1. **Go to "Configuration" → "Permissions"**
2. **Click on the role name** (opens IAM console)
3. **Click "Add permissions" → "Attach policies"**
4. **Search for:** `AmazonS3FullAccess` (or create custom policy below)
5. **Select it and click "Add permissions"**

**Better: Custom Policy (More Secure):**
1. Instead of step 4-5 above, click "Add permissions" → "Create inline policy"
2. Switch to JSON tab and paste:

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
            "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
        }
    ]
}
```

3. Replace `YOUR-BUCKET-NAME` with your actual bucket name
4. Click "Review policy"
5. Name it: `TradingAlgorithmS3Access`
6. Click "Create policy"

---

### Step 6: Test Lambda Function

1. **In Lambda console, click "Test" tab**
2. **Create test event:**
   - **Event name:** `test-event`
   - **Event JSON:** (leave as default or use `{}`)
3. **Click "Test"**
4. **Check results:**
   - Should see "Execution result: succeeded"
   - Check CloudWatch Logs for output
   - **Check your Telegram** - you should get a notification!

---

### Step 7: Create EventBridge Schedules

Now we'll create two schedules: one for 9:35 AM and one for every 30 minutes.

#### Schedule 1: First Run at 9:35 AM ET

1. **Go to EventBridge Console:** https://console.aws.amazon.com/events/
2. **Click "Rules" (left sidebar)**
3. **Click "Create rule"**
4. **Rule settings:**
   - **Name:** `trading-algorithm-935am`
   - **Description:** `First trading check at 9:35 AM ET`
   - **Event bus:** default
   - **Rule type:** Schedule
5. **Click "Next"**
6. **Schedule pattern:**
   - **Cron expression:** `35 13,14 ? * MON-FRI *`
   - *(Covers both EST and EDT)*
7. **Click "Next"**
8. **Select target:**
   - **Target types:** AWS service
   - **Select a target:** Lambda function
   - **Function:** `trading-algorithm`
9. **Click "Next"** → **Next** → **Create rule**

#### Schedule 2: Every 30 Minutes (10:00 AM - 4:00 PM ET)

1. **Click "Create rule"** again
2. **Rule settings:**
   - **Name:** `trading-algorithm-every30min`
   - **Description:** `Trading checks every 30 min from 10 AM`
   - **Rule type:** Schedule
3. **Click "Next"**
4. **Schedule pattern:**
   - **Cron expression:** `0,30 14-21 ? * MON-FRI *`
5. **Click "Next"**
6. **Select target:**
   - **Target types:** AWS service
   - **Select a target:** Lambda function
   - **Function:** `trading-algorithm`
7. **Click "Next"** → **Next** → **Create rule**

---

## ✅ Verification

### Test It Works:

1. **Manual Test:**
   - Go to Lambda console
   - Click "Test"
   - Check Telegram for notification

2. **Check Logs:**
   - Go to CloudWatch Logs
   - Find log group: `/aws/lambda/trading-algorithm`
   - Check recent logs for execution details

3. **Verify Schedule:**
   - Wait for next scheduled time (e.g., 9:35 AM or 10:00 AM)
   - Check CloudWatch Logs
   - Check Telegram for notification

4. **Check State Storage:**
   - Go to S3 bucket
   - You should see `trading_state.json` file
   - Download it to verify contents

---

## 💰 Cost Estimate

**Free Tier (First 12 months):**
- Lambda: 1M requests/month FREE
- S3: 5GB storage FREE
- EventBridge: 1M events/month FREE

**Your Usage:**
- ~280 Lambda invocations/month
- ~5KB S3 storage
- 2 EventBridge rules

**Total Cost: $0.00** (well within free tier!)

**After Free Tier:**
- ~$0.20/month (essentially free)

---

## 🎯 Next Steps

1. ✅ Disable GitHub Actions workflow (to avoid duplicate runs)
2. ✅ Monitor for a few days to ensure reliability
3. ✅ Check CloudWatch Logs for any errors
4. ✅ Verify Telegram notifications

---

## 🐛 Troubleshooting

**Lambda times out:**
- Increase timeout in Configuration → General configuration

**No Telegram notification:**
- Check environment variables are set correctly
- Check CloudWatch Logs for errors

**S3 permission denied:**
- Verify IAM role has S3 permissions (Step 5)
- Check bucket name is correct in environment variable

**Function not triggering:**
- Check EventBridge rules are enabled
- Verify cron expressions are correct
- Check CloudWatch Logs for invocation attempts

---

## 📚 Useful Commands

**View CloudWatch Logs:**
```bash
aws logs tail /aws/lambda/trading-algorithm --follow
```

**Invoke Lambda manually:**
```bash
aws lambda invoke --function-name trading-algorithm output.json
```

**Check S3 state file:**
```bash
aws s3 cp s3://YOUR-BUCKET-NAME/trading_state.json -
```

---

**Questions? Check CloudWatch Logs first!** They'll show you exactly what's happening.
