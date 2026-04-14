# UptimeRobot Keep-Alive Setup Guide

**Purpose**: Keep Render Free tier service warm to avoid 50-second cold starts  
**Cost**: $0/month (Free tier: 50 monitors, 5-minute intervals)  
**Time**: 5 minutes

---

## Why Keep-Alive?

Render Free tier spins down after 15 minutes of inactivity. When a request comes in, it takes ~50 seconds to spin up (cold start). For active testing with Ronin, this is problematic.

**Solution**: UptimeRobot pings your `/health` endpoint every 5 minutes, keeping the service warm.

---

## Step 1: Sign Up for UptimeRobot

1. Go to https://uptimerobot.com
2. Click **"Sign Up Free"**
3. Enter email and password
4. Verify email address
5. Log in to dashboard

---

## Step 2: Create Monitor

### 2.1 Click "Add New Monitor"

In the UptimeRobot dashboard, click the **"+ Add New Monitor"** button.

### 2.2 Configure Monitor

Fill in the form:

**Monitor Type**: HTTP(s)

**Friendly Name**: Pharos Keep-Alive

**URL (or IP)**: 
```
https://pharos-cloud-api.onrender.com/health
```

**Monitoring Interval**: 5 minutes (free tier)

**Monitor Timeout**: 30 seconds

**Alert Contacts**: (Optional) Add your email to get notified if service goes down

**Advanced Settings** (Optional):
- **HTTP Method**: GET
- **Expected Status Code**: 200
- **Keyword Exists**: "healthy" (optional, checks response contains "healthy")

### 2.3 Create Monitor

Click **"Create Monitor"** button.

---

## Step 3: Verify Monitor

### 3.1 Check Monitor Status

After creating, you should see:
- **Status**: Up (green checkmark)
- **Uptime**: 100%
- **Response Time**: ~200-500ms (first request may be slower)

### 3.2 View Logs

Click on the monitor name to see:
- **Response Time Graph**: Shows response times over time
- **Uptime Logs**: Shows all pings and responses
- **Downtime Alerts**: Shows any downtime incidents

---

## Step 4: Test Keep-Alive

### 4.1 Wait 5 Minutes

UptimeRobot will ping your service every 5 minutes.

### 4.2 Check Render Logs

In Render dashboard:
1. Go to **pharos-cloud-api** service
2. Click **"Logs"** tab
3. You should see health check requests every 5 minutes:

```
[INFO] GET /health 200 OK (50ms)
[INFO] GET /health 200 OK (45ms)
[INFO] GET /health 200 OK (48ms)
```

### 4.3 Test Cold Start Prevention

1. Wait 10 minutes (service should stay warm)
2. Make a request to your API:
   ```bash
   curl https://pharos-cloud-api.onrender.com/health
   ```
3. Response should be fast (<1 second, not 50 seconds)

---

## Step 5: Configure Alerts (Optional)

### 5.1 Add Alert Contact

1. Go to **"My Settings"** → **"Alert Contacts"**
2. Click **"Add Alert Contact"**
3. Choose notification method:
   - **Email**: Your email address
   - **SMS**: Your phone number (paid feature)
   - **Slack**: Slack webhook URL
   - **Discord**: Discord webhook URL
   - **Telegram**: Telegram bot token

### 5.2 Assign to Monitor

1. Go back to your monitor
2. Click **"Edit"**
3. Under **"Alert Contacts"**, select your contact
4. Click **"Save Changes"**

### 5.3 Test Alert

1. Stop your Render service temporarily
2. Wait 5 minutes
3. You should receive a downtime alert
4. Restart service
5. You should receive an uptime alert

---

## Monitoring Dashboard

### Key Metrics

**Uptime Percentage**:
- **100%**: Perfect (no downtime)
- **99.9%**: Excellent (43 minutes downtime/month)
- **99%**: Good (7 hours downtime/month)
- **<99%**: Investigate issues

**Response Time**:
- **<500ms**: Excellent (warm service)
- **500ms-2s**: Good (warm service, some load)
- **2s-10s**: Slow (investigate)
- **>10s**: Very slow (cold start or issues)

**Downtime Incidents**:
- **0**: Perfect
- **1-2/month**: Acceptable (deployments, maintenance)
- **>5/month**: Investigate issues

---

## Troubleshooting

### Issue: Monitor Shows "Down"

**Possible Causes**:
1. Service is deploying (temporary)
2. Service crashed (check Render logs)
3. Database connection error (check NeonDB)
4. Redis connection error (check Upstash)

**Solution**:
1. Check Render dashboard for errors
2. Check Render logs for stack traces
3. Verify environment variables
4. Restart service if needed

### Issue: Response Time >10s

**Possible Causes**:
1. Cold start (service was idle)
2. High load (too many requests)
3. Database query slow (check NeonDB)
4. Out of memory (check RAM usage)

**Solution**:
1. Verify keep-alive is working (check logs)
2. Reduce concurrent requests
3. Optimize database queries
4. Upgrade to paid tier if needed

### Issue: Monitor Shows "Paused"

**Cause**: You manually paused the monitor

**Solution**: Click **"Resume Monitoring"** button

---

## Best Practices

### DO:
- ✅ Use 5-minute interval (free tier)
- ✅ Monitor `/health` endpoint (lightweight)
- ✅ Set up email alerts
- ✅ Check dashboard weekly
- ✅ Investigate downtime incidents

### DON'T:
- ❌ Use 1-minute interval (paid feature, unnecessary)
- ❌ Monitor heavy endpoints (e.g., `/api/ingest/github`)
- ❌ Ignore downtime alerts
- ❌ Rely on keep-alive for production (use paid tier)

---

## Cost Comparison

### Free Tier (Current)
- **Monitors**: 50
- **Interval**: 5 minutes
- **Alert Contacts**: Unlimited
- **SMS Alerts**: No
- **Cost**: $0/month

### Pro Tier (If Needed)
- **Monitors**: Unlimited
- **Interval**: 1 minute
- **Alert Contacts**: Unlimited
- **SMS Alerts**: Yes
- **Cost**: $7/month

**Recommendation**: Free tier is sufficient for testing. Upgrade to Pro only if you need 1-minute intervals or SMS alerts.

---

## Alternative Keep-Alive Methods

### 1. Cron Job (Self-Hosted)

```bash
# Add to crontab (runs every 5 minutes)
*/5 * * * * curl -s https://pharos-cloud-api.onrender.com/health > /dev/null
```

**Pros**: Free, no third-party service  
**Cons**: Requires server, no monitoring dashboard

### 2. GitHub Actions (Free)

```yaml
# .github/workflows/keep-alive.yml
name: Keep Alive
on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Ping Health Endpoint
        run: curl -s https://pharos-cloud-api.onrender.com/health
```

**Pros**: Free, integrated with GitHub  
**Cons**: No monitoring dashboard, limited to 5-minute intervals

### 3. Render Cron Job (Paid)

Render offers cron jobs on paid plans.

**Pros**: Native integration, reliable  
**Cons**: Requires paid plan ($7/month)

**Recommendation**: Use UptimeRobot for testing. It's free, reliable, and provides monitoring dashboard.

---

## Monitoring Multiple Services

If you deploy multiple services (e.g., edge worker, cloud API), create separate monitors:

**Monitor 1**: Pharos Cloud API
- URL: `https://pharos-cloud-api.onrender.com/health`
- Interval: 5 minutes

**Monitor 2**: Pharos Edge Worker (if deployed)
- URL: `https://pharos-edge-worker.onrender.com/health`
- Interval: 5 minutes

**Monitor 3**: Frontend (if deployed)
- URL: `https://pharos-frontend.onrender.com`
- Interval: 5 minutes

Free tier allows 50 monitors, so you have plenty of room.

---

## When to Disable Keep-Alive

Disable keep-alive when:
1. **Not actively testing**: Save UptimeRobot quota
2. **Deploying updates**: Avoid false downtime alerts
3. **Migrating to paid tier**: Render paid tier doesn't need keep-alive
4. **Service no longer needed**: Clean up unused monitors

To disable:
1. Go to monitor
2. Click **"Pause Monitoring"**
3. Or click **"Delete"** to remove permanently

---

## Summary

✅ **Setup Time**: 5 minutes  
✅ **Cost**: $0/month  
✅ **Benefit**: No cold starts during testing  
✅ **Monitoring**: Uptime dashboard and alerts  
✅ **Reliability**: 99.9% uptime for UptimeRobot itself

**Next Steps**:
1. Create UptimeRobot account
2. Add monitor for Pharos health endpoint
3. Verify pings in Render logs
4. Test fast response times
5. Configure Ronin integration

---

**Status**: Ready to set up  
**Estimated Time**: 5 minutes  
**Difficulty**: Easy

**Let's keep Pharos warm for Ronin testing!** 🔥
