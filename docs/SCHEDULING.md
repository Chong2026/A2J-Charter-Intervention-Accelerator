# Running the Monitor weekly (Windows Task Scheduler)

## 1. One-time setup
1. Copy `secrets.example.ps1` to `secrets.ps1` in the same folder as `run_monitor.py`,
   and fill in your real contact email and (optionally) email-alert credentials.
   `secrets.ps1` is in `.gitignore` -- it will never be committed.
2. Test it manually once:
   ```powershell
   .\run_weekly.ps1
   ```
   Check `monitor.log` for the output. Fix anything that fails before scheduling it.

## 2. Create the scheduled task
1. Open **Task Scheduler** (search for it in the Start menu).
2. Click **Create Task...** (not "Create Basic Task", so we get more options).
3. **General** tab:
   - Name: `A2J Charter Monitor`
   - Check **Run whether user is logged on or not** if you want it to run even when
     you're not logged in (it will ask for your Windows password once, when you save).
     Otherwise leave the default ("Run only when user is logged on").
4. **Triggers** tab -> **New...**:
   - Begin the task: **On a schedule**
   - Weekly, pick a day and time (e.g. Monday 9:00 AM)
5. **Actions** tab -> **New...**:
   - Action: **Start a program**
   - Program/script: `powershell.exe`
   - Add arguments:
     `-NoProfile -ExecutionPolicy Bypass -File "run_weekly.ps1"`
   - Start in (very important, this is what makes relative paths work):
     the full path to this folder, e.g. `C:\Coding\Charter Accelerator`
6. **Conditions** tab: if this is a laptop, you may want to uncheck
   "Start the task only if the computer is on AC power".
7. Save. Enter your Windows password if it was requested in step 3.

## 3. Test it
Right-click the task in the list -> **Run**. Then check `monitor.log` in the project
folder to confirm it ran and see what it found.

## Notes
- The monitor keeps its own record of which cases it has already seen and already
  alerted on (in `data/monitor.sqlite`), so running it more often than weekly is
  harmless -- it just won't find anything new most of the time.
- If you ever move the project folder, update the task's "Start in" field to match.
- University (Office365/Outlook) mail accounts often block this kind of SMTP login
  for security reasons. If `secrets.ps1` uses your osgoode.yorku.ca address and
  sending fails with an authentication error, use a personal Gmail account with an
  App Password instead -- see the comments in `secrets.example.ps1`.
