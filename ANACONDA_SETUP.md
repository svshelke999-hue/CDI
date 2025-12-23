# Anaconda Setup Guide for CDI FastAPI

## Step 1: Create a New Conda Environment

```bash
# Create a new environment with Python 3.10 or 3.11
conda create -n cdi_api python=3.10 -y

# Or if you prefer Python 3.11
conda create -n cdi_api python=3.11 -y
```

## Step 2: Activate the Environment

```bash
# Activate the environment
conda activate cdi_api
```

## Step 3: Install Dependencies

### Option A: Install from requirements.txt (Recommended)

```bash
# Make sure you're in the project directory
cd "C:\Users\svshelke\OneDrive\CDI\Final_refact_CDI_copy - Copy - Backup - 10_19_amrishdemo"

# Install all dependencies from requirements.txt
pip install -r requirements.txt
```

### Option B: Install packages individually with conda (if available)

```bash
# Install packages that are available in conda
conda install -c conda-forge boto3 botocore -y
conda install -c conda-forge opensearch-py -y
conda install -c conda-forge pypdf2 -y

# Install remaining packages with pip
pip install fastapi uvicorn[standard] python-multipart python-docx streamlit typing-extensions
```

## Step 4: Verify Installation

```bash
# Check Python version
python --version

# Check installed packages
pip list

# Or check specific packages
pip show fastapi
pip show uvicorn
pip show python-docx
```

## Step 5: Set Up Environment Variables (if needed)

```bash
# Set AWS credentials (if using AWS Bedrock)
conda env config vars set AWS_ACCESS_KEY_ID=your_key
conda env config vars set AWS_SECRET_ACCESS_KEY=your_secret
conda env config vars set AWS_REGION=us-east-1

# Set Claude model ID
conda env config vars set CLAUDE_MODEL_ID=your_model_id

# Reactivate environment to apply changes
conda deactivate
conda activate cdi_api
```

## Step 6: Run the FastAPI Server

```bash
# Make sure you're in the project directory
cd "C:\Users\svshelke\OneDrive\CDI\Final_refact_CDI_copy - Copy - Backup - 10_19_amrishdemo"

# Activate environment (if not already activated)
conda activate cdi_api

# Run the API server
python api.py
```

## Useful Conda Commands

### Environment Management

```bash
# List all environments
conda env list
# or
conda info --envs

# Activate environment
conda activate cdi_api

# Deactivate environment
conda deactivate

# Remove environment (if needed)
conda env remove -n cdi_api

# Export environment to YAML file
conda env export > environment.yml

# Create environment from YAML file
conda env create -f environment.yml

# Update conda
conda update conda
```

### Package Management

```bash
# List installed packages in current environment
conda list

# Search for a package
conda search package_name

# Install a package
conda install package_name

# Install from specific channel
conda install -c conda-forge package_name

# Update a package
conda update package_name

# Update all packages
conda update --all

# Remove a package
conda remove package_name

# Install pip packages in conda environment
pip install package_name
```

### Information Commands

```bash
# Show environment information
conda info

# Show environment variables
conda env config vars list

# Show package information
conda list package_name

# Check if package is installed
conda list | grep package_name
```

## Troubleshooting Commands

```bash
# Clear conda cache
conda clean --all

# Fix broken packages
conda update --all

# Reinstall a package
conda install --force-reinstall package_name

# Check for conflicts
conda install package_name --dry-run

# Update pip
python -m pip install --upgrade pip
```

## Running in Background (Windows)

```bash
# Create a batch file to run in background
# Save as start_api_background.bat:
@echo off
call conda activate cdi_api
start "CDI API Server" cmd /k "python api.py"
```

## Quick Start Script

Create a file `setup_and_run.bat`:

```batch
@echo off
echo Setting up CDI API Environment...
call conda create -n cdi_api python=3.10 -y
call conda activate cdi_api
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Setup complete! Starting API server...
echo.
python api.py
pause
```

## Daily Usage Commands

```bash
# 1. Activate environment
conda activate cdi_api

# 2. Navigate to project directory
cd "C:\Users\svshelke\OneDrive\CDI\Final_refact_CDI_copy - Copy - Backup - 10_19_amrishdemo"

# 3. Run the API
python api.py

# 4. When done, deactivate
conda deactivate
```

## Verify API is Running

After starting the server, test it:

```bash
# In a new terminal (while API is running)
curl http://localhost:8001/

# Or visit in browser:
# http://localhost:8001/docs
```

## Notes

- Always activate the conda environment before running the API
- The API runs on port 8001 by default
- Make sure all environment variables are set before running
- If you encounter import errors, verify all packages are installed in the active environment

