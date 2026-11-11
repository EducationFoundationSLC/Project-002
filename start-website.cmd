@echo off
rem Double-click this file to start the Project 002 website.
rem It runs start-website.ps1. Windows blocks PowerShell scripts by default, and
rem "-ExecutionPolicy Bypass" allows just this one script to run.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-website.ps1" %*
