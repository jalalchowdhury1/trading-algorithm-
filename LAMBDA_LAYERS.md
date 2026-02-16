# Lambda Layers for Dependencies

Your `lambda_deployment.zip` (7.7KB) contains only your Python code. You'll add dependencies via Lambda Layers.

---

## 📦 Required Dependencies

Your algorithm needs:
- pandas, numpy (for data processing)
- yfinance (for stock data)
- requests, pytz (utilities)
- boto3 (already included in Lambda runtime)

---

## ✅ Easy Option: Use Public Lambda Layers

### Step 1: Add AWS Data Wrangler Layer (pandas + numpy)

1. In Lambda console, scroll to "Layers" section
2. Click "Add a layer"
3. Choose "Specify an ARN"
4. Use this ARN (for us-east-1, Python 3.11):
   ```
   arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python311:15
   ```

   **Other regions:**
   - `us-west-2`: `arn:aws:lambda:us-west-2:336392948345:layer:AWSSDKPandas-Python311:15`
   - `eu-west-1`: `arn:aws:lambda:eu-west-1:336392948345:layer:AWSSDKPandas-Python311:15`

5. Click "Add"

✅ This gives you: pandas, numpy, boto3, requests

---

### Step 2: Create Custom Layer for yfinance + pytz

You have two options:

#### Option A: Quick Fix (Use Lambda's /tmp directory)

Add this to the top of `lambda_function.py`:

```python
import subprocess
import sys

def install_packages():
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "yfinance", "pytz", "-t", "/tmp"
    ])
    sys.path.insert(0, '/tmp')

# Call once when Lambda starts
install_packages()
```

**Pros:** Simple, no additional setup
**Cons:** Adds ~2 seconds to cold start time

#### Option B: Create Custom Layer (Recommended)

On your local machine:

```bash
# Create layer directory
mkdir -p python_layer/python
cd python_layer

# Install packages
pip install yfinance pytz beautifulsoup4 lxml html5lib -t python/

# Create layer zip
zip -r yfinance_layer.zip python

# Upload to AWS (creates layer)
aws lambda publish-layer-version \
    --layer-name yfinance-layer \
    --zip-file fileb://yfinance_layer.zip \
    --compatible-runtimes python3.9 python3.11
```

Then add this layer ARN to your Lambda function.

---

## 🎯 Recommended Setup

1. **Upload your code:** `lambda_deployment.zip`
2. **Add Layer 1:** AWS Data Wrangler (pandas, numpy, requests, boto3)
3. **Add Layer 2:** Custom yfinance layer OR use Option A quick fix

---

## 🔍 Verify Dependencies

Test your Lambda function and check CloudWatch Logs. You should see:

```
Downloading data from 2025-10-15 to 2026-02-12
Fetching QQQ... ✓ Data Check: Successfully downloaded 83 rows
```

If you see import errors, check:
- Lambda Layers are added
- Layer ARN matches your region
- Python version matches (3.9 or 3.11)

---

## 💡 Alternative: Use Larger Package

If you want all dependencies in the zip:

```bash
# On a Linux machine or Docker
docker run -v "$PWD":/var/task public.ecr.aws/lambda/python:3.11 \
    pip install -r requirements.txt -t lambda_package/
```

This creates a ~50MB package with all dependencies.

---

**For simplicity, I recommend Option A (quick fix) or using the AWS Data Wrangler layer + custom yfinance layer.**
