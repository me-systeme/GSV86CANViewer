"""
grid_cell.py

Grid cell widget used by the GSV Grid application.

Each GridCell represents one position in the diamond-shaped grid layout
(e.g., "4/7"). Cells can be either:

- inactive:
  - show only the position label (row/column key)
  - have no border and no measurement UI

- active:
  - show position key, serial number, CAN ID, and the current measurement value
  - support dynamic background color (device-based coloring)
  - support an error highlight state (e.g., device init failure)

This widget is purely responsible for rendering. It does not talk to the DLL
or handle acquisition logic.
"""

from PyQt5 import QtCore, QtWidgets  
from PyQt5.QtGui import QColor

from gsvgrid.utils import best_text_color

class GridCell(QtWidgets.QFrame):
    """
    One cell in the grid display.

    What happens in this class:
    - Creates a small UI with labels (key / serial / CAN / value).
    - If the cell is inactive, only the position key is visible.
    - Provides setter methods to update value, CAN ID, serial number, and
      appearance (color or error highlight).

    Parameters
    ----------
    key : str
        Grid key identifying the cell position, e.g. "4/7".
    active : bool
        If True, the cell displays measurement content (SN, CAN, value) and
        a border. If False, only the key label is shown.
    parent : QObject | None
        Optional Qt parent widget.

    Returns
    -------
    None
    """

    def __init__(self, key: str, active: bool, parent=None):
        super().__init__(parent)

        # ---------------------------------------------------------------------
        # Cell identity and mode
        # ---------------------------------------------------------------------
        self.key = key
        self.active = active

        # ---------------------------------------------------------------------
        # Layout setup
        # ---------------------------------------------------------------------
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(3, 3, 3, 3)
        v.setSpacing(2)

        # ---------------------------------------------------------------------
        # Small helper: thin horizontal separator line
        # ---------------------------------------------------------------------
        def hline():
            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.HLine)
            line.setFrameShadow(QtWidgets.QFrame.Sunken)
            line.setStyleSheet("color: #999;")
            line.setFixedHeight(1)
            return line

        # ---------------------------------------------------------------------
        # Labels (always create them; hide some for inactive cells)
        # ---------------------------------------------------------------------
        self.lbl_key = QtWidgets.QLabel(key)
        self.lbl_key.setAlignment(QtCore.Qt.AlignCenter)

        self.lbl_sn = QtWidgets.QLabel("")
        self.lbl_sn.setAlignment(QtCore.Qt.AlignCenter)

        self.lbl_can = QtWidgets.QLabel("")   
        self.lbl_can.setAlignment(QtCore.Qt.AlignCenter)
        
        self.lbl_val = QtWidgets.QLabel("-")
        self.lbl_val.setAlignment(QtCore.Qt.AlignCenter)

        # Make labels visually "flat" (no frames inside the cell)
        for lbl in (self.lbl_key, self.lbl_sn, self.lbl_can, self.lbl_val):
            lbl.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")

        # ---------------------------------------------------------------------
        # Compose the UI depending on active/inactive mode
        # ---------------------------------------------------------------------
        v.addWidget(self.lbl_key)

        if active:
            # Active cells show all information separated by thin lines
            v.addWidget(hline())
            v.addWidget(self.lbl_sn)

            v.addWidget(hline())
            v.addWidget(self.lbl_can)

            v.addWidget(hline())
            v.addWidget(self.lbl_val)

            # Default styling for active cells
            self.setMinimumSize(1, 1)
            self.setStyleSheet("""QFrame { border: 2px solid black; border-radius: 2px; }""")

            self.lbl_key.setStyleSheet("font-weight: 600; border: none; background: transparent;")
            self.lbl_sn.setStyleSheet("color: #333; border: none; background: transparent;")
            self.lbl_can.setStyleSheet("color: #333; border: none; background: transparent;")
            self.lbl_val.setStyleSheet("border: none; background: transparent;")
        else:
            # Inactive cells only show the key label
            self.lbl_sn.hide()
            self.lbl_can.hide()
            self.lbl_val.hide()

            self.setMinimumSize(1, 1)
            self.setStyleSheet("QFrame { border: none; }")
            self.lbl_key.setStyleSheet("color: #444; border: none; background: transparent;")

    # -------------------------------------------------------------------------
    # Data setters (called by MainWindow / controller code)
    # -------------------------------------------------------------------------
    def set_value(self, val: float):
        """
        Update the displayed measurement value.

        Parameters
        ----------
        value_kn : float
            Measurement value in kN.

        Returns
        -------
        None
        """
        if not self.active:
            return
        
        try:
            self.lbl_val.setText(f"{val:.2f} kN")
        except Exception:
            self.lbl_val.setText("NaN")

    def set_can(self, answer_id: int):
        """
        Update the displayed CAN answer ID label.

        Parameters
        ----------
        answer_id : int
            CAN answer ID (will be shown in hex format).

        Returns
        -------
        None
        """
        if not self.active:
            return
        
        self.lbl_can.setText(f"CAN 0x{answer_id:03X}")

    def set_sn(self, serial):
        """
        Update the displayed device serial number.

        Parameters
        ----------
        serial : int | None
            Serial number of the device. If None, "SN ?" is shown.

        Returns
        -------
        None
        """
        if not self.active:
            return
        
        if serial is None:
            self.lbl_sn.setText("SN ?")
        else:
            self.lbl_sn.setText(f"SN {serial}")
    
    # -------------------------------------------------------------------------
    # Appearance helpers
    # -------------------------------------------------------------------------
    def set_color(self, color: QColor | None):
        """
        Apply a background color and automatically choose a readable text color.

        What happens:
        - If color is None, the cell is reset to a neutral style.
        - If color is provided, the cell background becomes that color and the
          text color is chosen via best_text_color().

        Parameters
        ----------
        color : QColor | None
            Background color to apply, or None for the neutral style.

        Returns
        -------
        None
        """
        if not self.active:
            return

        if color is None:
            # Reset to neutral style
            self.setStyleSheet("QFrame { border: 2px solid black; border-radius: 2px; }")

            # Reset text to a dark default
            for lbl in (self.lbl_key, self.lbl_sn, self.lbl_can, self.lbl_val):
                lbl.setStyleSheet(lbl.styleSheet() + "color: #333;")
            return

        bg = color.name()
        fg = best_text_color(color)

        self.setStyleSheet(f"""
            QFrame {{
                border: 2px solid black;
                border-radius: 2px;
                background-color: {bg};
            }}
        """)
        
        for lbl in (self.lbl_key, self.lbl_sn, self.lbl_can, self.lbl_val):
            lbl.setStyleSheet(lbl.styleSheet() + f"color: {fg};")
    
    def set_error(self, is_error: bool):
        """
        Apply an error highlight style.

        Notes:
        - This method only sets the error style when is_error is True.
        - Resetting the style should be done via set_color(...) or set_color(None),
          because those represent the "normal" rendering states.

        Parameters
        ----------
        is_error : bool
            If True, apply the error highlight style.

        Returns
        -------
        None
        """
        if not self.active:
            return

        if not is_error:
            return  # Normal style is controlled by set_color(...)

        # Alarm red style that fits the application's overall palette
        self.setStyleSheet("""
            QFrame {
                border: 2px solid #D64545;
                border-radius: 2px;
                background-color: #FDECEC;
            }
        """)
        
        for lbl in (self.lbl_key, self.lbl_sn, self.lbl_can, self.lbl_val):
            lbl.setStyleSheet(lbl.styleSheet() + "color: #8A1F1F;")