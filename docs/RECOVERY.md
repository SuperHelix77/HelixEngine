# Recovery and rollback

Keep the application data directory separate from the installed package.
The default is ~/.helixengine on Linux and macOS, and the equivalent
user-home .helixengine directory on Windows. A custom --data-dir is the
authoritative location for that run.

## Preserve a failed run

Do not delete or edit a failed receipt. Save the receipt identifier and
retrieve stdout and stderr separately:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH retrieve RECEIPT --stream stdout
    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH retrieve RECEIPT --stream stderr

If a reducer fails, the command is not rerun automatically. A manually
requested rerun is a new command with a new receipt and must be reviewed as
such. A hash mismatch means the evidence object is not trusted; preserve it
for diagnosis and use another verified receipt.

## Back up and restore

Stop the local server and active routed commands before copying the data
directory. Copy the complete directory, including telemetry.sqlite3,
SQLite sidecar files, objects, runs, and any indexes. Use a new destination
for the backup so an existing backup is not overwritten.

To test a backup, pass its exact path with --data-dir and run:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir BACKUP_PATH doctor
    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir BACKUP_PATH status

Do not hand-edit SQLite rows or replace individual evidence objects. The
receipt hash binds an object to its bytes.

## Roll back a package update

Keep the prior wheel in a private release directory. Reinstall it with the
same interpreter:

    "$HOME/.helixengine-venv/bin/python" -m pip install --no-index --find-links PRIOR_WHEELHOUSE --force-reinstall PRIOR_WHEELHOUSE/helixengine-0.1.0-py3-none-any.whl

On Windows:

    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip install --no-index --find-links .\prior-wheelhouse --force-reinstall .\prior-wheelhouse\helixengine-0.1.0-py3-none-any.whl

Verify the installed version and run doctor before using the restored
package. Package rollback does not alter the data directory.

## Uninstall without data loss

Use the uninstall helper or pip uninstall. It removes package files only.
Back up and inspect the data directory before any manual removal. Do not
use a broad recursive deletion command or a wildcard path for recovery.
