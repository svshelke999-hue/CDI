# Streamlit Cloud Deployment Guide

This guide will help you deploy the Multi-Payer CDI Compliance Checker to Streamlit Cloud.

## Prerequisites

1. ✅ GitHub repository created: `svshelke999-hue/CDI`
2. ✅ Code pushed to GitHub
3. ✅ Streamlit Cloud account (free at https://share.streamlit.io/)

## Step 1: Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io/
2. Sign in with your GitHub account
3. Click **"New app"**
4. Fill in the deployment form:
   - **Repository**: `svshelke999-hue/CDI`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`
5. Click **"Deploy!"**

Wait 2-5 minutes for the initial deployment to complete.

## Step 2: Configure AWS Credentials (CRITICAL)

After deployment, you **MUST** add your AWS credentials in Streamlit Cloud Secrets:

1. In Streamlit Cloud, go to your deployed app
2. Click the **"⋮"** (three dots menu) → **"Settings"**
3. Click **"Secrets"** in the left sidebar
4. Paste the following configuration (replace with your actual credentials):

```toml
AWS_REGION = "us-east-1"
AWS_ACCESS_KEY_ID = "YOUR_AWS_ACCESS_KEY_ID_HERE"
AWS_SECRET_ACCESS_KEY = "YOUR_AWS_SECRET_ACCESS_KEY_HERE"
CLAUDE_MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
ENABLE_PROMPT_CACHING = "true"
DATA_SOURCE = "json"
ENABLE_CACHE = "true"
```

**Note:** Replace `YOUR_AWS_ACCESS_KEY_ID_HERE` and `YOUR_AWS_SECRET_ACCESS_KEY_HERE` with your actual AWS credentials. See `STREAMLIT_SECRETS_TEMPLATE.txt` for the actual values to use.

5. Click **"Save"**

**⚠️ IMPORTANT**: 
- These credentials are stored securely in Streamlit Cloud
- They are NOT committed to your GitHub repository
- Only you and authorized Streamlit Cloud users can see them

## Step 3: Verify Deployment

1. Go back to your app (click the app name)
2. Check the logs for any errors:
   - Click **"Manage app"** → **"Logs"**
   - Look for any error messages
3. Test the app:
   - Upload a sample chart file
   - Verify it processes correctly
   - Check that all payers (Cigna, UHC, Anthem) are working

## Step 4: Share Your App

Once deployed and working, you'll get a URL like:
```
https://cdi.streamlit.app
```

Share this URL with your team members - they can test the application without any setup!

## Troubleshooting

### App won't start / Shows errors

1. **Check Logs**: Go to "Manage app" → "Logs" to see error messages
2. **Verify Secrets**: Make sure all AWS credentials are correctly set in Secrets
3. **Check File Paths**: Ensure JSON data files are in the repository at:
   - `src/multi_payer_cdi/JSON_Data/extracted_procedures_single_call_Anthem_with_evidence_v2/`
   - `src/multi_payer_cdi/JSON_Data/extracted_procedures_single_call_UHC_with_evidence_v2/`
   - `src/multi_payer_cdi/JSON_Data/extracted_procedures_single_call_cigna_with_evidence_v2/`
   - `src/multi_payer_cdi/JSON_Data/CMS_General_guidelines/`

### "No module named..." errors

- Check that `requirements.txt` includes all dependencies
- Streamlit Cloud will automatically install packages from `requirements.txt`

### AWS Authentication errors

- Verify AWS credentials in Streamlit Secrets
- Check that AWS credentials have Bedrock access permissions
- Ensure `AWS_REGION` is set correctly

### File not found errors

- Verify JSON data files are committed to GitHub
- Check that file paths in `config.py` are relative (not Windows absolute paths)
- Ensure all data directories are in the repository

## Updating the App

To update your deployed app:

1. Make changes to your code locally
2. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Your update message"
   git push origin main
   ```
3. Streamlit Cloud will automatically detect the changes and redeploy (usually takes 1-2 minutes)

## Cost Monitoring

- Monitor AWS Bedrock usage in AWS Console
- Streamlit Cloud is free for public apps
- Consider setting up AWS billing alerts

## Security Notes

- ✅ AWS credentials are stored securely in Streamlit Cloud Secrets
- ✅ Credentials are never exposed in the code or GitHub
- ✅ App is publicly accessible (consider adding authentication if needed)
- ⚠️ Monitor usage to prevent unexpected costs

---

**Need Help?** Check the Streamlit Cloud documentation: https://docs.streamlit.io/streamlit-community-cloud

