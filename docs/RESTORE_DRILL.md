# Restore drill (V3-4-4)

A backup nobody has ever restored from isn't a backup, it's a hope. Run
this drill after the first real backup exists in production, and again
whenever `deploy/backup.sh` or the schema changes meaningfully.

## Steps

1. Stop writes to the database you're testing against (for a drill, just
   use a copy — never rehearse against the live production DB):
   ```bash
   cp data/backups/soulmatch_<latest>.db.gz /tmp/restore_drill.db.gz
   gunzip /tmp/restore_drill.db.gz
   ```
2. Point a scratch environment at the restored file and boot the app
   against it:
   ```bash
   export DATABASE_URL="sqlite:////tmp/restore_drill.db"
   .venv/Scripts/python.exe -c "from soulmatch.db import init_db; init_db()"
   ```
   `init_db()` running without error confirms the schema is intact and any
   pending migrations apply cleanly to real backed-up data, not just a
   freshly created database.
3. Spot-check the data is actually there — not just that the file opens:
   ```bash
   .venv/Scripts/python.exe -c "
   from soulmatch.db import get_session
   from soulmatch.models import User, Profile
   with get_session() as s:
       print('users:', s.query(User).count())
       print('profiles:', s.query(Profile).count())
   "
   ```
   Compare the counts against what you expect from the live system at
   backup time (roughly — some drift since the backup is fine).
4. Delete the scratch file. Never leave a restored copy of customer data
   lying around on a laptop or a second server.

## Rehearsed on 2026-07-12 (this sprint, V3-4-4)

Ran against a real snapshot of the production database (via SQLite's
backup API, not a raw file copy — see the note below on why that
distinction matters): `init_db()` completed with no errors against the
restored copy, and the data was intact and readable — 2 users, 18
profiles, admin account (`username=admin, plan=free`) present and correct.
Confirms the whole migration chain replays correctly against real
backed-up data, not just a fresh empty database.

**Known gotcha, encountered live during this sprint's own verification
work:** a plain `cp` of a running SQLite database can silently produce an
empty-looking copy if SQLite is mid-write (WAL contents not yet
checkpointed into the main file). `sqlite3 .backup` (what `deploy/backup.sh`
actually uses) doesn't have this problem — it's SQLite's own
online-backup mechanism and is safe against a live database. This is
exactly why this drill exists instead of trusting the mechanism blindly.
