# FastAPI Server Access Guide

## Server Status
✅ Your server is running successfully!

## How to Access the API

### Important: `0.0.0.0` is NOT a valid browser address!

When you see `Uvicorn running on http://0.0.0.0:8001`, this means the server is listening on **all network interfaces**. However, you **cannot** use `0.0.0.0` in your browser.

### Use These URLs Instead:

#### For Local Access (Same Machine):
- **http://localhost:8001/**
- **http://127.0.0.1:8001/**

#### For Network Access (From Other Machines):
- **http://10.50.20.175:8001/** (Your machine's IP address)
- Or use your actual machine IP address

### Available Endpoints:

1. **Health Check**: 
   - http://localhost:8001/
   - http://localhost:8001/health

2. **API Documentation (Swagger UI)**:
   - http://localhost:8001/docs

3. **Alternative API Docs (ReDoc)**:
   - http://localhost:8001/redoc

4. **Process PDF/DOCX/TXT**:
   - POST http://localhost:8001/process-pdf
   - Or: POST http://10.50.20.175:8001/process-pdf (for React app)

5. **System Info**:
   - GET http://localhost:8001/system-info

## React Frontend Configuration

Your React app is configured to use:
```javascript
http://10.50.20.175:8001/process-pdf
```

Make sure:
1. ✅ The FastAPI server is running
2. ✅ The IP address `10.50.20.175` matches your machine's actual IP
3. ✅ Firewall allows connections on port 8001

## Testing the API

### Using Browser:
1. Open: http://localhost:8001/docs
2. You'll see the interactive API documentation
3. Click "Try it out" on the `/process-pdf` endpoint
4. Upload a file and test

### Using curl (Command Line):
```bash
# Health check
curl http://localhost:8001/

# Test with file upload
curl -X POST "http://localhost:8001/process-pdf" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@path/to/your/file.pdf"
```

### Using Python:
```python
import requests

# Health check
response = requests.get("http://localhost:8001/")
print(response.json())

# Upload file
with open("path/to/file.pdf", "rb") as f:
    files = {"file": f}
    response = requests.post("http://localhost:8001/process-pdf", files=files)
    print(response.json())
```

## Troubleshooting

### Issue: "Can't reach this page" with 0.0.0.0
**Solution**: Use `localhost` or `127.0.0.1` instead of `0.0.0.0`

### Issue: React app can't connect
**Check**:
1. Server is running (check terminal)
2. Correct IP address in React code
3. Firewall settings
4. Network connectivity

### Issue: Port already in use
**Solution**: 
```bash
# Find process using port 8001
netstat -ano | findstr :8001

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

## Server Configuration

The server is configured to:
- **Host**: `0.0.0.0` (allows access from any network interface)
- **Port**: `8001`
- **Reload**: Enabled (auto-reloads on code changes)
- **CORS**: Enabled for all origins (for React frontend)

## Next Steps

1. ✅ Server is running
2. ✅ Access API docs at: http://localhost:8001/docs
3. ✅ Test file upload
4. ✅ Connect your React app to: http://10.50.20.175:8001/process-pdf

