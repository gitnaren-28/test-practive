@echo off
REM Script to push MLR folder to a new repository

echo Initializing Git repository...
git init

echo Adding .gitignore...
git add .gitignore

echo Adding all files...
git add .

echo Creating initial commit...
git commit -m "Initial commit: MLR project with CloudFormation templates and Lambda functions"

echo.
echo ========================================
echo Next steps:
echo 1. Create a new repository on GitHub/GitLab/Bitbucket
echo 2. Copy the repository URL
echo 3. Run: git remote add origin YOUR_REPOSITORY_URL
echo 4. Run: git branch -M main
echo 5. Run: git push -u origin main
echo ========================================
echo.
echo Or run this command with your repository URL:
echo git remote add origin YOUR_REPOSITORY_URL ^&^& git branch -M main ^&^& git push -u origin main
