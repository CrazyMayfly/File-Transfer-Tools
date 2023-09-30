# Icons From https://www.iconfinder.com/, lisence: Attribution 3.0 Unported (CC BY 3.0)
# Install the Pyinstaller
pip install -U pyinstaller

# Move to your project path or your venv path
# Make sure the paths below are correct

# If the packaged file is too large, you may consider placing
# UPX.exe (https://upx.github.io/) in the same path as pyinstaller.exe

# Package FTC.py as an executable program
pyinstaller.exe  --onefile --icon="./docs/build_guide/FTC.png" --console ./FTC.py

# Package FTS.py as an executable program
pyinstaller.exe  --onefile --icon="./docs/build_guide/FTS.png" --console ./FTS.py

