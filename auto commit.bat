@echo off
git config user.name = april
git config user.email = aprilblog@163.com
git status
git add .
git status
set /p comment="Enter the comment: "
git commit -m %comment%
git push -u origin main
pause