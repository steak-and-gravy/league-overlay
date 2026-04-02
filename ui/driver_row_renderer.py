"""Driver row rendering with pluggable style strategies."""

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QGridLayout, QSizePolicy
from PySide6.QtCore import Qt

from config.constants import COLUMN_MIN_WIDTHS, COLUMN_REGISTRY
from config.logging_config import get_logger
from core.driver_state import DriverState
from .styles import BandingColorStyle, DefaultColorStyle, AlternateColorStyle, OutlineColorStyle, DarkColorStyle

logger = get_logger(__name__)

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay


class DriverRowRenderer:
    """Handles driver row creation with pluggable color styles."""

    LOGO_DIRECTORY = Path(__file__).resolve().parent.parent / "assets" / "manufacturer_logos"
    MANUFACTURER_LOGO_FILES = {
        "ACU": "acura.png",
        "ALP": "alpine.png",
        "AMR": "aston.png",
        "AMV": "aston.png",
        "AUD": "audi.png",
        "BMW": "bmw.png",
        "CAD": "cadillac.png",
        "CHE": "chevrolet.png",
        "CHV": "chevrolet.png",
        "DAL": "dallara.png",
        "FER": "ferrari.png",
        "FOR": "ford.png",
        "FRD": "ford.png",
        "HND": "honda.png",
        "HON": "honda.png",
        "LAM": "lamborghini.png",
        "LIG": "ligier.png",
        "MAZ": "mazda.png",
        "MCL": "mclaren.png",
        "MER": "mercedes.png",
        "NIS": "nissan.png",
        "POR": "porsche.png",
        "RAD": "radical.png",
        "TOY": "toyota.png",
    }
    _logo_cache: Dict[str, Optional[QPixmap]] = {}

    STYLES = {
        "Default": DefaultColorStyle(),
        "Banding": BandingColorStyle(),
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

    @classmethod
    def _get_manufacturer_logo_path(cls, driver: DriverState) -> Optional[Path]:
        """Return the configured logo path for the driver's car manufacturer."""
        manufacturer_code = (driver.car_manufacturer or "").upper()
        logo_file = cls.MANUFACTURER_LOGO_FILES.get(manufacturer_code)
        if logo_file:
            logo_path = cls.LOGO_DIRECTORY / logo_file
            if logo_path.exists():
                return logo_path

        car_path = driver.driver_info.get("CarPath", "")
        manufacturer_key = car_path.split()[0].lower() if car_path.split() else ""
        if manufacturer_key:
            logo_path = cls.LOGO_DIRECTORY / f"{manufacturer_key}.png"
            if logo_path.exists():
                return logo_path

        return None

    @classmethod
    def _get_manufacturer_logo_pixmap(cls, driver: DriverState) -> Optional[QPixmap]:
        """Load and cache the manufacturer's logo pixmap."""
        logo_path = cls._get_manufacturer_logo_path(driver)
        if logo_path is None:
            return None

        cache_key = str(logo_path)
        if cache_key not in cls._logo_cache:
            pixmap = QPixmap(str(logo_path))
            cls._logo_cache[cache_key] = pixmap if not pixmap.isNull() else None

        return cls._logo_cache[cache_key]

    def create_row(self, driver: DriverState, row_index: int = 0) -> QWidget:
        """Create a driver row widget using the configured color style.

        Columns are rendered in the order specified by settings.column_order,
        with optional columns skipped if their visibility setting is off.

        Args:
            driver: DriverState object containing driver information
            row_index: Zero-based row index within the current rendered list

        Returns:
            QWidget representing the driver row
        """
        # Get color style
        style = self.STYLES.get(self.parent.settings.row_color_style, self.STYLES["Default"])
        styling = style.get_styling(driver, self.parent, row_index=row_index)

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

        # Determine font weight
        font_weight = "bold" if driver.is_player or driver.is_spectated or self.parent.settings.bold_drivers else "normal"

        # Build visible columns in user-configured order
        current_col = 0
        for col_id in self.parent.settings.column_order:
            col_def = COLUMN_REGISTRY.get(col_id)
            if col_def is None:
                continue

            # Skip optional columns that are toggled off
            if col_def.settings_key and not getattr(self.parent.settings, col_def.settings_key, False):
                continue

            layout.setColumnStretch(current_col, col_def.stretch)

            # Dispatch to the appropriate render method
            render_method = col_def.render_method
            if render_method == 'position':
                self._create_position_label(layout, driver, text_color, label_bg, label_border, font_weight, styling, current_col)
            elif render_method == 'positions_gained':
                self._create_positions_gained_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'manufacturer':
                self._create_manufacturer_label(layout, driver, label_bg, label_border, font_weight, current_col)
            elif render_method == 'division_position':
                self._create_division_position_label(layout, driver, text_color, label_bg, label_border, font_weight, styling, current_col)
            elif render_method == 'driver_name':
                self._create_driver_name_label(layout, driver, text_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'combined_rating':
                self._create_combined_rating_label(layout, driver, text_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'car_number':
                self._create_car_number_label(layout, driver, text_color, label_bg, label_border, font_weight, styling, current_col)
            elif render_method == 'gap':
                self._create_gap_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'division_gap':
                self._create_division_gap_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'interval':
                self._create_interval_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'division_interval':
                self._create_division_interval_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'best_lap':
                self._create_best_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'last_lap':
                self._create_last_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'delta':
                self._create_delta_label(layout, driver, delta_faster_color, delta_slower_color, gap_color, label_bg, label_border, font_weight, current_col)
            elif render_method == 'pit_lap':
                self._create_pit_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight, current_col)
            else:
                # Unknown render method — reset stretch and skip to avoid misalignment
                layout.setColumnStretch(current_col, 0)
                logger.warning(f"Unknown column render method '{render_method}' for column '{col_id}'")
                continue

            current_col += 1

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
                               label_bg: str, label_border: str, font_weight: str, styling: Dict = None, column: int = 0) -> None:
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
        layout.addWidget(pos_label, 0, column)

    def _create_division_position_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                       label_bg: str, label_border: str, font_weight: str, styling: Dict = None, column: int = 1) -> None:
        """Create division position label."""
        div_pos_color = styling.get('division_position_color', text_color) if styling else text_color
        div_pos_bg = styling.get('division_position_bg', label_bg) if styling else label_bg
        div_pos_border = styling.get('division_position_border', label_border) if styling else label_border

        div_pos_label = QLabel(str(driver.division_position if driver.division_position else ''))
        div_pos_label.setStyleSheet(f"""
            QLabel {{
                color: {div_pos_color};
                background-color: {div_pos_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {div_pos_border}
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
        car_border = styling.get('car_number_border', label_border) if styling else label_border

        car_label = QLabel(str(driver.car_number))
        car_label.setStyleSheet(f"""
            QLabel {{
                color: {car_color};
                background-color: {car_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {car_border}
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
        name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
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
        """Create gap to overall leader label."""
        gap_text, gap_display_color = self._get_gap_display(driver, driver.gap_to_leader, gap_color)
        gap_label = QLabel(gap_text)
        gap_label.setStyleSheet(f"""
            QLabel {{
                color: {gap_display_color};
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

    def _create_division_gap_label(self, layout: QGridLayout, driver: DriverState, gap_color: str,
                                   label_bg: str, label_border: str, font_weight: str, column: int = 5) -> None:
        """Create gap to division leader label (C-Gap)."""
        div_gap_text, div_gap_display_color = self._get_gap_display(
            driver,
            driver.division_gap_to_leader,
            gap_color
        )
        div_gap_label = QLabel(div_gap_text)
        div_gap_label.setStyleSheet(f"""
            QLabel {{
                color: {div_gap_display_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        div_gap_label.setAlignment(Qt.AlignCenter)
        div_gap_label.setMinimumWidth(COLUMN_MIN_WIDTHS.DIV_GAP)
        div_gap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        div_gap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(div_gap_label, 0, column)

    def _create_interval_label(self, layout: QGridLayout, driver: DriverState, gap_color: str,
                              label_bg: str, label_border: str, font_weight: str, column: int = 5) -> None:
        """Create interval to car ahead (overall) label."""
        interval_text, interval_display_color = self._get_gap_display(driver, driver.interval, gap_color)
        interval_label = QLabel(interval_text)
        interval_label.setStyleSheet(f"""
            QLabel {{
                color: {interval_display_color};
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

    def _create_division_interval_label(self, layout: QGridLayout, driver: DriverState, gap_color: str,
                                        label_bg: str, label_border: str, font_weight: str, column: int = 6) -> None:
        """Create interval to car ahead in division label (C-Int)."""
        div_interval_text, div_interval_display_color = self._get_gap_display(
            driver,
            driver.division_interval,
            gap_color
        )
        div_interval_label = QLabel(div_interval_text)
        div_interval_label.setStyleSheet(f"""
            QLabel {{
                color: {div_interval_display_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        div_interval_label.setAlignment(Qt.AlignCenter)
        div_interval_label.setMinimumWidth(COLUMN_MIN_WIDTHS.DIV_INTERVAL)
        div_interval_label.setContextMenuPolicy(Qt.CustomContextMenu)
        div_interval_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(div_interval_label, 0, column)

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

    @staticmethod
    def _get_gap_display(driver: DriverState, default_text: str, default_color: str) -> tuple[str, str]:
        """Return display text/color for gap-style columns, including pit/tow overrides."""
        if driver.pit_lap == "TOW":
            return "TOW", "#FF3B30"
        if driver.pit_lap == "PIT":
            return "PIT", default_color
        return default_text, default_color

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
        positions_text = driver.positions_gained

        # Determine color based on positions gained/lost
        if positions_text.startswith("↑"):
            # Gained positions - use faster_color (green by default)
            positions_color = self.parent.settings.faster_color
            positions_text = positions_text.replace("↑", "▲ ", 1)
        elif positions_text.startswith("↓"):
            # Lost positions - use slower_color (red by default)
            positions_color = self.parent.settings.slower_color
            positions_text = positions_text.replace("↓", "▼ ", 1)
        else:
            # No change or invalid - use default color
            positions_color = text_color

        positions_gained_label = QLabel(positions_text)
        positions_gained_label.setStyleSheet(f"""
            QLabel {{
                color: {positions_color};
                background-color: {label_bg};
                font-size: calc({self.parent.get_font_size('data')} + 2pt);
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

    def _create_manufacturer_label(self, layout: QGridLayout, driver: DriverState,
                                   label_bg: str, label_border: str, font_weight: str, column: int) -> None:
        """Create manufacturer logo label with text fallback."""
        mfr_label = QLabel(driver.car_manufacturer)
        mfr_color = driver.car_manufacturer_color
        logo_pixmap = self._get_manufacturer_logo_pixmap(driver)

        mfr_label.setStyleSheet(f"""
            QLabel {{
                color: {mfr_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: bold;
                {label_border}
            }}
        """)
        mfr_label.setAlignment(Qt.AlignCenter)
        mfr_label.setMinimumWidth(COLUMN_MIN_WIDTHS.CAR_MANUFACTURER)
        if logo_pixmap is not None:
            scaled_logo = logo_pixmap.scaled(
                COLUMN_MIN_WIDTHS.CAR_MANUFACTURER - 4,
                18,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            mfr_label.setPixmap(scaled_logo)
            mfr_label.setText("")
        mfr_label.setContextMenuPolicy(Qt.CustomContextMenu)
        mfr_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(mfr_label, 0, column)

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
        # Status colors: OUT in orange, TOW in red, otherwise default text color
        if driver.pit_lap == "OUT":
            pit_lap_color = "#FF8200"
        elif driver.pit_lap == "TOW":
            pit_lap_color = "#FF3B30"
        else:
            pit_lap_color = text_color

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
