@echo off
REM ---------------------------------------------------------------------------
REM One action: pull the branch, fetch the city records this project could not
REM reach from the sandboxed cloud session, commit the retrieved text, push.
REM
REM Run this from a machine with ordinary network access (home wifi). Double-click
REM it, or from a shell:  Scripts\qc\fetch_city_records.cmd
REM
REM It is safe to re-run. Sources already fetched successfully are skipped; only
REM failures and new entries are attempted. Nothing is deleted.
REM
REM If you would rather not have it push, delete the final git push line.
REM ---------------------------------------------------------------------------
setlocal
set BRANCH=claude/edmonds-lidar-records-hzb7fy
cd /d "%~dp0..\.."
echo.
echo === repo: %CD%
echo === branch: %BRANCH%
echo.

git fetch origin %BRANCH% || goto :fail
git checkout %BRANCH% || goto :fail
git pull --ff-only origin %BRANCH% || goto :fail

echo.
echo === fetching public records (serial, 2s apart - this is deliberate)
echo.
pushd Scripts
py -3.12 qc\fetch_city_records.py %*
if errorlevel 1 (popd & goto :fail)
py -3.12 qc\fetch_city_records.py --status
popd

echo.
echo === committing retrieved text
git add Reports/sources
git diff --cached --quiet && (echo nothing new to commit & goto :done)
git commit -m "Reports: retrieved city public records from unrestricted network" || goto :fail
git push origin %BRANCH% || goto :fail

:done
echo.
echo === DONE. Retrieved text is in Reports\sources\text\ ; provenance in MANIFEST.tsv
echo === Anything marked FAILED needs a browser or a manual save - see the manifest notes.
echo.
pause
exit /b 0

:fail
echo.
echo *** FAILED - see the error above. Nothing was pushed.
echo.
pause
exit /b 1
