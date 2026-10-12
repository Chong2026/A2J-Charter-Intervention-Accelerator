# Copy this file to secrets.ps1 and fill in your real values.
# secrets.ps1 is in .gitignore -- never commit real credentials.

# Contact email shown to the SCC servers in the User-Agent header (any address is fine).
$env:SCC_MONITOR_CONTACT = "you@example.com"

# --- Email alerts (leave these four blank to disable email; the monitor still runs) ---
#
# Gmail: create an "App Password" at https://myaccount.google.com/apppasswords
#   (requires 2-Step Verification to be turned on for your Google account first)
$env:ALERT_SMTP_HOST = "smtp.gmail.com"
$env:ALERT_SMTP_PORT = "465"
$env:ALERT_SMTP_USER = "you@gmail.com"
$env:ALERT_SMTP_PASS = "your-16-character-app-password"

# Who receives the alert. For now, send it to yourself.
$env:ALERT_FROM = $env:ALERT_SMTP_USER
$env:ALERT_TO   = "you@gmail.com"

# Optional: send health warnings somewhere other than ALERT_TO.
# $env:HEALTH_TO = "you@example.com"

# Optional: Charter sections or doctrines of special interest. Comma-separated.
# "s. 7" also matches s. 7 doctrines; "s. 2" matches s. 2(a)-(d).
# $env:ALERT_SECTIONS = "s. 7, s. 15"
# What to do with them: "extra" (default) = an extra priority email for those cases
# on top of the usual alert covering every Charter case; "only" = email only those cases.
# $env:ALERT_SECTIONS_MODE = "extra"
