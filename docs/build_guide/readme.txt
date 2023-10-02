#################################
#  Build Guide for FTC and FTS  #
#################################

# Icons From https://www.iconfinder.com/, lisence: Attribution 3.0 Unported (CC BY 3.0)
# Install the Pyinstaller
pip install -U pyinstaller

# Just run the "build.py" to build the program, the packaged file will be "FTT.zip"
#
# If the above process is executed successfully,
# there is no need for you to continue browsing the following content

-----------------------------------------------------------------

# Move to your project path or your venv path
# Make sure the paths below are correct

# If the packaged file is too large, you may consider placing
# UPX.exe (https://upx.github.io/) to the path './docs/build_guide/upx.exe'

# Package FTC.py as an executable program
pyinstaller.exe --onefile --icon="../docs/build_guide/FTC.png" --specpath "./build" --upx-dir "./docs/build_guide/upx.exe" --distpath "./FTT" --console ./FTC.py

# Package FTS.py as an executable program
pyinstaller.exe --onefile --icon="../docs/build_guide/FTS.png" --specpath "./build" --upx-dir "./docs/build_guide/upx.exe" --distpath "./FTT" --console ./FTS.py

