#!/bin/bash

# Deploy trading algorithm to AWS Lambda
# This script packages your code and dependencies for Lambda

echo "🚀 Packaging trading algorithm for AWS Lambda..."

# Clean up old package
rm -rf lambda_package
rm -f lambda_deployment.zip

# Create package directory
mkdir lambda_package

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt -t lambda_package/ --platform manylinux2014_x86_64 --only-binary=:all:

# Copy Python files
echo "📄 Copying Python files..."
cp main.py lambda_package/
cp lambda_function.py lambda_package/
cp state_manager.py lambda_package/
cp market_hours.py lambda_package/

# Create ZIP file
echo "📦 Creating deployment package..."
cd lambda_package
zip -r ../lambda_deployment.zip . -q
cd ..

# Get file size
SIZE=$(du -h lambda_deployment.zip | cut -f1)
echo "✅ Done! Package size: $SIZE"
echo ""
echo "📦 Deployment package: lambda_deployment.zip"
echo ""
echo "Next steps:"
echo "1. Go to AWS Lambda console"
echo "2. Upload lambda_deployment.zip"
echo "3. Follow AWS_SETUP.md for complete instructions"
