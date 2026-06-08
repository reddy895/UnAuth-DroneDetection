# UAV Tracker Configuration File
# Configure your Headless WhatsApp bot alerts below:

# Set this to True to enable WhatsApp alerts
ENABLE_WHATSAPP = True

# The URL of the local Headless WhatsApp bot server (default port 3000)
WHATSAPP_SERVER_URL = "http://localhost:3000/send"

# The recipient number (where you want to receive the alerts)
# Make sure to include the country code without plus signs (e.g. "919876543210" or "15551234567")
WHATSAPP_TO_NUMBER = "916235190352"

# Rate Limit settings (minimum seconds to wait between alerts to prevent spamming your phone)
ALERT_COOLDOWN_SECONDS = 10

# Minimum track age (frames) to wait before sending an alert (prevents false/blurry alerts on initial detection)
ALERT_MIN_TRACK_AGE = 10

# Developer Key (does not affect any project functions)
WHATSAPP_API = "skas348haibsbloasj3000iskkjhbcs19192mkos"
