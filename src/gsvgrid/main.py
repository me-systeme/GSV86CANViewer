"""
main.py

Application entry point for the GSV86CANViewer GUI.

This module is intentionally small and focused:
- It initializes the GSV86CAN DLL wrapper.
- It creates the Qt application and main window.
- It applies a reasonable default window size based on the screen.
- It starts the Qt event loop.

All UI logic, device handling, and acquisition are implemented
in the imported modules (MainWindow, ReaderThread, GSV86CAN, etc.).
"""

import sys
from PyQt5 import QtWidgets  

from gsvgrid.gsv86can import GSV86CAN
from gsvgrid.main_window import MainWindow


def main():
    """
    Application bootstrap function.

    What happens:
    - Instantiate the GSV86CAN wrapper (loads the DLL and prepares CAN access).
    - Create the Qt application object.
    - Create and show the main window.
    - Resize the window to a fraction of the available screen size.
    - Enter the Qt event loop.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The function only exits when the Qt event loop terminates.
    """
    # Initialize the GSV86CAN DLL wrapper (hardware / CAN interface)
    gsv = GSV86CAN()

    # Create the Qt application (required before any QWidget)
    app = QtWidgets.QApplication(sys.argv)

    # Create the main window and pass the GSV interface to it
    win = MainWindow(gsv)

    # Choose a reasonable initial window size relative to the screen
    screen = app.primaryScreen()
    geo = screen.availableGeometry()
    win.resize(int(geo.width() * 0.3), int(geo.height() * 0.42))

    # Show the main window
    win.show()

    # Start the Qt event loop and exit cleanly on close
    sys.exit(app.exec_())


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
