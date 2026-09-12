@echo off
REM ===========================================================================
REM Retrieve the Edmonds/Snohomish public records the sandboxed cloud session
REM could not reach — IN AN ISOLATED CLONE, never in your working tree.
REM
REM Run:   Scripts\qc\fetch_city_records.cmd
REM        Scripts\qc\fetch_city_records.cmd D:\some\other\path     (custom location)
REM
REM ISOLATION IS THE POINT. Your working tree at D:\edmonds-pipeline\treedata may
REM have a Claude session or a pipeline run active on it; README and
REM Scripts/CLAUDE.md rule 1b warn that parallel sessions share that tree. So this
REM script does ALL of its git work in a throwaway clone under
REM %LOCALAPPDATA%\edmonds-records-fetch. It never checks out, pulls, stages,
REM commits, resets or pushes in your working tree. The only thing it reads from
REM your tree is the origin URL, and only if it needs one.
REM
REM When it finishes, your own session picks the results up whenever IT chooses:
REM     git fetch origin claude/edmonds-lidar-records-hzb7fy
REM
REM Safe to re-run. The clone is reset to origin each time; the fetched records
REM live on the branch, not in the clone, so nothing is lost by discarding it.
REM ===========================================================================
setlocal enabledelayedexpansion
set BRANCH=claude/edmonds-lidar-records-hzb7fy
set FALLBACK_URL=https://github.com/Kameron-Eck/edmonds-treedata.git

set WORK=%~1
if "%WORK%"=="" set WORK=%LOCALAPPDATA%\edmonds-records-fetch

echo.
echo === ISOLATED RECORDS FETCH
echo === working clone : %WORK%
echo === branch        : %BRANCH%
echo === your tree     : NOT TOUCHED
echo.

REM ---- locate a Python ------------------------------------------------------
set PY=
py -3.12 -c "import sys" >nul 2>&1 && set PY=py -3.12
if not defined PY (py -3 -c "import sys" >nul 2>&1 && set PY=py -3)
if not defined PY (python -c "import sys" >nul 2>&1 && set PY=python)
if not defined PY (
  echo *** No Python found. Install 3.12 and re-run.
  goto :fail
)
echo === python: %PY%

REM ---- remote URL: hardcoded on purpose -------------------------------------
REM Deliberately does NOT read it from your working tree. Even `git remote get-url`
REM would mean running a git command with your tree as cwd, and the requirement here
REM is zero contact. Override with a second argument if the URL ever changes:
REM     fetch_city_records.cmd "" git@github.com:Kameron-Eck/edmonds-treedata.git
set ORIGIN=%~2
if "%ORIGIN%"=="" set ORIGIN=%FALLBACK_URL%
echo === origin: !ORIGIN!

REM ---- create or refresh the isolated clone ---------------------------------
echo.
echo === STEP 1/5  isolated clone
if exist "%WORK%\.git" (
  echo     refreshing existing clone
  git -C "%WORK%" fetch origin %BRANCH% || goto :fail
  git -C "%WORK%" checkout -B %BRANCH% origin/%BRANCH% || goto :fail
  git -C "%WORK%" reset --hard origin/%BRANCH% || goto :fail
) else (
  echo     cloning ^(single branch, shallow^)
  git clone --branch %BRANCH% --single-branch --depth 50 "!ORIGIN!" "%WORK%" || goto :fail
)

REM ---- prove the tool works before contacting city servers ------------------
echo.
echo === STEP 2/5  self-test ^(public AWS S3, unrelated to the city servers^)
echo.
pushd "%WORK%\Scripts"
%PY% qc\fetch_city_records.py --selftest
if errorlevel 1 (
  echo.
  echo *** Self-test failed. If it said text was MISSING, install the PDF reader:
  echo ***     %PY% -m pip install pypdf
  echo *** Not contacting city servers until this passes.
  popd
  goto :fail
)

REM ---- fetch ----------------------------------------------------------------
echo.
echo === STEP 3/5  fetching records ^(serial, 2s apart - deliberate, do not speed up^)
echo.
%PY% qc\fetch_city_records.py

REM ---- browser pass for the JS portals --------------------------------------
echo.
echo === STEP 4/5  browser pass for JavaScript portals ^(Laserfiche, PrimeGov^)
%PY% -c "import playwright" >nul 2>&1
if errorlevel 1 (
  echo     Playwright not installed - skipping. To enable the portal fallback:
  echo         %PY% -m pip install playwright
  echo         %PY% -m playwright install chromium
  echo     then re-run this script.
) else (
  %PY% qc\fetch_city_records.py --retry-failed --browser
)

echo.
echo === STEP 5/5  result
%PY% qc\fetch_city_records.py --status
popd

REM ---- commit and push, entirely inside the isolated clone ------------------
echo.
git -C "%WORK%" add Reports/sources
git -C "%WORK%" diff --cached --quiet && (echo nothing new to commit & goto :done)
git -C "%WORK%" -c user.name="records-fetch" -c user.email="noreply@localhost" commit -m "Reports: retrieved city public records from unrestricted network" || goto :fail
git -C "%WORK%" push origin %BRANCH% || goto :fail
echo === pushed to %BRANCH%

:done
echo.
echo === DONE. Nothing in your working tree was touched.
echo.
echo === Retrieved text : %WORK%\Reports\sources\text\
echo === Provenance     : %WORK%\Reports\sources\MANIFEST.tsv
echo.
echo === To analyse, open a SEPARATE Claude Code session in the isolated clone:
echo ===     cd /d %WORK%
echo ===     claude
echo === and paste the prompt from Reports\LIDAR_ACQUISITION_RECORDS_2026-09-09.md section 9.
echo.
echo === Anything still FAILED needs a manual save: open the URL in MANIFEST.tsv,
echo === save the PDF to %WORK%\Reports\sources\raw\^<id^>.pdf, then re-run this script.
echo.
pause
exit /b 0

:fail
echo.
echo *** STOPPED - see the error above. Nothing was pushed, and your working tree
echo *** was not modified.
echo.
pause
exit /b 1
