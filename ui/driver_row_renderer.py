"""Driver row rendering with pluggable style strategies."""

from typing import TYPE_CHECKING, Dict
from PySide6.QtWidgets import QWidget, QLabel, QGridLayout, QSizePolicy
from PySide6.QtCore import Qt

from config.constants import COLUMN_LAYOUT, COLUMN_MIN_WIDTHS
from core.driver_state import DriverState
from .styles import DefaultColorStyle, AlternateColorStyle, OutlineColorStyle, DarkColorStyle

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay


class DriverRowRenderer:
    """Handles driver row creation with pluggable color styles."""

    STYLES = {
        "Default": DefaultColorStyle(),
        "Dark": DarkColorStyle(),
        "Alternate": AlternateColorStyle(),
        "Outline": OutlineColorStyle()
    }

    def __init__(self, parent: 'LeagueOverlay'):
        """Initialize renderer with reference to parent overlay.

        Args:
            parent: LeagueOverlay instance
        """
        self.parent = parent

    def create_row(self, driver: DriverState) -> QWidget:
        """Create a driver row widget using the configured color style.

        Args:
            driver: DriverState object containing driver information

        Returns:
            QWidget representing the driver row
        """
        # Get color style
        style = self.STYLES.get(self.parent.settings.row_color_style, self.STYLES["Default"])
        styling = style.get_styling(driver, self.parent)

        # Extract styling components
        row_widget = styling['row_widget']
        container_widget = styling['container_widget']
        text_color = styling['text_color']
        gap_color = styling['gap_color']
        delta_faster_color = styling['delta_faster_color']
        delta_slower_color = styling['delta_slower_color']
        label_bg = styling['label_bg']
        label_border = styling['label_border']

        # Create layout
        layout = QGridLayout(row_widget)
        layout.setContentsMargins(*styling['layout_margins'])
        layout.setSpacing(styling['layout_spacing'])

        # Build column configuration based on settings
        # Column order: Pos | [+/-] | D-Pos | Driver | [Rating] | Car# | Gap | Int | [Best] | [Last] | [Delta] | [Pit]
        # Columns in brackets are optional

        # Start with base columns
        stretches = [COLUMN_LAYOUT.POS]
        current_col = 1

        # Track column indices for optional columns
        positions_gained_col = None
        div_pos_col = None
        name_col = None
        rating_col = None
        car_num_col = None
        gap_col = None
        interval_col = None
        best_lap_col = None
        last_lap_col = None
        delta_col = None
        pit_lap_col = None

        # Optional: Positions Gained
        if self.parent.settings.show_positions_gained:
            stretches.append(COLUMN_LAYOUT.POSITIONS_GAINED)
            positions_gained_col = current_col
            current_col += 1

        # D-Pos (always shown)
        stretches.append(COLUMN_LAYOUT.DIV_POS)
        div_pos_col = current_col
        current_col += 1

        # Driver (always shown)
        stretches.append(COLUMN_LAYOUT.DRIVER_NAME)
        name_col = current_col
        current_col += 1

        # Optional: Combined Rating (iRating + Safety Rating)
        if self.parent.settings.show_rating:
            stretches.append(COLUMN_LAYOUT.RATING)
            rating_col = current_col
            current_col += 1

        # Car# (moved to after Rating)
        stretches.append(COLUMN_LAYOUT.CAR_NUM)
        car_num_col = current_col
        current_col += 1

        # Optional: Gap to leader
        if self.parent.settings.show_gap:
            stretches.append(COLUMN_LAYOUT.GAP)
            gap_col = current_col
            current_col += 1

        # Optional: Interval to car ahead
        if self.parent.settings.show_interval:
            stretches.append(COLUMN_LAYOUT.INTERVAL)
            interval_col = current_col
            current_col += 1

        # Optional: Best Lap
        if self.parent.settings.show_best_lap:
            stretches.append(COLUMN_LAYOUT.BEST_LAP)
            best_lap_col = current_col
            current_col += 1

        # Optional: Last Lap
        if self.parent.settings.show_last_lap:
            stretches.append(COLUMN_LAYOUT.LAST_LAP)
            last_lap_col = current_col
            current_col += 1

        # Optional: Delta
        if self.parent.settings.show_delta:
            stretches.append(COLUMN_LAYOUT.DELTA)
            delta_col = current_col
            current_col += 1

        # Optional: Pit Lap (combined Last Pit + Out Lap)
        if self.parent.settings.show_pit_lap:
            stretches.append(COLUMN_LAYOUT.PIT_LAP)
            pit_lap_col = current_col
            current_col += 1

        # Apply column stretches
        for col_idx, stretch in enumerate(stretches):
            layout.setColumnStretch(col_idx, stretch)

        # Determine font weight
        font_weight = "bold" if driver.is_player or self.parent.settings.bold_drivers else "normal"

        # Create labels with dynamic column positions
        self._create_position_label(layout, driver, text_color, label_bg, label_border, font_weight, styling)

        # Optional: Positions Gained
        if positions_gained_col is not None:
            self._create_positions_gained_label(layout, driver, gap_color, label_bg, label_border, font_weight, positions_gained_col)

        # Always show: Division Position
        self._create_division_position_label(layout, driver, text_color, label_bg, label_border, font_weight, styling, div_pos_col)

        # Always show: Driver Name
        self._create_driver_name_label(layout, driver, text_color, label_bg, label_border, font_weight, name_col)

        # Optional: Combined Rating (iRating + Safety Rating with license color background)
        if rating_col is not None:
            self._create_combined_rating_label(layout, driver, text_color, label_bg, label_border, font_weight, rating_col)

        # Always show: Car Number (moved to after Rating)
        self._create_car_number_label(layout, driver, text_color, label_bg, label_border, font_weight, styling, car_num_col)

        # Gap to leader
        if gap_col is not None:
            self._create_gap_label(layout, driver, gap_color, label_bg, label_border, font_weight, gap_col)

        # Interval to car ahead
        if interval_col is not None:
            self._create_interval_label(layout, driver, gap_color, label_bg, label_border, font_weight, interval_col)

        # Optional: Best Lap
        if best_lap_col is not None:
            self._create_best_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight, best_lap_col)

        # Optional: Last Lap
        if last_lap_col is not None:
            self._create_last_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight, last_lap_col)

        # Optional: Delta
        if delta_col is not None:
            self._create_delta_label(layout, driver, delta_faster_color, delta_slower_color, gap_color, label_bg, label_border, font_weight, delta_col)

        # Optional: Pit Lap (combined Last Pit + Out Lap)
        if pit_lap_col is not None:
            self._create_pit_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight, pit_lap_col)

        # Set context menu for row widget
        row_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        row_widget.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )

        # Set context menu for container if it exists
        if container_widget:
            container_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            container_widget.customContextMenuRequested.connect(
                lambda pos, d=driver: self.parent.show_context_menu(d)
            )

        return container_widget if container_widget else row_widget

    def _create_position_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                               label_bg: str, label_border: str, font_weight: str, styling: Dict = None) -> None:
        """Create position label."""
        # Check for special position styling (for Default style)
        pos_color = styling.get('position_color', text_color) if styling else text_color
        pos_bg = styling.get('position_bg', label_bg) if styling else label_bg

        pos_label = QLabel(str(driver.position if driver.position else ''))
        pos_label.setStyleSheet(f"""
            QLabel {{
                color: {pos_color};
                background-color: {pos_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        pos_label.setAlignment(Qt.AlignCenter)
        pos_label.setMinimumWidth(COLUMN_MIN_WIDTHS.POS)
        pos_label.setContextMenuPolicy(Qt.CustomContextMenu)
        pos_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(pos_label, 0, 0)

    def _create_division_position_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                       label_bg: str, label_border: str, font_weight: str, styling: Dict = None, column: int = 1) -> None:
        """Create division position label."""
        # Check for special division position styling (same as car number for Default style)
        div_pos_color = styling.get('car_number_color', text_color) if styling else text_color
        div_pos_bg = styling.get('car_number_bg', label_bg) if styling else label_bg

        div_pos_label = QLabel(str(driver.division_position if driver.division_position else ''))
        div_pos_label.setStyleSheet(f"""
            QLabel {{
                color: {div_pos_color};
                background-color: {div_pos_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        div_pos_label.setAlignment(Qt.AlignCenter)
        div_pos_label.setMinimumWidth(COLUMN_MIN_WIDTHS.DIV_POS)
        div_pos_label.setContextMenuPolicy(Qt.CustomContextMenu)
        div_pos_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(div_pos_label, 0, column)

    def _create_car_number_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                 label_bg: str, label_border: str, font_weight: str, styling: Dict = None, column: int = 2) -> None:
        """Create car number label."""
        # Check for special car number styling (for Default style)
        car_color = styling.get('car_number_color', text_color) if styling else text_color
        car_bg = styling.get('car_number_bg', label_bg) if styling else label_bg

        car_label = QLabel(str(driver.car_number))
        car_label.setStyleSheet(f"""
            QLabel {{
                color: {car_color};
                background-color: {car_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        car_label.setAlignment(Qt.AlignCenter)
        car_label.setMinimumWidth(COLUMN_MIN_WIDTHS.CAR_NUM)
        car_label.setContextMenuPolicy(Qt.CustomContextMenu)
        car_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(car_label, 0, column)

    def _create_driver_name_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                  label_bg: str, label_border: str, font_weight: str, column: int = 3) -> None:
        """Create driver name label."""
        name_align = Qt.AlignCenter if self.parent.settings.center_drivers else Qt.AlignLeft
        name_label = QLabel(driver.team_name if driver.team_name > "" else driver.driver_name)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                padding-left: 0.5px;
                {label_border}
            }}
        """)
        name_label.setAlignment(name_align | Qt.AlignVCenter)
        name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name_label.setMinimumWidth(COLUMN_MIN_WIDTHS.DRIVER_NAME)
        name_label.setWordWrap(False)
        name_label.setContextMenuPolicy(Qt.CustomContextMenu)
        name_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(name_label, 0, column)

    def _create_gap_label(self, layout: QGridLayout, driver: DriverState, gap_color: str,
                         label_bg: str, label_border: str, font_weight: str, column: int = 4) -> None:
        """Create gap to leader label."""
        gap_label = QLabel(driver.gap_to_leader)
        gap_label.setStyleSheet(f"""
            QLabel {{
                color: {gap_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        gap_label.setAlignment(Qt.AlignCenter)
        gap_label.setMinimumWidth(COLUMN_MIN_WIDTHS.GAP)
        gap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        gap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(gap_label, 0, column)

    def _create_interval_label(self, layout: QGridLayout, driver: DriverState, gap_color: str,
                              label_bg: str, label_border: str, font_weight: str, column: int = 5) -> None:
        """Create interval to car ahead label."""
        interval_label = QLabel(driver.interval)
        interval_label.setStyleSheet(f"""
            QLabel {{
                color: {gap_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        interval_label.setAlignment(Qt.AlignCenter)
        interval_label.setMinimumWidth(COLUMN_MIN_WIDTHS.INTERVAL)
        interval_label.setContextMenuPolicy(Qt.CustomContextMenu)
        interval_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(interval_label, 0, column)

    def _create_delta_label(self, layout: QGridLayout, driver: DriverState, delta_faster_color: str,
                           delta_slower_color: str, default_color: str, label_bg: str,
                           label_border: str, font_weight: str, column: int = 6) -> None:
        """Create delta label with style-specific colors.

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing delta value
            delta_faster_color: Color for negative delta (you're faster)
            delta_slower_color: Color for positive delta (you're slower)
            default_color: Fallback color for no data ("--")
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
        """
        # Color code deltas: green for negative (you're faster), red for positive (you're slower)
        if driver.delta.startswith('-'):
            delta_display_color = delta_faster_color  # Green - you're faster than reference
        elif driver.delta.startswith('+'):
            delta_display_color = delta_slower_color  # Red - you're slower than reference
        else:
            delta_display_color = default_color  # Default color for "--"

        delta_label = QLabel(driver.delta)
        delta_label.setStyleSheet(f"""
            QLabel {{
                color: {delta_display_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        delta_label.setAlignment(Qt.AlignCenter)
        delta_label.setMinimumWidth(COLUMN_MIN_WIDTHS.DELTA)
        delta_label.setContextMenuPolicy(Qt.CustomContextMenu)
        delta_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(delta_label, 0, column)

    def _create_last_lap_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                               label_bg: str, label_border: str, font_weight: str, column: int = 5) -> None:
        """Create last lap time label.

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing last lap time
            text_color: Text color (gap_color - white)
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
        """
        last_lap_label = QLabel(driver.last_lap)
        last_lap_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        last_lap_label.setAlignment(Qt.AlignCenter)
        last_lap_label.setMinimumWidth(COLUMN_MIN_WIDTHS.LAST_LAP)
        last_lap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        last_lap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(last_lap_label, 0, column)

    def _create_best_lap_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                               label_bg: str, label_border: str, font_weight: str, column: int = 5) -> None:
        """Create best lap time label.

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing best lap time
            text_color: Text color (gap_color - white)
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
            column: Column index to place label
        """
        best_lap_label = QLabel(driver.best_lap)
        best_lap_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        best_lap_label.setAlignment(Qt.AlignCenter)
        best_lap_label.setMinimumWidth(COLUMN_MIN_WIDTHS.BEST_LAP)
        best_lap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        best_lap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(best_lap_label, 0, column)

    def _create_positions_gained_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                       label_bg: str, label_border: str, font_weight: str, column: int = 1) -> None:
        """Create positions gained label with color coding.

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing positions gained
            text_color: Text color (default - used for no change)
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
            column: Column index to place label
        """
        # Determine color based on positions gained/lost
        if driver.positions_gained.startswith("↑"):
            # Gained positions - use faster_color (green by default)
            positions_color = self.parent.settings.faster_color
        elif driver.positions_gained.startswith("↓"):
            # Lost positions - use slower_color (red by default)
            positions_color = self.parent.settings.slower_color
        else:
            # No change or invalid - use default color
            positions_color = text_color

        positions_gained_label = QLabel(driver.positions_gained)
        positions_gained_label.setStyleSheet(f"""
            QLabel {{
                color: {positions_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        positions_gained_label.setAlignment(Qt.AlignCenter)
        positions_gained_label.setMinimumWidth(COLUMN_MIN_WIDTHS.POSITIONS_GAINED)
        positions_gained_label.setContextMenuPolicy(Qt.CustomContextMenu)
        positions_gained_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(positions_gained_label, 0, column)

    def _create_combined_rating_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                       label_bg: str, label_border: str, font_weight: str, column: int) -> None:
        """Create combined rating label (iRating + Safety Rating) with license class background color.

        Format: "A 2.5  3.0k" (license + sublevel + space + iRating with k suffix)
        Background color matches license class (R=red, D=orange, C=gold, B=green, A=blue, P=indigo)

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing combined rating
            text_color: Text color
            label_bg: Background color (IGNORED - uses license class color instead)
            label_border: Border style
            font_weight: Font weight
            column: Column index to place label
        """
        from core.gap_calculator import GapCalculator

        # Get license class background color
        rating_bg = GapCalculator.get_license_background_color(driver.lic_level)

        rating_label = QLabel(driver.combined_rating)
        rating_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                background-color: {rating_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        rating_label.setAlignment(Qt.AlignCenter)
        rating_label.setMinimumWidth(COLUMN_MIN_WIDTHS.RATING)
        rating_label.setContextMenuPolicy(Qt.CustomContextMenu)
        rating_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(rating_label, 0, column)

    def _create_pit_lap_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                              label_bg: str, label_border: str, font_weight: str, column: int) -> None:
        """Create pit lap label (combined Last Pit + Out Lap).

        Shows "OUT" in orange during out lap, otherwise shows last pit lap number "L12".

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing pit lap display
            text_color: Default text color
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
            column: Column index to place label
        """
        # Use orange color (#FF8200) when showing "OUT", otherwise use default color
        pit_lap_color = "#FF8200" if driver.pit_lap == "OUT" else text_color

        pit_lap_label = QLabel(driver.pit_lap)
        pit_lap_label.setStyleSheet(f"""
            QLabel {{
                color: {pit_lap_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        pit_lap_label.setAlignment(Qt.AlignCenter)
        pit_lap_label.setMinimumWidth(COLUMN_MIN_WIDTHS.PIT_LAP)
        pit_lap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        pit_lap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(pit_lap_label, 0, column)
